from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class GeneContext:
    symbol: str
    ensembl_id: str
    entrez_id: str | None = None
    uniprot_id: str | None = None
    chromosome: str | None = None
    start: int | None = None
    end: int | None = None
    biotype: str | None = None
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChartSpec:
    """A JSON-serialisable ECharts option produced by figures.chart_specs."""

    id: str
    title: str
    subtitle: str = ""
    option: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModuleResult:
    name: str
    status: Literal["ok", "no_data"] = "ok"
    facts: dict[str, Any] = field(default_factory=dict)
    tables: dict[str, Any] = field(default_factory=dict)
    caveats: list[str] = field(default_factory=list)
    charts: list[ChartSpec] = field(default_factory=list)
    narrative: str | None = None
    label_cards: list[dict[str, Any]] = field(default_factory=list)

    def degrade(self, reason: str) -> "ModuleResult":
        self.status = "no_data"
        self.caveats.append(reason)
        return self
