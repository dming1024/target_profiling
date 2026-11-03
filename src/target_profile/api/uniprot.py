from typing import Any

from target_profile.api.cache import CachedFetcher

UNIPROT_URL = "https://rest.uniprot.org/uniprotkb/{acc}.json"


def uniprot_record(
    acc: str | None, fetcher: CachedFetcher, refresh: bool = False
) -> dict[str, Any] | None:
    if not acc:
        return None
    return fetcher.request_json(
        f"uniprot_{acc}",
        "GET",
        UNIPROT_URL.format(acc=acc),
        gene="_global",
        refresh=refresh,
    )
