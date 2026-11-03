from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def cache_key(gene: str, facts: dict[str, Any], model: str, prompt_version: str) -> str:
    payload = json.dumps(
        {"gene": gene, "facts": facts, "model": model, "prompt_version": prompt_version},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


class NarrativeCache:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def get(self, key: str) -> str | None:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("text")
        except (json.JSONDecodeError, OSError):
            return None

    def put(self, key: str, text: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._path(key).write_text(
            json.dumps({"text": text}, ensure_ascii=False), encoding="utf-8"
        )
