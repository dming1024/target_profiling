import json

import pytest

from target_profile.api.cache import CachedFetcher
from target_profile.errors import OfflineCacheMiss


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def request(self, method, url, params=None, json=None):
        self.calls += 1
        return FakeResponse(self.payload)


def test_cache_hit_avoids_network(tmp_path):
    fetcher = CachedFetcher(tmp_path, offline=False, client=FakeClient({"ok": 1}))
    first = fetcher.request_json("t", "GET", "https://example.org/x", gene="KRAS")
    second = fetcher.request_json("t", "GET", "https://example.org/x", gene="KRAS")
    assert first == second == {"ok": 1}
    assert fetcher.client.calls == 1
    assert json.loads((tmp_path / "KRAS" / "t.json").read_text()) == {"ok": 1}


def test_offline_miss_raises(tmp_path):
    fetcher = CachedFetcher(tmp_path, offline=True, client=FakeClient({"ok": 1}))
    with pytest.raises(OfflineCacheMiss):
        fetcher.request_json("t", "GET", "https://example.org/x", gene="KRAS")


def test_refresh_forces_network(tmp_path):
    client = FakeClient({"ok": 2})
    fetcher = CachedFetcher(tmp_path, offline=False, client=client)
    fetcher.request_json("t", "GET", "https://example.org/x", gene="KRAS")
    fetcher.request_json("t", "GET", "https://example.org/x", gene="KRAS", refresh=True)
    assert client.calls == 2
