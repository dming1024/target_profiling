from __future__ import annotations

import pandas as pd

from target_profile.api.cache import CachedFetcher
from target_profile.api.opentargets import target_safety
from target_profile.config import Settings
from target_profile.models import GeneContext, ModuleResult


def analyze_comparative(
    ctx: GeneContext,
    settings: Settings,
    offline: bool = True,
    fetcher: CachedFetcher | None = None,
    prior: dict[str, ModuleResult] | None = None,
) -> ModuleResult:
    result = ModuleResult(name="comparative")
    fetcher = fetcher or CachedFetcher(settings.data_root / "cache", offline=offline)

    try:
        details = target_safety(ctx.ensembl_id, fetcher)
    except Exception as exc:
        return result.degrade(f"comparative: Open Targets homologues unavailable ({exc})")
    if not details:
        return result.degrade("comparative: no homologues payload")

    rows = []
    for item in details.get("homologues") or []:
        identity = item.get("queryPercentageIdentity")
        if identity is None:
            continue
        if item.get("targetGeneId") == ctx.ensembl_id:
            continue
        rows.append(
            {
                "species": item.get("speciesName") or "Unknown",
                "type": item.get("homologyType") or "unknown",
                "identity": round(float(identity), 1),
                "target_gene_id": item.get("targetGeneId"),
            }
        )
    if not rows:
        return result.degrade("comparative: no homologues with identity scores")

    frame = pd.DataFrame(rows).sort_values("identity", ascending=False)
    frame = frame.reset_index(drop=True)
    result.tables["homologues"] = frame

    orthologues = frame[frame["type"].str.contains("ortholog", case=False, na=False)]
    paralogues = frame[frame["type"].str.contains("paralog", case=False, na=False)]
    top = frame.iloc[0]
    result.facts["n_homologues"] = int(len(frame))
    result.facts["top_homologue"] = str(top["species"])
    result.facts["top_homologue_identity"] = float(top["identity"])
    if not orthologues.empty:
        result.facts["top_orthologue"] = str(orthologues.iloc[0]["species"])
        result.facts["top_orthologue_identity"] = float(orthologues.iloc[0]["identity"])
    if not paralogues.empty:
        result.facts["n_paralogues"] = int(len(paralogues))
        result.facts["top_paralogue_identity"] = float(paralogues.iloc[0]["identity"])
    else:
        result.caveats.append("comparative: 未记录种内旁系同源")
    return result
