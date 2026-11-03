from __future__ import annotations

from target_profile.config import Settings
from target_profile.models import ModuleResult


def _number(value):
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def build_summary(modules: list[ModuleResult], settings: Settings) -> ModuleResult:
    by_name = {module.name: module for module in modules}
    cards: list[dict] = []

    basic = by_name.get("basic")
    if basic and basic.facts.get("target_class"):
        cards.append(
            {"label": "靶点类别", "value": basic.facts["target_class"], "level": "info"}
        )

    disease = by_name.get("disease")
    if disease and disease.facts.get("top_disease"):
        cards.append(
            {"label": "Top 关联疾病", "value": disease.facts["top_disease"], "level": "info"}
        )

    expression = by_name.get("expression")
    tau = _number(expression.facts.get("tau")) if expression else None
    if tau is not None:
        if tau >= settings.thresholds.tissue_specific_tau:
            level, text = "ok", "组织特异"
        elif tau >= settings.thresholds.tissue_partial_tau:
            level, text = "info", "偏特异表达"
        else:
            level, text = "info", "广泛表达"
        cards.append(
            {"label": "组织表达模式", "value": f"{text} · τ={tau:.3f}", "level": level}
        )

    mutation = by_name.get("mutation")
    frequency = _number(mutation.facts.get("overall_freq_pct")) if mutation else None
    if frequency is not None:
        hot = frequency > settings.thresholds.pan_cancer_hotspot_pct
        cards.append(
            {
                "label": "泛癌突变率",
                "value": f"{frequency:.2f}%" + (" · 高频" if hot else ""),
                "level": "warn" if hot else "info",
            }
        )

    dependency = by_name.get("dependency")
    mean_effect = _number(dependency.facts.get("mean_effect")) if dependency else None
    if mean_effect is not None:
        strong = mean_effect <= settings.thresholds.strong_dependency_effect
        cards.append(
            {
                "label": "依赖性",
                "value": ("强依赖" if strong else "非强依赖") + f" · 平均效应 {mean_effect:.3f}",
                "level": "ok" if strong else "info",
            }
        )

    safety = by_name.get("safety")
    if safety:
        essential = safety.facts.get("common_essential")
        if essential:
            cards.append(
                {
                    "label": "泛癌必需",
                    "value": str(essential),
                    "level": "warn" if essential == "Yes" else "info",
                }
            )
        loeuf = _number(safety.facts.get("loeuf"))
        if loeuf is not None:
            constrained = loeuf < settings.thresholds.loeuf_constrained
            cards.append(
                {
                    "label": "LoF 约束",
                    "value": ("强约束" if constrained else "无强约束") + f" · LOEUF {loeuf:.3f}",
                    "level": "info",
                }
            )
        liabilities = _number(safety.facts.get("n_safety_liabilities"))
        if liabilities is not None:
            if liabilities > 0:
                value = f"{int(liabilities)} 条安全事件记录"
                level = "warn"
            else:
                value = "无安全事件记录（不代表安全）"
                level = "info"
            cards.append({"label": "安全警示", "value": value, "level": level})

    tractability = by_name.get("tractability")
    if tractability and tractability.facts.get("tractable"):
        tractable = str(tractability.facts["tractable"])
        cards.append(
            {
                "label": "可成药性",
                "value": tractable,
                "level": "ok" if tractable == "Yes" else "info",
            }
        )

    cancer = by_name.get("cancer")
    if cancer and cancer.facts.get("driver_status"):
        status = str(cancer.facts["driver_status"])
        cards.append(
            {
                "label": "癌症驱动",
                "value": status,
                "level": "warn" if status == "驱动证据阳性" else "info",
            }
        )

    result = ModuleResult(name="summary")
    result.label_cards = cards
    result.facts = {
        "n_label_cards": len(cards),
        "thresholds": {
            "tissue_specific_tau": settings.thresholds.tissue_specific_tau,
            "tissue_partial_tau": settings.thresholds.tissue_partial_tau,
            "pan_cancer_hotspot_pct": settings.thresholds.pan_cancer_hotspot_pct,
            "strong_dependency_effect": settings.thresholds.strong_dependency_effect,
            "loeuf_constrained": settings.thresholds.loeuf_constrained,
        },
    }
    if not cards:
        return result.degrade("summary: insufficient facts for label cards")
    return result
