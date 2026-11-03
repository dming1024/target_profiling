from typing import Any

from target_profile.api.cache import CachedFetcher

OT_URL = "https://api.platform.opentargets.org/api/v4/graphql"

SEARCH_QUERY = """
query Search($q: String!) {
  search(queryString: $q, entityNames: ["target"]) {
    hits { id name entity }
  }
}
"""

TARGET_QUERY = """
query Target($id: String!) {
  target(ensemblId: $id) {
    id
    approvedSymbol
    biotype
    genomicLocation { chromosome start end }
    proteinIds { id source }
    dbXrefs { id source }
  }
}
"""


def search_targets(query: str, fetcher: CachedFetcher) -> list[dict[str, Any]]:
    payload = fetcher.request_json(
        f"opentargets_search_{query}",
        "POST",
        OT_URL,
        gene="_global",
        json_body={"query": SEARCH_QUERY, "variables": {"q": query}},
    )
    return payload.get("data", {}).get("search", {}).get("hits", [])


BASIC_QUERY = """
query Basic($id: String!) {
  target(ensemblId: $id) {
    id
    approvedSymbol
    approvedName
    biotype
    functionDescriptions
    targetClass { label level }
    subcellularLocations { location termSL labelSL }
    proteinIds { id source }
    synonyms { label source }
  }
}
"""

PATHWAY_QUERY = """
query Pathways($id: String!) {
  target(ensemblId: $id) {
    id
    pathways { pathwayId pathway topLevelTerm }
    geneOntology { aspect evidence term { id label } }
  }
}
"""


def _target_query(
    ensembl_id: str,
    query: str,
    name: str,
    fetcher: CachedFetcher,
    refresh: bool = False,
) -> dict[str, Any] | None:
    payload = fetcher.request_json(
        name,
        "POST",
        OT_URL,
        gene=ensembl_id,
        json_body={"query": query, "variables": {"id": ensembl_id}},
        refresh=refresh,
    )
    return payload.get("data", {}).get("target")


def target_details(
    ensembl_id: str, fetcher: CachedFetcher, refresh: bool = False
) -> dict[str, Any] | None:
    payload = fetcher.request_json(
        "opentargets_target",
        "POST",
        OT_URL,
        gene=ensembl_id,
        json_body={"query": TARGET_QUERY, "variables": {"id": ensembl_id}},
        refresh=refresh,
    )
    return payload.get("data", {}).get("target")


def target_basic(
    ensembl_id: str, fetcher: CachedFetcher, refresh: bool = False
) -> dict[str, Any] | None:
    return _target_query(ensembl_id, BASIC_QUERY, "opentargets_basic", fetcher, refresh)


def target_pathways(
    ensembl_id: str, fetcher: CachedFetcher, refresh: bool = False
) -> dict[str, Any] | None:
    return _target_query(ensembl_id, PATHWAY_QUERY, "opentargets_pathways", fetcher, refresh)


DISEASE_QUERY = """
query Disease($id: String!) {
  target(ensemblId: $id) {
    id
    associatedDiseases(page: {index: 0, size: 20}) {
      count
      rows { disease { id name } score datatypeScores { id score } }
    }
    geneticConstraint { constraintType score oe oeLower oeUpper upperRank }
  }
}
"""

TRACTABILITY_QUERY = """
query Tractability($id: String!) {
  target(ensemblId: $id) {
    id
    tractability { modality label value }
    chemicalProbes { id drugId mechanismOfAction isHighQuality }
    drugAndClinicalCandidates {
      count
      rows { id maxClinicalStage drug { id name } diseases { disease { id name } } }
    }
  }
}
"""

SAFETY_QUERY = """
query Safety($id: String!) {
  target(ensemblId: $id) {
    id
    safetyLiabilities { event eventId datasource effects { direction dosing } studies { name type } }
    mousePhenotypes { modelPhenotypeLabel modelPhenotypeClasses { id label } }
    geneticConstraint { constraintType score oeUpper }
    isEssential
    homologues { speciesName homologyType targetGeneId queryPercentageIdentity targetPercentageIdentity }
  }
}
"""


def target_disease(
    ensembl_id: str, fetcher: CachedFetcher, refresh: bool = False
) -> dict[str, Any] | None:
    return _target_query(ensembl_id, DISEASE_QUERY, "opentargets_disease", fetcher, refresh)


def target_tractability(
    ensembl_id: str, fetcher: CachedFetcher, refresh: bool = False
) -> dict[str, Any] | None:
    return _target_query(
        ensembl_id, TRACTABILITY_QUERY, "opentargets_tractability", fetcher, refresh
    )


def target_safety(
    ensembl_id: str, fetcher: CachedFetcher, refresh: bool = False
) -> dict[str, Any] | None:
    return _target_query(ensembl_id, SAFETY_QUERY, "opentargets_safety", fetcher, refresh)


CANCER_QUERY = """
query Cancer($id: String!) {
  target(ensemblId: $id) {
    id
    hallmarks {
      attributes { name description }
      cancerHallmarks { label impact description pmid }
    }
  }
}
"""


def target_cancer(
    ensembl_id: str, fetcher: CachedFetcher, refresh: bool = False
) -> dict[str, Any] | None:
    return _target_query(ensembl_id, CANCER_QUERY, "opentargets_cancer", fetcher, refresh)
