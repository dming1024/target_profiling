# src/target_profile/analysis/safety.py
from collections import Counter

import pandas as pd

from target_profile.analysis.expression import _read, _tau
from target_profile.api.cache import CachedFetcher
from target_profile.api.opentargets import target_safety
from target_profile.config import Settings
from target_profile.models import GeneContext, ModuleResult


def analyze_safety(
    ctx: GeneContext,
    settings: Settings,
    offline: bool = True,
    fetcher: CachedFetcher | None = None,
) -> ModuleResult:
    result = ModuleResult(name="safety")
    fetcher = fetcher or CachedFetcher(settings.data_root / "cache", offline=offline)

    details = None
    try:
        details = target_safety(ctx.ensembl_id, fetcher)
    except Exception as exc:
        result.caveats.append(f"safety: Open Targets unavailable ({exc})")

    if details:
        liabilities = details.get("safetyLiabilities") or []
        result.facts["n_safety_liabilities"] = int(len(liabilities))
        if liabilities:
            rows = [
                {
                    "event": item.get("event") or item.get("eventId"),
                    "datasource": item.get("datasource"),
                    "effect": ", ".join(
                        sorted(
                            {
                                effect.get("direction")
                                for effect in item.get("effects") or []
                                if effect.get("direction")
                            }
                        )
                    ),
                    "studies": ", ".join(
                        sorted(
                            {
                                study.get("name")
                                for study in item.get("studies") or []
                                if study.get("name")
                            }
                        )[:3]
                    ),
                }
                for item in liabilities
            ]
            result.tables["liabilities"] = pd.DataFrame(rows)
            result.facts["safety_datasources"] = ", ".join(
                sorted(
                    {
                        item.get("datasource")
                        for item in liabilities
                        if item.get("datasource")
                    }
                )
            )
            result.facts["top_safety_event"] = str(rows[0]["event"])

        mouse = details.get("mousePhenotypes") or []
        if mouse:
            labels: set[str] = set()
            class_counts: Counter[str] = Counter()
            for item in mouse:
                if item.get("modelPhenotypeLabel"):
                    labels.add(item["modelPhenotypeLabel"])
                for phenotype_class in item.get("modelPhenotypeClasses") or []:
                    if phenotype_class.get("label"):
                        class_counts[phenotype_class["label"]] += 1
            if class_counts:
                class_frame = pd.DataFrame(
                    sorted(class_counts.items(), key=lambda item: (-item[1], item[0])),
                    columns=["phenotype_class", "models"],
                )
                result.tables["mouse_phenotypes"] = class_frame
                result.facts["n_mouse_phenotypes"] = int(len(labels))
                result.facts["top_mouse_phenotype_class"] = str(
                    class_frame.iloc[0]["phenotype_class"]
                )
                result.facts["mouse_phenotype_examples"] = "; ".join(
                    sorted(labels)[:3]
                )

        constraint = details.get("geneticConstraint") or []
        lof = next(
            (item for item in constraint if item.get("constraintType") == "lof"), None
        )
        if lof:
            loeuf = float(lof.get("oeUpper") or 0)
            result.facts["loeuf"] = round(loeuf, 4)
            result.facts["constrained"] = (
                "Yes" if loeuf < settings.thresholds.loeuf_constrained else "No"
            )

        if details.get("isEssential") is not None:
            result.facts["common_essential"] = (
                "Yes" if details["isEssential"] else "No"
            )

        paralogues = [
            item
            for item in details.get("homologues") or []
            if "paralog" in (item.get("homologyType") or "")
            and item.get("targetGeneId") != ctx.ensembl_id
        ]
        if paralogues:
            result.facts["n_paralogues"] = int(len(paralogues))
            best = max(
                paralogues,
                key=lambda item: float(item.get("queryPercentageIdentity") or 0),
            )
            result.facts["top_paralogue_identity"] = round(
                float(best.get("queryPercentageIdentity") or 0), 1
            )

    gtex = _read(settings.data_root / "parquet" / "gtex.parquet")
    sub = gtex[gtex["Gene"] == ctx.symbol]
    if not sub.empty:
        tissue = sub.groupby("Tissue")["Expression"].median()
        result.tables["expression_breadth"] = (
            tissue.sort_values(ascending=False)
            .rename_axis("tissue")
            .reset_index(name="median")
        )
        result.facts["n_tissues_expressed"] = int(
            (tissue >= settings.thresholds.expression_breadth_tpm).sum()
        )
        result.facts["tissue_count"] = int(len(tissue))
        result.facts["expression_tau"] = round(_tau(tissue), 3)

    result.caveats.append("safety: 无安全记录不代表安全；安全性维度数据天然稀疏")

    if not result.tables:
        return result.degrade("safety: no safety data")
    return result
