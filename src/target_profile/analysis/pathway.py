import pandas as pd

from target_profile.api.cache import CachedFetcher
from target_profile.api.opentargets import target_pathways
from target_profile.api.stringdb import interaction_partners
from target_profile.config import Settings
from target_profile.models import GeneContext, ModuleResult

ASPECT_NAMES = {
    "P": "Biological process",
    "F": "Molecular function",
    "C": "Cellular component",
}


def analyze_pathway(
    ctx: GeneContext,
    settings: Settings,
    offline: bool = True,
    fetcher: CachedFetcher | None = None,
) -> ModuleResult:
    result = ModuleResult(name="pathway")
    fetcher = fetcher or CachedFetcher(settings.data_root / "cache", offline=offline)

    details = None
    try:
        details = target_pathways(ctx.ensembl_id, fetcher)
    except Exception as exc:
        result.caveats.append(f"pathway: Open Targets unavailable ({exc})")

    if details:
        pathways = details.get("pathways") or []
        if pathways:
            frame = pd.DataFrame(pathways).drop_duplicates(subset=["pathwayId"])
            counts = (
                frame["topLevelTerm"]
                .fillna("Other")
                .value_counts()
                .rename_axis("topLevelTerm")
                .reset_index(name="count")
            )
            result.tables["pathways"] = frame.sort_values("topLevelTerm")[
                ["pathwayId", "pathway", "topLevelTerm"]
            ]
            result.tables["top_levels"] = counts
            result.facts["n_pathways"] = int(len(frame))
            result.facts["top_level_term"] = str(counts.iloc[0]["topLevelTerm"])
            result.facts["top_level_terms"] = ", ".join(
                counts.head(3)["topLevelTerm"].astype(str)
            )

        ontology = details.get("geneOntology") or []
        if ontology:
            rows = [
                {
                    "aspect": ASPECT_NAMES.get(item.get("aspect"), item.get("aspect")),
                    "term_id": (item.get("term") or {}).get("id"),
                    "term": (item.get("term") or {}).get("label"),
                    "evidence": item.get("evidence"),
                }
                for item in ontology
            ]
            go_frame = pd.DataFrame(rows).dropna(subset=["term"])
            grouped = (
                go_frame.groupby(["aspect", "term"])
                .size()
                .reset_index(name="evidence_count")
                .sort_values("evidence_count", ascending=False)
            )
            result.tables["go_terms"] = grouped.head(30)
            result.facts["n_go_terms"] = int(go_frame["term"].nunique())
            aspect_counts = (
                go_frame.drop_duplicates(subset=["term"])
                .groupby("aspect")
                .size()
                .reindex([ASPECT_NAMES[code] for code in sorted(ASPECT_NAMES)])
                .dropna()
                .astype(int)
            )
            result.facts["go_aspect_summary"] = " / ".join(
                f"{name} {int(count)}" for name, count in aspect_counts.items()
            )

    partners = []
    try:
        partners = interaction_partners(ctx.symbol, fetcher)
    except Exception as exc:
        result.caveats.append(f"pathway: STRING unavailable ({exc})")

    if partners:
        frame = pd.DataFrame(partners)
        if {"preferredName_B", "score"} <= set(frame.columns):
            threshold = settings.thresholds.string_min_score
            frame = frame[frame["preferredName_B"] != ctx.symbol]
            frame = frame.drop_duplicates(subset=["preferredName_B"])
            high = frame[frame["score"] >= threshold].sort_values(
                "score", ascending=False
            )
            if not high.empty:
                result.tables["partners"] = high[
                    ["preferredName_B", "score"]
                ].head(30).reset_index(drop=True)
                result.facts["n_partners_high_conf"] = int(len(high))
                result.facts["top_partner"] = str(high.iloc[0]["preferredName_B"])
                result.facts["top_partner_score"] = round(
                    float(high.iloc[0]["score"]), 3
                )

    if not result.tables:
        return result.degrade("pathway: no pathway or interaction data")
    return result
