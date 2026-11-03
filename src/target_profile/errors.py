class TargetProfileError(Exception):
    """Base error for target profiling."""


class GeneNotFound(TargetProfileError):
    """Gene identifier could not be resolved."""


class DataMissing(TargetProfileError):
    """Required local data file is missing or unreadable."""


class OfflineCacheMiss(TargetProfileError):
    """Offline mode requested but the API response is not cached."""
