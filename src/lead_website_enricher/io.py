from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def load_rows(path: str | Path) -> list[dict[str, Any]]:
    file_path = Path(path)
    suffix = file_path.suffix.casefold()
    if suffix == ".json":
        payload = json.loads(file_path.read_text())
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict) and isinstance(payload.get("rows"), list):
            return payload["rows"]
        raise ValueError("JSON input must be a list of lead rows or an object with a rows array.")
    if suffix == ".jsonl":
        return [json.loads(line) for line in file_path.read_text().splitlines() if line.strip()]
    if suffix == ".csv":
        with file_path.open(newline="") as handle:
            return list(csv.DictReader(handle))
    raise ValueError(f"Unsupported input format: {file_path}")


def dump_json(path: str | Path, payload: Any) -> None:
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True))
