"""The only module that talks to a model server.

Everything here speaks the OpenAI shape — `POST /embeddings` for vectors and
`POST /chat/completions` for text — which is what LM Studio serves locally, and
also what hosted gateways speak, so pointing `base_url` elsewhere is the only
change needed to move off the machine.

Retries, optional pacing and error surfacing live here so no stage repeats them.
"""

from __future__ import annotations

import json
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Sequence

import httpx

LOCAL_BASE_URL = "http://127.0.0.1:1234/v1"

# Some models put their scratchpad inline instead of in a separate field.
_THINK_BLOCK = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)

# Errors worth splitting an embedding batch over, rather than giving up.
_BATCH_TOO_BIG = ("too many", "batch", "exceed", "limit", "too large")


class LLMError(RuntimeError):
    """A request failed. `status` is the HTTP code, when there was one."""

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


class RateLimiter:
    """Spaces requests across threads. Pointless locally, needed for hosted APIs."""

    def __init__(self, requests_per_minute: int):
        self.interval = 60.0 / requests_per_minute if requests_per_minute > 0 else 0.0
        self._lock = threading.Lock()
        self._next_at = 0.0

    def wait(self) -> None:
        if not self.interval:
            return
        with self._lock:
            now = time.monotonic()
            start_at = max(now, self._next_at)
            self._next_at = start_at + self.interval
        delay = start_at - time.monotonic()
        if delay > 0:
            time.sleep(delay)


class LLMClient:
    """OpenAI-compatible client: `embed()` and `complete()`."""

    def __init__(
        self,
        base_url: str = LOCAL_BASE_URL,
        api_key: Optional[str] = None,
        requests_per_minute: int = 0,
        # Local generation is slow — a reasoning model can spend half a minute
        # per reply, and LM Studio may load the model on the first request.
        timeout: float = 300.0,
        max_retries: int = 3,
        app_title: str = "athletic-supplements-rag",
        log: Callable[[str], None] = print,
        transport: Optional[httpx.BaseTransport] = None,
        # Merged into every /chat/completions body. The OpenAI shape is the
        # common denominator between providers, not the whole of what any one
        # of them accepts — OpenRouter's routing preferences live here, for
        # instance, and a server that does not know a key ignores it.
        extra_body: Optional[Dict[str, Any]] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self.log = log
        self.limiter = RateLimiter(requests_per_minute)
        self.extra_body = dict(extra_body or {})

        headers = {"Content-Type": "application/json", "X-Title": app_title}
        if api_key:
            # LM Studio needs no key; hosted gateways do.
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.Client(
            timeout=timeout, transport=transport, headers=headers
        )

    # -- endpoints ---------------------------------------------------------- #
    def models(self) -> List[str]:
        """Model ids the server currently offers — also a reachability check."""
        body = self._get("/models")
        return sorted(row["id"] for row in body.get("data", []))

    def embed(self, model: str, inputs: Sequence[str]) -> List[List[float]]:
        """Embed a batch of strings, in the order given."""
        inputs = list(inputs)
        if not inputs:
            return []

        try:
            body = self._post(
                "/embeddings",
                {"model": model, "input": inputs, "encoding_format": "float"},
            )
        except LLMError as error:
            if not self._is_batch_too_big(error, len(inputs)):
                raise
            # If the server turns out to cap batch size, halve and carry on
            # rather than failing the whole run.
            middle = len(inputs) // 2
            self.log(f"Batch of {len(inputs)} rejected as too large; splitting.")
            return self.embed(model, inputs[:middle]) + self.embed(
                model, inputs[middle:]
            )

        rows = body.get("data") or []
        if len(rows) != len(inputs):
            raise LLMError(f"Asked for {len(inputs)} embeddings, got {len(rows)}.")
        # `index` is authoritative: servers may answer out of order.
        rows = sorted(rows, key=lambda row: row.get("index", 0))
        return [list(row["embedding"]) for row in rows]

    def complete(
        self,
        model: str,
        prompt: str,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        reasoning_effort: Optional[str] = None,
    ) -> str:
        """One user turn in, assistant text out.

        `reasoning_effort` is passed through for servers that honour it. Neither
        model this project ships with does — they reason regardless — so the
        budget in `max_tokens` has to cover the thinking as well as the answer.
        """
        payload: Dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if reasoning_effort:
            payload["reasoning"] = {"effort": reasoning_effort}
        # Caller-set keys win, so a per-call `reasoning` is not overwritten by a
        # per-endpoint default.
        for key, value in self.extra_body.items():
            payload.setdefault(key, value)

        return self._text_of(self._post("/chat/completions", payload))

    def tune(
        self,
        requests_per_minute: int,
        timeout: float,
        max_retries: int,
    ) -> None:
        """Adjust pacing, patience and retries in place.

        The UI changes these between requests, and rebuilding the client would
        throw away the connection pool for no reason.
        """
        self.limiter = RateLimiter(requests_per_minute)
        self._client.timeout = httpx.Timeout(timeout)
        self.max_retries = max_retries

    def close(self) -> None:
        self._client.close()

    # -- internals ---------------------------------------------------------- #
    @staticmethod
    def _text_of(body: Dict[str, Any]) -> str:
        choices = body.get("choices") or []
        if not choices:
            raise LLMError(f"No choices in response: {json.dumps(body)[:300]}")

        choice = choices[0]
        content = (choice.get("message") or {}).get("content") or ""
        if not content.strip():
            # A reasoning model that spends the whole token budget thinking
            # answers with empty content and finish_reason="length". Silently
            # returning "" would look like a model with nothing to say, so say
            # what actually happened.
            reasoning_tokens = (
                (body.get("usage") or {})
                .get("completion_tokens_details", {})
                .get("reasoning_tokens", 0)
            )
            raise LLMError(
                "Empty reply "
                f"(finish_reason={choice.get('finish_reason')!r}, "
                f"reasoning_tokens={reasoning_tokens}). "
                "Raise max_tokens: reasoning comes out of the same budget."
            )
        return _THINK_BLOCK.sub("", content).strip()

    @staticmethod
    def _is_batch_too_big(error: LLMError, count: int) -> bool:
        message = str(error).lower()
        return (
            count > 1
            and error.status == 400
            and any(hint in message for hint in _BATCH_TOO_BIG)
        )

    def _get(self, path: str) -> Dict[str, Any]:
        self.limiter.wait()
        try:
            response = self._client.get(f"{self.base_url}{path}")
        except httpx.RequestError as exc:
            raise self._unreachable(exc) from exc
        if response.status_code != 200:
            raise LLMError(
                f"{path} -> HTTP {response.status_code}: {response.text[:200]}",
                response.status_code,
            )
        return response.json()

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        last_error = "unknown error"

        for attempt in range(self.max_retries):
            self.limiter.wait()
            try:
                response = self._client.post(f"{self.base_url}{path}", json=payload)
            except httpx.ConnectError as exc:
                raise self._unreachable(exc) from exc  # retrying will not help
            except httpx.RequestError as exc:  # timeout, reset connection
                last_error = str(exc)
                self._backoff(attempt, f"{path} failed ({exc})")
                continue

            if response.status_code == 200:
                body = response.json()
                # Some servers report upstream failures as 200 + error body.
                if isinstance(body, dict) and body.get("error"):
                    raise LLMError(f"{path}: {body['error']}", 200)
                return body

            detail = response.text[:300]
            last_error = f"HTTP {response.status_code}: {detail}"
            if response.status_code == 429 or response.status_code >= 500:
                self._backoff(
                    attempt,
                    f"{path} got HTTP {response.status_code}",
                    self._retry_after(response),
                )
                continue
            # 400/401/403/404 will not fix themselves.
            raise LLMError(f"{path} -> {last_error}", response.status_code)

        raise LLMError(
            f"{path} failed after {self.max_retries} attempts. Last: {last_error}"
        )

    def _unreachable(self, exc: Exception) -> LLMError:
        return LLMError(
            f"Cannot reach the model server at {self.base_url} ({exc}). "
            "Is LM Studio running with the local server started, and both models "
            "loaded?"
        )

    def _backoff(self, attempt: int, message: str, seconds: Optional[float] = None):
        if attempt >= self.max_retries - 1:
            return  # caller is about to raise
        delay = seconds if seconds is not None else float(2**attempt)
        self.log(f"{message}; retrying in {delay:.0f}s...")
        time.sleep(delay)

    @staticmethod
    def _retry_after(response: httpx.Response) -> Optional[float]:
        """Honour `Retry-After` when the server sends one."""
        header = response.headers.get("retry-after")
        try:
            return float(header) if header else None
        except ValueError:
            return None  # HTTP-date form; fall back to exponential backoff
