"""The only module that talks to a model provider.

OpenRouter speaks the OpenAI shape: `POST /embeddings` for vectors and
`POST /chat/completions` for text, both under one API key. Retries, rate
limiting and error surfacing live here so no stage has to repeat them.

The `:free` model variants allow roughly 20 requests per minute (plus a daily
cap), so requests are paced by default rather than fired as fast as the thread
pool can manage — an unpaced indexing run would spend its time collecting 429s.
"""

from __future__ import annotations

import json
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Sequence

import httpx

BASE_URL = "https://openrouter.ai/api/v1"

# Some reasoning models put their scratchpad inline instead of in the separate
# `reasoning` field.
_THINK_BLOCK = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)

# Errors worth splitting an embedding batch over, rather than giving up.
_BATCH_TOO_BIG = ("too many", "batch", "exceed", "limit", "too large")


class OpenRouterError(RuntimeError):
    """A request failed. `status` is the HTTP code, when there was one."""

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


class RateLimiter:
    """Spaces requests across threads so a free endpoint stays happy."""

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


class OpenRouterClient:
    """Thin OpenRouter API client: `embed()` and `complete()`."""

    def __init__(
        self,
        api_key: Optional[str],
        base_url: str = BASE_URL,
        requests_per_minute: int = 20,
        timeout: float = 180.0,
        max_retries: int = 5,
        app_title: str = "athletic-supplements-rag",
        log: Callable[[str], None] = print,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        if not api_key:
            raise OpenRouterError(
                "An OpenRouter API key is required — set OPENROUTER_API_KEY."
            )
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self.log = log
        self.limiter = RateLimiter(requests_per_minute)
        self._client = httpx.Client(
            timeout=timeout,
            transport=transport,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                # Optional attribution, used by OpenRouter's app rankings.
                "X-Title": app_title,
            },
        )

    # -- endpoints ---------------------------------------------------------- #
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
        except OpenRouterError as error:
            if not self._is_batch_too_big(error, len(inputs)):
                raise
            # The endpoint does not document a batch ceiling; if it turns out to
            # have one, halve and carry on instead of failing the whole run.
            middle = len(inputs) // 2
            self.log(f"Batch of {len(inputs)} rejected as too large; splitting.")
            return self.embed(model, inputs[:middle]) + self.embed(
                model, inputs[middle:]
            )

        rows = body.get("data") or []
        if len(rows) != len(inputs):
            raise OpenRouterError(
                f"Asked for {len(inputs)} embeddings, got {len(rows)}."
            )
        # `index` is authoritative: providers may answer out of order.
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

        `reasoning_effort="none"` switches reasoning off for mechanical tasks
        (question generation), which is both faster and cheaper in requests.
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

        return self._text_of(self._post("/chat/completions", payload))

    def close(self) -> None:
        self._client.close()

    # -- internals ---------------------------------------------------------- #
    @staticmethod
    def _text_of(body: Dict[str, Any]) -> str:
        choices = body.get("choices") or []
        if not choices:
            raise OpenRouterError(f"No choices in response: {json.dumps(body)[:300]}")

        choice = choices[0]
        content = (choice.get("message") or {}).get("content") or ""
        if not content.strip():
            # A reasoning model that spends the whole token budget thinking
            # answers with content=None and finish_reason="length". Silently
            # returning "" would look like a model that had nothing to say, so
            # say what actually happened.
            reasoning_tokens = (
                (body.get("usage") or {})
                .get("completion_tokens_details", {})
                .get("reasoning_tokens", 0)
            )
            raise OpenRouterError(
                "Empty reply "
                f"(finish_reason={choice.get('finish_reason')!r}, "
                f"reasoning_tokens={reasoning_tokens}). "
                "Raise max_tokens: reasoning is billed against the same budget."
            )
        return _THINK_BLOCK.sub("", content).strip()

    @staticmethod
    def _is_batch_too_big(error: OpenRouterError, count: int) -> bool:
        message = str(error).lower()
        return (
            count > 1
            and error.status == 400
            and any(hint in message for hint in _BATCH_TOO_BIG)
        )

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        last_error = "unknown error"

        for attempt in range(self.max_retries):
            self.limiter.wait()
            try:
                response = self._client.post(f"{self.base_url}{path}", json=payload)
            except httpx.RequestError as exc:  # timeout, reset connection, DNS
                last_error = str(exc)
                self._backoff(attempt, f"{path} failed ({exc})")
                continue

            if response.status_code == 200:
                body = response.json()
                # OpenRouter reports some upstream failures as 200 + error body.
                if isinstance(body, dict) and body.get("error"):
                    raise OpenRouterError(f"{path}: {body['error']}", 200)
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
            raise OpenRouterError(f"{path} -> {last_error}", response.status_code)

        raise OpenRouterError(
            f"{path} failed after {self.max_retries} attempts. Last: {last_error}"
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
