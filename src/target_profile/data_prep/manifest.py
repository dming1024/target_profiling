import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class SourceEntry(BaseModel):
    name: str
    path: str
    version: str
    license: str
    fetched_at: str
    sha256: str
    rows: int | None = None
    note: str = ""


class Manifest(BaseModel):
    generated_at: str = Field(default_factory=now_iso)
    sources: list[SourceEntry] = Field(default_factory=list)


def write_manifest(entries: list[SourceEntry], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = Manifest(sources=entries)
    path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
