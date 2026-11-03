from target_profile.config import LLMSettings, Settings
from target_profile.llm import build_narratives
from target_profile.llm.cache import NarrativeCache, cache_key
from target_profile.models import ModuleResult


def test_cache_key_is_stable_and_facts_sensitive():
    first = cache_key("KRAS", {"a": 1}, "model", "v1")
    second = cache_key("KRAS", {"a": 1}, "model", "v1")
    third = cache_key("KRAS", {"a": 2}, "model", "v1")
    assert first == second
    assert first != third


def test_cache_roundtrip(tmp_path):
    cache = NarrativeCache(tmp_path / "cache")
    key = cache_key("KRAS", {"a": 1}, "model", "v1")
    assert cache.get(key) is None
    cache.put(key, "解读文本")
    assert cache.get(key) == "解读文本"


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def complete(self, system, user):
        self.calls += 1
        if not self.replies:
            raise AssertionError("unexpected LLM call")
        return self.replies.pop(0)


def _settings(tmp_path, enabled=True):
    return Settings(
        lake_root=tmp_path / "lake",
        data_root=tmp_path / "data",
        out_root=tmp_path / "out",
        llm=LLMSettings(enabled=enabled, base_url="http://example.invalid/v1", model="gpt-test"),
    )


def _mutation_module():
    return ModuleResult(
        name="mutation",
        facts={
            "overall_freq_pct": 6.96,
            "top_cancer": "PAAD",
            "top_cancer_freq_pct": 63.59,
            "top_protein_change": "G12D",
            "top_protein_change_count": 197,
        },
    )


def test_pipeline_uses_valid_llm_output(tmp_path, monkeypatch):
    monkeypatch.setenv("TARGET_PROFILE_LLM_API_KEY", "key")
    client = FakeClient(["KRAS 泛癌突变率为 6.96%。"])
    modules = [_mutation_module()]
    info = build_narratives("KRAS", modules, _settings(tmp_path), enabled=True, client=client)
    assert modules[0].narrative == "KRAS 泛癌突变率为 6.96%。"
    assert info["used"] == 1
    assert client.calls == 1


def test_pipeline_falls_back_on_guard_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("TARGET_PROFILE_LLM_API_KEY", "key")
    client = FakeClient(["KRAS 突变率为 99.9%。", "KRAS 突变率高达 88.8%。"])
    modules = [_mutation_module()]
    info = build_narratives("KRAS", modules, _settings(tmp_path), enabled=True, client=client)
    assert modules[0].narrative.startswith("TCGA PanCancer")
    assert info["fallback"] == 1
    assert client.calls == 2


def test_pipeline_uses_cache_on_second_run(tmp_path, monkeypatch):
    monkeypatch.setenv("TARGET_PROFILE_LLM_API_KEY", "key")
    first = FakeClient(["KRAS 泛癌突变率为 6.96%。"])
    build_narratives("KRAS", [_mutation_module()], _settings(tmp_path), enabled=True, client=first)
    second = FakeClient([])
    modules = [_mutation_module()]
    info = build_narratives("KRAS", modules, _settings(tmp_path), enabled=True, client=second)
    assert modules[0].narrative == "KRAS 泛癌突变率为 6.96%。"
    assert info["cached"] == 1
    assert second.calls == 0


def test_pipeline_no_llm_uses_template(tmp_path):
    modules = [_mutation_module()]
    info = build_narratives("KRAS", modules, _settings(tmp_path), enabled=False, client=None)
    assert modules[0].narrative.startswith("TCGA PanCancer")
    assert info["used"] == 0


def test_pipeline_missing_api_key_falls_back(tmp_path, monkeypatch):
    monkeypatch.delenv("TARGET_PROFILE_LLM_API_KEY", raising=False)
    modules = [_mutation_module()]
    info = build_narratives("KRAS", modules, _settings(tmp_path), enabled=True, client=None)
    assert modules[0].narrative.startswith("TCGA PanCancer")
    assert "error" in info
