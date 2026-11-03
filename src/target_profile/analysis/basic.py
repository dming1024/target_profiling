from target_profile.api.alphafold import alphafold_prediction
from target_profile.api.cache import CachedFetcher
from target_profile.api.opentargets import target_basic
from target_profile.api.uniprot import uniprot_record
from target_profile.config import Settings
from target_profile.models import GeneContext, ModuleResult


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
    if prediction and prediction.get("globalMetricValue") is not None:
        result.facts["alphafold_mean_plddt"] = round(
            float(prediction["globalMetricValue"]), 1
        )

    if not details and not record:
        return result.degrade("basic: target metadata unavailable")
    return result
