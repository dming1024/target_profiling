import difflib

import pandas as pd
import pyarrow.parquet as pq

from target_profile.api.cache import CachedFetcher
from target_profile.api.opentargets import search_targets, target_details
from target_profile.config import Settings
from target_profile.errors import DataMissing, GeneNotFound
from target_profile.models import GeneContext

UNIPROT_URL = "https://rest.uniprot.org/uniprotkb/{acc}.json"


def _gene_info(settings: Settings) -> pd.DataFrame:
    path = settings.data_root / "parquet" / "gene_info.parquet"
    if not path.exists():
        raise DataMissing(f"missing local data: {path}; run `target-profile data`")
    return pd.read_parquet(path)


def _entrez_from_depmap(settings: Settings, symbol: str) -> str | None:
    path = settings.data_root / "parquet" / "depmap_gene_effect.parquet"
    if not path.exists():
        return None
    names = pq.read_schema(path).names
    for column in names:
        if column.startswith(f"{symbol} (") and column.endswith(")"):
            return column[column.rfind("(") + 1 : -1]
    return None


def _row_to_context(
    row: pd.Series, settings: Settings, fetcher: CachedFetcher
) -> GeneContext:
    symbol = str(row["gene_name"])
    ensembl = str(row["gene_id"])
    uniprot = None
    try:
        details = target_details(ensembl, fetcher)
        if details:
            for protein in details.get("proteinIds") or []:
                if protein.get("source") == "uniprot_swissprot":
                    uniprot = protein.get("id")
                    break
    except Exception:
        pass
    return GeneContext(
        symbol=symbol,
        ensembl_id=ensembl,
        entrez_id=_entrez_from_depmap(settings, symbol),
        uniprot_id=uniprot,
        chromosome=str(row["chr"]),
        start=int(row["gene_start"]),
        end=int(row["gene_end"]),
        biotype=str(row["gene_type"]),
    )


def resolve_gene(
    query: str,
    settings: Settings,
    offline: bool = False,
    fetcher: CachedFetcher | None = None,
) -> GeneContext:
    fetcher = fetcher or CachedFetcher(settings.data_root / "cache", offline=offline)
    info = _gene_info(settings)
    q = query.strip()

    row = None
    if q.upper().startswith("ENSG"):
        match = info[info["gene_id"] == q]
    else:
        match = info[info["gene_name"] == q]
        if match.empty and 6 <= len(q) <= 10 and q.isalnum() and q.upper() == q:
            try:
                payload = fetcher.request_json(
                    f"uniprot_{q}",
                    "GET",
                    UNIPROT_URL.format(acc=q),
                    gene="_global",
                )
                symbol = payload["genes"][0]["geneName"]["value"]
                match = info[info["gene_name"] == symbol]
            except Exception:
                match = info.iloc[0:0]
    if not match.empty:
        row = match.iloc[0]

    if row is None:
        try:
            hits = search_targets(q, fetcher)
        except Exception:
            hits = []
        if hits:
            match = info[info["gene_id"] == hits[0]["id"]]
            if not match.empty:
                row = match.iloc[0]

    if row is None:
        candidates = difflib.get_close_matches(
            q, info["gene_name"].dropna().tolist(), n=5
        )
        hint = f"; did you mean: {', '.join(candidates)}" if candidates else ""
        raise GeneNotFound(f"cannot resolve gene '{query}'{hint}")

    return _row_to_context(row, settings, fetcher)
