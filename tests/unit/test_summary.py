from target_profile.analysis.summary import build_summary
from target_profile.config import Settings
from target_profile.models import ModuleResult


def _settings(tmp_path):
    return Settings(
        lake_root=tmp_path / "lake", data_root=tmp_path / "data", out_root=tmp_path / "out"
    )


def _module(name, **facts):
    return ModuleResult(name=name, facts=facts)


def test_summary_cards_for_hot_target(tmp_path):
    modules = [
        _module("basic", target_class="Enzyme / Hydrolase"),
        _module("disease", top_disease="Noonan syndrome"),
        _module("expression", tau=0.95),
        _module("mutation", overall_freq_pct=6.96),
        _module("dependency", mean_effect=-0.62),
        _module("tractability", tractable="Yes"),
        _module("safety", common_essential="Yes", loeuf=0.2264, n_safety_liabilities=0),
        _module("cancer", driver_status="驱动证据阳性"),
    ]
    summary = build_summary(modules, _settings(tmp_path))
    cards = {card["label"]: card for card in summary.label_cards}
    assert cards["靶点类别"]["value"] == "Enzyme / Hydrolase"
    assert cards["Top 关联疾病"]["value"] == "Noonan syndrome"
    assert cards["组织表达模式"]["level"] == "ok"
    assert "组织特异" in cards["组织表达模式"]["value"]
    assert cards["泛癌突变率"]["level"] == "warn"
    assert "强依赖" in cards["依赖性"]["value"]
    assert cards["泛癌必需"]["value"] == "Yes"
    assert cards["LoF 约束"]["value"].startswith("强约束")
    assert cards["可成药性"]["value"] == "Yes"
    assert cards["安全警示"]["level"] == "info"
    assert cards["癌症驱动"]["level"] == "warn"
    assert summary.facts["thresholds"]["pan_cancer_hotspot_pct"] == 5.0


def test_summary_general_expression_and_safety_warning(tmp_path):
    modules = [
        _module("expression", tau=0.2),
        _module("mutation", overall_freq_pct=1.0),
        _module("safety", n_safety_liabilities=3, loeuf=1.2),
    ]
    summary = build_summary(modules, _settings(tmp_path))
    cards = {card["label"]: card for card in summary.label_cards}
    assert "广泛表达" in cards["组织表达模式"]["value"]
    assert cards["泛癌突变率"]["level"] == "info"
    assert cards["安全警示"]["level"] == "warn"
    assert cards["LoF 约束"]["value"].startswith("无强约束")


def test_summary_degrades_without_facts(tmp_path):
    summary = build_summary([], _settings(tmp_path))
    assert summary.status == "no_data"
