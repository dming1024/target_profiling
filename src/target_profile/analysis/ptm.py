import pandas as pd

from target_profile.api.cache import CachedFetcher
from target_profile.api.uniprot import uniprot_record
from target_profile.config import Settings
from target_profile.models import GeneContext, ModuleResult

PTM_TYPES = (
    "Modified residue",
    "Lipidation",
    "Glycosylation",
    "Disulfide bond",
    "Cross-link",
)
REGION_TYPES = (
    "Domain",
    "Region",
    "Zinc finger",
    "Repeat",
    "Coiled coil",
    "Motif",
)


def analyze_ptm(
    ctx: GeneContext,
    settings: Settings,
    offline: bool = True,
    fetcher: CachedFetcher | None = None,
) -> ModuleResult:
    result = ModuleResult(name="ptm")
    if not ctx.uniprot_id:
        return result.degrade("ptm: UniProt ID unavailable")
    fetcher = fetcher or CachedFetcher(settings.data_root / "cache", offline=offline)

    try:
        record = uniprot_record(ctx.uniprot_id, fetcher)
    except Exception as exc:
        return result.degrade(f"ptm: UniProt unavailable ({exc})")
    if not record:
        return result.degrade("ptm: UniProt record unavailable")

    sequence_length = (record.get("sequence") or {}).get("length")
    if sequence_length:
        result.facts["sequence_length"] = int(sequence_length)

    sites: list[dict] = []
    regions: list[dict] = []
    for feature in record.get("features") or []:
        feature_type = feature.get("type")
        location = feature.get("location") or {}
        start = (location.get("start") or {}).get("value")
        end = (location.get("end") or {}).get("value")
        if start is None:
            continue
        if feature_type in PTM_TYPES:
            sites.append(
                {
                    "type": feature_type,
                    "position": int(start),
                    "end": int(end or start),
                    "description": feature.get("description") or "",
                }
            )
        elif feature_type in REGION_TYPES:
            regions.append(
                {
                    "type": feature_type,
                    "name": feature.get("description") or feature_type,
                    "start": int(start),
                    "end": int(end or start),
                }
            )

    if sites:
        site_frame = pd.DataFrame(sites).sort_values(["position", "type"])
        result.tables["ptm_sites"] = site_frame
        counts = (
            site_frame["type"]
            .value_counts()
            .rename_axis("type")
            .reset_index(name="count")
        )
        result.tables["ptm_types"] = counts
        result.facts["n_ptm_sites"] = int(len(site_frame))
        result.facts["ptm_types"] = ", ".join(
            f"{row.type} {row.count}" for row in counts.itertuples()
        )
        result.facts["top_ptm_type"] = str(counts.iloc[0]["type"])

    if regions:
        region_frame = pd.DataFrame(regions).sort_values("start")
        result.tables["domains"] = region_frame
        result.facts["n_domains"] = int(len(region_frame))
        result.facts["domain_summary"] = "; ".join(
            f"{row.name} ({row.start}-{row.end})"
            for row in region_frame.head(3).itertuples()
        )

    if not sites and not regions:
        return result.degrade("ptm: no curated PTM or domain features")
    return result
