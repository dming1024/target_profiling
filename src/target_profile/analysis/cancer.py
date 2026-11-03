from __future__ import annotations

import pandas as pd

from target_profile.api.cache import CachedFetcher
from target_profile.api.opentargets import target_cancer, target_safety
from target_profile.config import Settings
from target_profile.models import GeneContext, ModuleResult


def analyze_cancer(
    ctx: GeneContext,
    settings: Settings,
    offline: bool = True,
    fetcher: CachedFetcher | None = None,
    prior: dict[str, ModuleResult] | None = None,
) -> ModuleResult:
    result = ModuleResult(name="cancer")
    fetcher = fetcher or CachedFetcher(settings.data_root / "cache", offline=offline)
    prior = prior or {}

    hallmarks: list[dict] = []
    try:
        payload = target_cancer(ctx.ensembl_id, fetcher)
    except Exception as exc:
        payload = None
        result.caveats.append(f"cancer: Open Targets hallmarks unavailable ({exc})")

    if payload:
        hallmarks = (payload.get("hallmarks") or {}).get("cancerHallmarks") or []

    if hallmarks:
        frame = pd.DataFrame(
            [
                {"label": item.get("label"), "impact": item.get("impact") or "unknown"}
                for item in hallmarks
                if item.get("label")
            ]
        )
        frame = frame.drop_duplicates()
        if not frame.empty:
            counts = (
                frame.groupby(["label", "impact"])
                .size()
                .unstack(fill_value=0)
                .reset_index()
            )
            for column in ("promotes", "suppresses"):
                if column not in counts.columns:
                    counts[column] = 0
            counts["total"] = counts["promotes"] + counts["suppresses"]
            counts = counts.sort_values(
                ["total", "promotes", "label"],
                ascending=[False, False, True],
                kind="stable",
            )
            result.tables["hallmarks"] = counts[
                ["label", "promotes", "suppresses", "total"]
            ].reset_index(drop=True)
            result.facts["n_cancer_hallmarks"] = int(frame["label"].nunique())
            result.facts["top_hallmark"] = str(counts.iloc[0]["label"])
            result.facts["cancer_hallmark_impacts"] = "; ".join(
                f"{row.label}: promotes {row.promotes}, suppresses {row.suppresses}"
                for row in counts.itertuples()
            )

    essential = None
    try:
        safety = target_safety(ctx.ensembl_id, fetcher)
        if safety is not None and safety.get("isEssential") is not None:
            essential = bool(safety["isEssential"])
    except Exception as exc:
        result.caveats.append(f"cancer: isEssential unavailable ({exc})")
    result.facts["essential"] = (
        "Yes" if essential else ("No" if essential is not None else "Unknown")
    )

    mutation = prior.get("mutation")
    frequency = None
    if mutation is not None and mutation.status == "ok":
        frequency = mutation.facts.get("overall_freq_pct")
    result.facts["pan_cancer_freq_pct"] = frequency

    threshold = settings.thresholds.pan_cancer_hotspot_pct
    has_hallmarks = "hallmarks" in result.tables
    if frequency is None and not has_hallmarks:
        status = "未知"
        basis = "缺少突变与 hallmark 数据"
    elif frequency is not None and frequency >= threshold:
        status = "驱动证据阳性"
        basis = f"泛癌突变率 {frequency}% 达到阈值 {threshold}%"
    elif has_hallmarks:
        status = "驱动证据阳性"
        basis = "命中 Open Targets 癌症 hallmark"
    else:
        status = "证据不足"
        basis = f"泛癌突变率 {frequency}% 低于阈值 {threshold}%，且无 hallmark 记录"
    result.facts["driver_status"] = status
    result.caveats.append(
        f"cancer: 驱动状态为规则推导（{basis}）；Open Targets v4 未提供 isCancerDriverGene 字段"
    )

    if not result.tables:
        return result.degrade("cancer: no hallmark data")
    return result
