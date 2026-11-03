import pandas as pd

from target_profile.api.cache import CachedFetcher
from target_profile.api.cbioportal import fetch_pancan_mutations
from target_profile.config import Settings
from target_profile.models import GeneContext, ModuleResult


def analyze_mutation(
    ctx: GeneContext,
    settings: Settings,
    offline: bool = True,
    fetcher: CachedFetcher | None = None,
) -> ModuleResult:
    result = ModuleResult(name="mutation")
    if not ctx.entrez_id:
        return result.degrade("mutation: entrez ID unavailable")
    fetcher = fetcher or CachedFetcher(settings.data_root / "cache", offline=offline)

    try:
        mutations, studies = fetch_pancan_mutations(ctx.symbol, ctx.entrez_id, fetcher)
    except Exception as exc:
        return result.degrade(f"mutation: cBioPortal unavailable ({exc})")

    if studies.empty:
        return result.degrade("mutation: no TCGA PanCancer studies")

    studies = studies.copy()
    studies["freq_pct"] = studies.apply(
        lambda row: round(100 * row["n_mutated_samples"] / row["n_samples"], 2)
        if row["n_samples"]
        else 0.0,
        axis=1,
    )
    studies = studies.sort_values("freq_pct", ascending=False)
    total_samples = int(studies["n_samples"].sum())
    total_mutated = int(studies["n_mutated_samples"].sum())

    type_counts = (
        mutations["mutationType"]
        .fillna("Unknown")
        .value_counts()
        .rename_axis("mutationType")
        .reset_index(name="count")
    )
    protein_counts = (
        mutations["proteinChange"]
        .dropna()
        .value_counts()
        .rename_axis("proteinChange")
        .reset_index(name="count")
    )

    result.tables["cancers"] = studies
    result.tables["types"] = type_counts
    result.tables["protein_changes"] = protein_counts
    result.facts.update(
        {
            "n_studies": int(len(studies)),
            "n_samples": total_samples,
            "n_mutated_samples": total_mutated,
            "overall_freq_pct": round(100 * total_mutated / total_samples, 2) if total_samples else 0.0,
            "top_cancer": str(studies.iloc[0]["cancer"]),
            "top_cancer_freq_pct": float(studies.iloc[0]["freq_pct"]),
            "top_protein_change": (
                str(protein_counts.iloc[0]["proteinChange"]) if not protein_counts.empty else None
            ),
            "top_protein_change_count": (
                int(protein_counts.iloc[0]["count"]) if not protein_counts.empty else 0
            ),
        }
    )
    return result
