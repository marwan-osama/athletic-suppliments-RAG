"""Golden-dataset loader — JSON, JSONL, and CSV all supported.

The evaluator needs four fields per sample:

    question        The user query.
    ground_truth    The ideal (reference) answer.
    contexts        A list of retrieved passage strings.
    answer          The generated answer to evaluate.

Any file format may include extra columns; they are carried through but
ignored by the scoring engine.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List

# ── required schema ──────────────────────────────────────────────────── #
REQUIRED_FIELDS = {"question", "ground_truth", "contexts", "answer"}


class DatasetLoadError(ValueError):
    """Raised when a golden-dataset file is malformed or missing fields."""


# ── public entry point ───────────────────────────────────────────────── #

def load_dataset(path: str | Path) -> List[Dict[str, Any]]:
    """Load a golden evaluation dataset from JSON, JSONL, or CSV.

    Returns a list of dicts with the canonical field names:
    ``question``, ``ground_truth``, ``contexts``, ``answer``.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Dataset file not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".json":
        records = _load_json(path)
    elif suffix == ".jsonl":
        records = _load_jsonl(path)
    elif suffix == ".csv":
        records = _load_csv(path)
    else:
        raise DatasetLoadError(
            f"Unsupported file format '{suffix}'. Use .json, .jsonl, or .csv."
        )

    if not records:
        raise DatasetLoadError(f"No records found in {path}.")

    _validate(records, path)

    # Ensure "contexts" is always a list of strings.
    for record in records:
        if isinstance(record["contexts"], str):
            record["contexts"] = _parse_contexts(record["contexts"])

    return records


# ── format-specific loaders ──────────────────────────────────────────── #

def _load_json(path: Path) -> List[Dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, list):
        return data
    raise DatasetLoadError(f"{path}: expected a JSON array at top level.")


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    records = []
    with open(path, encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise DatasetLoadError(
                    f"{path}:{line_number}: invalid JSON — {exc}"
                ) from exc
    return records


def _load_csv(path: Path) -> List[Dict[str, Any]]:
    """Read a CSV file.

    The ``contexts`` column may contain either:
    - A JSON array string:  ``["passage one", "passage two"]``
    - A semicolon-separated string:  ``passage one; passage two``
    """
    records = []
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            records.append(dict(row))
    return records


# ── helpers ──────────────────────────────────────────────────────────── #

def _parse_contexts(raw: str) -> List[str]:
    """Turn a CSV string value into a list of context passages."""
    raw = raw.strip()
    # Try JSON array first.
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except json.JSONDecodeError:
            pass
    # Fall back to semicolon-separated.
    return [segment.strip() for segment in raw.split(";") if segment.strip()]


def _validate(records: List[Dict[str, Any]], path: Path) -> None:
    """Ensure every record has the four required fields."""
    for index, record in enumerate(records):
        missing = REQUIRED_FIELDS - set(record.keys())
        if missing:
            raise DatasetLoadError(
                f"{path}: record {index} is missing fields: {sorted(missing)}"
            )
