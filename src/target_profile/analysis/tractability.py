# src/target_profile/analysis/tractability.py
import pandas as pd

from target_profile.api.cache import CachedFetcher
from target_profile.api.opentargets import target_tractability
from target_profile.config import Settings
from target_profile.models import GeneContext, ModuleResult

MODALITY_LABELS = {
    "SM": "Small molecule",
    "AB": "Antibody",
    "PR": "PROTAC",
    "OC": "Other modality",
}
STAGE_LABELS = {
    "APPROVAL": "Approved",
    "PHASE_4": "Phase 4",
    "PHASE_3": "Phase 3",
    "PHASE_2": "Phase 2",
    "PHASE_1": "Phase 1",
    "PRECLINICAL": "Preclinical",
    "UNKNOWN": "Unknown",
}
STAGE_ORDER = {label: index for index, label in enumerate(STAGE_LABELS.values())}


def analyze_tractability(
    ctx: GeneContext,
    settings: Settings,
    offline: bool = True,
    fetcher: CachedFetcher | None = None,
) -> ModuleResult:
    result = ModuleResult(name="tractability")
    fetcher = fetcher or CachedFetcher(settings.data_root / "cache", offline=offline)

    details = None
    try:
        details = target_tractability(ctx.ensembl_id, fetcher)
    except Exception as exc:
        result.caveats.append(f"tractability: Open Targets unavailable ({exc})")

    if details:
        rows = details.get("tractability") or []
        if rows:
            frame = pd.DataFrame(
                [
                    {
                        "modality": MODALITY_LABELS.get(row["modality"], row["modality"]),
                        "bucket": row["label"],
                        "available": bool(row["value"]),
                    }
                    for row in rows
                ]
            )
            result.tables["tractability"] = frame
            available = frame[frame["available"]]
            approved = sorted(
                set(available.loc[available["bucket"] == "Approved Drug", "modality"])
            )
            advanced = sorted(
                set(
                    available.loc[
                        available["bucket"] == "Advanced Clinical", "modality"
                    ]
                )
            )
            result.facts.update(
                {
                    "tractable": "Yes" if approved or advanced else "No",
                    "approved_modalities": ", ".join(approved) or "None",
                    "advanced_clinical_modalities": ", ".join(advanced) or "None",
                }
            )

        probes = details.get("chemicalProbes") or []
        if probes:
            probe_frame = pd.DataFrame(
                [
                    {
                        "probe": probe.get("id"),
                        "drug_id": probe.get("drugId"),
                        "mechanism": ", ".join(probe.get("mechanismOfAction") or []),
                        "high_quality": bool(probe.get("isHighQuality")),
                    }
                    for probe in probes
                ]
            ).sort_values(
                ["high_quality", "probe"], ascending=[False, True]
            ).reset_index(drop=True)
            result.tables["probes"] = probe_frame
            result.facts.update(
                {
                    "n_probes": int(len(probe_frame)),
                    "n_high_quality_probes": int(probe_frame["high_quality"].sum()),
                    "top_probe": str(probe_frame.iloc[0]["probe"]),
                }
            )

        candidates = details.get("drugAndClinicalCandidates") or {}
        drug_rows = candidates.get("rows") or []
        if drug_rows:
            records = []
            for row in drug_rows:
                drug = row.get("drug") or {}
                diseases = sorted(
                    {
                        (item.get("disease") or {}).get("name")
                        for item in row.get("diseases") or []
                        if (item.get("disease") or {}).get("name")
                    }
                )
                records.append(
                    {
                        "drug": drug.get("name") or row.get("id"),
                        "drug_id": drug.get("id"),
                        "stage": STAGE_LABELS.get(
                            row.get("maxClinicalStage"), row.get("maxClinicalStage")
                        ),
                        "diseases": ", ".join(diseases[:3]),
                    }
                )
            drug_frame = pd.DataFrame(records)
            drug_frame["stage_order"] = drug_frame["stage"].map(STAGE_ORDER).fillna(99)
            drug_frame = drug_frame.sort_values(
                ["stage_order", "drug"]
            ).drop(columns="stage_order").reset_index(drop=True)
            result.tables["drugs"] = drug_frame
            result.tables["drug_stages"] = (
                drug_frame["stage"]
                .value_counts()
                .rename_axis("stage")
                .reset_index(name="count")
            )
            result.facts.update(
                {
                    "n_drugs": int(len(drug_frame)),
                    "max_clinical_stage": str(drug_frame.iloc[0]["stage"]),
                    "approved_drug_count": int(
                        (drug_frame["stage"] == "Approved").sum()
                    ),
                }
            )

    if not result.tables:
        return result.degrade("tractability: no tractability data")
    return result
