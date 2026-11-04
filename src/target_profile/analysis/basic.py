import pandas as pd

from target_profile.api.alphafold import alphafold_confidence, alphafold_prediction
from target_profile.api.cache import CachedFetcher
from target_profile.api.opentargets import target_basic
from target_profile.api.uniprot import uniprot_record
from target_profile.config import Settings
from target_profile.models import GeneContext, ModuleResult

CONFIDENCE_CATEGORIES = (
    ("Very high (≥90)", "fractionPlddtVeryHigh", "A", "alphafold_very_high_pct"),
    ("Confident (70–90)", "fractionPlddtConfident", "B", "alphafold_confident_pct"),
    ("Low (50–70)", "fractionPlddtLow", "C", "alphafold_low_pct"),
    ("Very low (<50)", "fractionPlddtVeryLow", "D", "alphafold_very_low_pct"),
)


def _coverage(
    prediction: dict, protein_length: int | None
) -> tuple[str | None, float | None]:
    start = prediction.get("uniprotStart") or prediction.get("sequenceStart")
    end = prediction.get("uniprotEnd") or prediction.get("sequenceEnd")
    if start is None or end is None:
        return None, None
    span = f"{start}–{end} aa"
    if not protein_length:
        return span, None
    pct = (int(end) - int(start) + 1) / int(protein_length) * 100
    return f"{span} ({pct:.0f}%)", pct


def _confidence_tables(
    prediction: dict, confidence: dict | None
) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    counts: dict[str, int] = {}
    if confidence:
        for category in confidence.get("confidenceCategory") or []:
            counts[str(category)] = counts.get(str(category), 0) + 1

    rows = []
    for label, fraction_key, code, _ in CONFIDENCE_CATEGORIES:
        fraction = prediction.get(fraction_key)
        if fraction is None:
            continue
        rows.append(
            {
                "category": label,
                "residues": counts.get(code),
                "pct": round(float(fraction) * 100, 1),
            }
        )
    categories = pd.DataFrame(rows) if rows else None

    plddt = None
    if confidence:
        residues = confidence.get("residueNumber") or []
        scores = confidence.get("confidenceScore") or []
        cats = confidence.get("confidenceCategory") or []
        if residues and len(residues) == len(scores):
            plddt = pd.DataFrame(
                {
                    "residue": [int(value) for value in residues],
                    "plddt": [float(value) for value in scores],
                    "category": list(cats[: len(residues)]) if cats else [""] * len(residues),
                }
            )
    return categories, plddt


def _uniprot_function(record: dict) -> str | None:
    for comment in record.get("comments") or []:
        if comment.get("commentType") != "FUNCTION":
            continue
        texts = comment.get("texts") or []
        if texts and texts[0].get("value"):
            return texts[0]["value"]
    return None


def analyze_basic(
    ctx: GeneContext,
    settings: Settings,
    offline: bool = True,
    fetcher: CachedFetcher | None = None,
) -> ModuleResult:
    result = ModuleResult(name="basic")
    fetcher = fetcher or CachedFetcher(settings.data_root / "cache", offline=offline)
    result.facts.update({"symbol": ctx.symbol, "ensembl_id": ctx.ensembl_id})
    if ctx.biotype:
        result.facts["biotype"] = ctx.biotype

    details = None
    try:
        details = target_basic(ctx.ensembl_id, fetcher)
    except Exception as exc:
        result.caveats.append(f"basic: Open Targets unavailable ({exc})")

    if details:
        if details.get("approvedName"):
            result.facts["approved_name"] = details["approvedName"]
        classes = [c["label"] for c in details.get("targetClass") or [] if c.get("label")]
        if classes:
            result.facts["target_class"] = " / ".join(classes)
        locations = [
            loc["location"]
            for loc in details.get("subcellularLocations") or []
            if loc.get("location")
        ]
        if locations:
            result.facts["subcellular_locations"] = "; ".join(dict.fromkeys(locations))
        descriptions = details.get("functionDescriptions") or []
        if descriptions:
            result.facts["function_summary"] = descriptions[0]
        synonyms = sorted(
            {syn["label"] for syn in details.get("synonyms") or [] if syn.get("label")}
        )
        if synonyms:
            result.facts["synonym_count"] = len(synonyms)

    record = None
    try:
        record = uniprot_record(ctx.uniprot_id, fetcher)
    except Exception as exc:
        result.caveats.append(f"basic: UniProt unavailable ({exc})")

    if record:
        sequence = record.get("sequence") or {}
        if sequence.get("length"):
            result.facts["protein_length"] = int(sequence["length"])
        protein_name = (
            ((record.get("proteinDescription") or {}).get("recommendedName") or {})
            .get("fullName", {})
            .get("value")
        )
        if protein_name:
            result.facts["protein_name"] = protein_name
        if not result.facts.get("function_summary"):
            function = _uniprot_function(record)
            if function:
                result.facts["function_summary"] = function

    try:
        prediction = alphafold_prediction(ctx.uniprot_id, fetcher)
    except Exception:
        prediction = None
    result.facts["alphafold_available"] = "Yes" if prediction else "No"
    if prediction:
        if prediction.get("globalMetricValue") is not None:
            result.facts["alphafold_mean_plddt"] = round(
                float(prediction["globalMetricValue"]), 1
            )
        if prediction.get("entryId"):
            result.facts["alphafold_entry_id"] = prediction["entryId"]
        if prediction.get("latestVersion") is not None:
            result.facts["alphafold_model_version"] = f"v{prediction['latestVersion']}"

        coverage_text, coverage_pct = _coverage(
            prediction, result.facts.get("protein_length")
        )
        if coverage_text:
            result.facts["alphafold_coverage"] = coverage_text

        for _, fraction_key, _, fact_key in CONFIDENCE_CATEGORIES:
            fraction = prediction.get(fraction_key)
            if fraction is not None:
                result.facts[fact_key] = round(float(fraction) * 100, 1)

        confidence = None
        try:
            confidence = alphafold_confidence(ctx.uniprot_id, prediction, fetcher)
        except Exception:
            confidence = None

        categories, plddt = _confidence_tables(prediction, confidence)
        if categories is not None and not categories.empty:
            result.tables["alphafold_categories"] = categories
        if plddt is not None and not plddt.empty:
            result.tables["alphafold_plddt"] = plddt

        if confidence is None:
            result.caveats.append(
                "未找到逐残基置信度缓存，本面板仅展示分段占比；运行 fetch 可补齐。"
            )
        result.caveats.append(
            "AlphaFold pLDDT 是单模型逐残基置信度，不代表实验结构精度或残基功能重要性；"
            "低 pLDDT 不等于无序。"
        )
        if coverage_pct is not None and coverage_pct < 95:
            result.caveats.append(
                f"AlphaFold 模型仅覆盖 UniProt 序列的 {coverage_pct:.0f}%，"
                "未覆盖区域没有结构置信度。"
            )

        links = [
            {
                "label": "AlphaFold DB",
                "url": f"https://alphafold.ebi.ac.uk/entry/{ctx.uniprot_id}",
            }
        ]
        for label, key in (("PDB", "pdbUrl"), ("CIF", "cifUrl")):
            url = prediction.get(key)
            if url:
                links.append({"label": label, "url": url})
        result.links = links

    if not details and not record:
        return result.degrade("basic: target metadata unavailable")
    return result
