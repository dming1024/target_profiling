import json
from pathlib import Path
from typing import Any

import httpx

from target_profile.data_prep.manifest import now_iso
from target_profile.errors import OfflineCacheMiss


class CachedFetcher:
    """Cache-first JSON fetcher. Cache path: <cache_dir>/<gene>/<name>.json."""

    def __init__(
        self,
        cache_dir: Path,
        offline: bool = False,
        client: Any | None = None,
        timeout: float = 90.0,
    ) -> None:
        self.cache_dir = cache_dir
        self.offline = offline
        self.client = client or httpx.Client(timeout=timeout)

    def _path(self, gene: str, name: str) -> Path:
        safe = name.replace("/", "_").replace(" ", "_")
        return self.cache_dir / gene / f"{safe}.json"

    def request_json(
        self,
        name: str,
        method: str,
        url: str,
        gene: str,
        params: dict | None = None,
        json_body: dict | None = None,
        refresh: bool = False,
    ) -> Any:
        path = self._path(gene, name)
        if path.exists() and not refresh:
            return json.loads(path.read_text(encoding="utf-8"))
        if self.offline:
            raise OfflineCacheMiss(f"offline: missing cache {path}")
        response = self.client.request(method, url, params=params, json=json_body)
        response.raise_for_status()
        payload = response.json()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        meta = path.with_suffix(".meta.json")
        meta.write_text(
            json.dumps(
                {"url": url, "method": method, "fetched_at": now_iso()},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return payload
