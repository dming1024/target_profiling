# src/target_profile/analysis/disease.py
from collections import Counter

import pandas as pd

from target_profile.api.cache import CachedFetcher
from target_profile.api.clinvar import fetch_clinvar
from target_profile.api.opentargets import target_disease
from target_profile.config import Settings
from target_profile.models import GeneContext, ModuleResult

CONSTRAINT_LABELS = {"lof": "LoF", "mis": "Missense", "syn": "Synonymous"}
DATASOURCE_LABELS = {
    "genetic_association": "Genetic association",
    "genetic_literature": "Genetic literature",
    "somatic_mutation": "Somatic mutation",
    "affected_pathway": "Affected pathway",
    "animal_model": "Animal model",
    "literature": "Literature",
    "clinical": "Clinical",
    "rna_expression": "RNA expression",
    "expression_atlas": "Expression atlas",
    "known_drug": "Known drug",
    "uniprot_variants": "UniProt variants",
    "europepmc": "Europe PMC",
    "phenotype": "Phenotype",
}


def _is_pathogenic(classification: str) -> bool:
    text = classification.lower()
    return (
        "pathogenic" in text
        and "conflict" not in text
        and "benign" not in text
    )


def analyze_disease(
    ctx: GeneContext,
    settings: Settings,
    offline: bool = True,
    fetcher: CachedFetcher | None = None,
) -> ModuleResult:
    result = ModuleResult(name="disease")
    fetcher = fetcher or CachedFetcher(settings.data_root / "cache", offline=offline)

    details = None
    try:
        details = target_disease(ctx.ensembl_id, fetcher)
    except Exception as exc:
        result.caveats.append(f"disease: Open Targets unavailable ({exc})")

    if details:
        associated = details.get("associatedDiseases") or {}
        rows = associated.get("rows") or []
        if rows:
            frame = pd.DataFrame(
                [
                    {
                        "disease_id": row["disease"]["id"],
                        "disease": row["disease"]["name"],
                        "score": round(float(row["score"]), 3),
                        "datasources": len(row.get("datatypeScores") or []),
                    }
                    for row in rows
                    if row.get("disease")
                ]
            )
            if not frame.empty:
                frame = frame.sort_values("score", ascending=False)
                result.tables["diseases"] = frame.reset_index(drop=True)
                result.facts.update(
                    {
                        "disease_count": int(associated.get("count") or 0),
                        "top_disease": str(frame.iloc[0]["disease"]),
                        "top_disease_score": float(frame.iloc[0]["score"]),
                        "top_diseases": ", ".join(frame.head(3)["disease"].astype(str)),
                    }
                )

            counts: Counter[str] = Counter()
            for row in rows:
                for component in row.get("datatypeScores") or []:
                    if float(component.get("score") or 0) > 0:
                        counts[component["id"]] += 1
            if counts:
                datasources = pd.DataFrame(
                    sorted(counts.items(), key=lambda item: (-item[1], item[0])),
                    columns=["datasource", "diseases"],
                )
                datasources["datasource"] = datasources["datasource"].map(
                    lambda value: DATASOURCE_LABELS.get(value, value)
                )
                result.tables["datasources"] = datasources

        constraint = details.get("geneticConstraint") or []
        lof = next(
            (item for item in constraint if item.get("constraintType") == "lof"), None
        )
        if lof:
            loeuf = float(lof.get("oeUpper") or 0)
            result.facts.update(
                {
                    "pli": round(float(lof.get("score") or 0), 4),
                    "loeuf": round(loeuf, 4),
                    "lof_oe": round(float(lof.get("oe") or 0), 4),
                    "constrained": (
                        "Yes"
                        if loeuf < settings.thresholds.loeuf_constrained
                        else "No"
                    ),
                }
            )
            result.tables["constraint"] = pd.DataFrame(
                [
                    {
                        "type": CONSTRAINT_LABELS.get(
                            item.get("constraintType"), item.get("constraintType")
                        ),
                        "score": item.get("score"),
                        "oe": item.get("oe"),
                        "oe_upper": item.get("oeUpper"),
                    }
                    for item in constraint
                ]
            )

    clinvar = None
    try:
        clinvar = fetch_clinvar(ctx.symbol, fetcher)
    except Exception as exc:
        result.caveats.append(f"disease: ClinVar unavailable ({exc})")

    if clinvar:
        result.facts["clinvar_total"] = clinvar["total"]
        result.facts["clinvar_pathogenic_submissions"] = clinvar[
            "pathogenic_submissions"
        ]
        records = clinvar.get("records") or []
        strong = [record for record in records if _is_pathogenic(record["classification"])]
        chosen = strong or records
        if chosen:
            result.tables["clinvar"] = pd.DataFrame(
                [
                    {
                        "variant": record["title"],
                        "classification": record["classification"],
                        "review": record["review_status"],
                    }
                    for record in chosen[:10]
                ]
            )
            result.facts["clinvar_top_variant"] = chosen[0]["title"]
        if clinvar["pathogenic_submissions"] > len(strong):
            result.caveats.append(
                "disease: ClinVar 计数含存在致病提交的记录，聚合分类可能为 VUS 或冲突"
            )

    if not result.tables:
        return result.degrade("disease: no disease association data")
    return result
