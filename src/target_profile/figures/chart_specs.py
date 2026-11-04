"""Build JSON-serialisable ECharts options from ModuleResult tables/facts."""
from __future__ import annotations

import numpy as np
import pandas as pd

from target_profile.models import ChartSpec, ModuleResult

PALETTE = ["#55d6be", "#6ea8fe", "#f0b053", "#f27d9a", "#75d88a", "#a78bfa"]
GRID = {"left": 8, "right": 64, "top": 20, "bottom": 12, "containLabel": True}


def empty_option(text: str = "No data available") -> dict:
    return {
        "graphic": {
            "type": "text",
            "left": "center",
            "top": "middle",
            "style": {"text": text, "fill": "#8b9bb0", "fontSize": 14},
        },
        "xAxis": {"show": False},
        "yAxis": {"show": False},
        "series": [],
    }


def _barh(categories, values, *, color=PALETTE[0], name="", x_name="", suffix=""):
    axis_label = {"color": "#8b9bb0"}
    if suffix:
        axis_label["formatter"] = "{value}" + suffix
    return {
        "grid": dict(GRID),
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "xAxis": {
            "type": "value",
            "name": x_name,
            "nameTextStyle": {"color": "#8b9bb0"},
            "axisLabel": axis_label,
            "splitLine": {"lineStyle": {"color": "rgba(120,160,200,.12)"}},
        },
        "yAxis": {
            "type": "category",
            "inverse": True,
            "data": list(categories),
            "axisLabel": {"color": "#c9d6e5", "width": 180, "overflow": "truncate"},
            "axisLine": {"lineStyle": {"color": "rgba(120,160,200,.2)"}},
            "splitLine": {"show": False},
        },
        "series": [
            {
                "type": "bar",
                "name": name or x_name,
                "data": list(values),
                "barMaxWidth": 18,
                "itemStyle": {"color": color, "borderRadius": [0, 4, 4, 0]},
            }
        ],
    }


def _bar(categories, values, *, color=PALETTE[1], name="", x_name="", y_name=""):
    return {
        "grid": dict(GRID),
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "xAxis": {
            "type": "category",
            "data": list(categories),
            "axisLabel": {
                "color": "#8b9bb0",
                "width": 96,
                "overflow": "truncate",
                "interval": 0,
                "rotate": 30,
            },
            "axisLine": {"lineStyle": {"color": "rgba(120,160,200,.25)"}},
        },
        "yAxis": {
            "type": "value",
            "name": y_name,
            "nameTextStyle": {"color": "#8b9bb0"},
            "axisLabel": {"color": "#8b9bb0"},
            "splitLine": {"lineStyle": {"color": "rgba(120,160,200,.12)"}},
        },
        "series": [
            {
                "type": "bar",
                "name": name or x_name,
                "data": list(values),
                "barMaxWidth": 26,
                "itemStyle": {"color": color, "borderRadius": [4, 4, 0, 0]},
            }
        ],
    }


def _num(value, default=0.0):
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def build_expression(result: ModuleResult) -> list[ChartSpec]:
    gtex = result.tables.get("gtex")
    if isinstance(gtex, pd.DataFrame) and not gtex.empty:
        top = gtex.dropna(subset=["Tissue", "median"]).head(20)
        option = _barh(
            [str(value) for value in top["Tissue"]],
            [round(_num(value), 3) for value in top["median"]],
            x_name="Median TPM",
        )
    else:
        option = empty_option()
    specs = [
        ChartSpec(
            id="expression-gtex",
            title="GTEx tissue expression",
            subtitle="Source: GTEx v8",
            option=option,
        )
    ]

    lineage = result.tables.get("depmap_lineage")
    if isinstance(lineage, pd.DataFrame) and not lineage.empty:
        top = lineage.dropna(subset=["OncotreeLineage", "median"]).head(12)
        option = _barh(
            [str(value) for value in top["OncotreeLineage"]],
            [round(_num(value), 3) for value in top["median"]],
            color=PALETTE[1],
            x_name="Median log2(TPM+1)",
        )
    else:
        option = empty_option()
    specs.append(
        ChartSpec(
            id="expression-depmap",
            title="DepMap cell-line expression",
            subtitle="Source: DepMap / CCLE",
            option=option,
        )
    )
    return specs


def build_mutation(result: ModuleResult) -> list[ChartSpec]:
    cancers = result.tables.get("cancers")
    if isinstance(cancers, pd.DataFrame) and not cancers.empty:
        top = cancers.dropna(subset=["cancer", "freq_pct"]).head(15)
        option = _barh(
            [str(value) for value in top["cancer"]],
            [round(_num(value), 2) for value in top["freq_pct"]],
            x_name="% mutated samples",
            suffix="%",
        )
    else:
        option = empty_option()
    specs = [
        ChartSpec(
            id="mutation-cancers",
            title="TCGA PanCancer mutation frequency",
            subtitle="Source: cBioPortal / TCGA PanCancer Atlas",
            option=option,
        )
    ]

    proteins = result.tables.get("protein_changes")
    if isinstance(proteins, pd.DataFrame) and not proteins.empty:
        top = proteins.dropna(subset=["proteinChange", "count"]).head(10)
        option = _barh(
            [str(value) for value in top["proteinChange"]],
            [int(_num(value)) for value in top["count"]],
            color=PALETTE[2],
            x_name="Mutation count",
        )
    else:
        option = empty_option()
    specs.append(
        ChartSpec(
            id="mutation-proteins",
            title="Top protein changes",
            subtitle="Source: cBioPortal / TCGA PanCancer Atlas",
            option=option,
        )
    )
    return specs


def build_dependency(result: ModuleResult) -> list[ChartSpec]:
    distribution = result.tables.get("distribution")
    subtitle = "Source: DepMap Chronos"
    if isinstance(distribution, pd.DataFrame) and not distribution.empty:
        values = distribution["effect"].dropna().to_numpy(dtype=float)
        counts, edges = np.histogram(values, bins=30)
        if len(edges) >= 2:
            subtitle = (
                f"Source: DepMap Chronos; bin = {edges[1] - edges[0]:.2f} effect units"
            )
        labels = [f"{edges[index]:.2f}" for index in range(len(counts))]
        option = _bar(
            labels,
            [int(value) for value in counts],
            color=PALETTE[1],
            y_name="Cell lines",
        )
    else:
        option = empty_option()
    specs = [
        ChartSpec(
            id="dependency-dist",
            title="DepMap CRISPR gene effect",
            subtitle=subtitle,
            option=option,
        )
    ]

    lineage = result.tables.get("by_lineage")
    if isinstance(lineage, pd.DataFrame) and not lineage.empty:
        top = lineage.dropna(subset=["OncotreeLineage", "median"]).head(12)
        option = _barh(
            [str(value) for value in top["OncotreeLineage"]],
            [round(_num(value), 3) for value in top["median"]],
            color=PALETTE[0],
            x_name="Median effect",
        )
    else:
        option = empty_option()
    specs.append(
        ChartSpec(
            id="dependency-lineage",
            title="Dependency by lineage",
            subtitle="Source: DepMap Chronos",
            option=option,
        )
    )
    return specs


def build_pathway(result: ModuleResult) -> list[ChartSpec]:
    levels = result.tables.get("top_levels")
    if isinstance(levels, pd.DataFrame) and not levels.empty:
        top = levels.dropna(subset=["topLevelTerm", "count"]).head(10)
        option = _barh(
            [str(value) for value in top["topLevelTerm"]],
            [int(_num(value)) for value in top["count"]],
            color=PALETTE[5],
            x_name="Pathway count",
        )
    else:
        option = empty_option()
    specs = [
        ChartSpec(
            id="pathway-levels",
            title="Reactome top-level pathways",
            subtitle="Source: Open Targets / Reactome",
            option=option,
        )
    ]

    partners = result.tables.get("partners")
    if isinstance(partners, pd.DataFrame) and not partners.empty:
        symbol = str(result.facts.get("symbol", "TARGET"))
        frame = partners.dropna(subset=["preferredName_B", "score"]).head(30)
        nodes = [
            {
                "name": symbol,
                "symbolSize": 46,
                "itemStyle": {"color": PALETTE[1]},
                "label": {"fontSize": 12},
            }
        ]
        links = []
        for row in frame.itertuples():
            score = _num(row.score)
            name = str(row.preferredName_B)
            nodes.append(
                {
                    "name": name,
                    "symbolSize": round(14 + score * 26, 1),
                    "itemStyle": {"color": PALETTE[0]},
                }
            )
            links.append(
                {
                    "source": symbol,
                    "target": name,
                    "value": round(score, 3),
                    "lineStyle": {
                        "width": round(1 + score * 5, 2),
                        "color": "rgba(110,168,254,.5)",
                    },
                }
            )
        option = {
            "tooltip": {"trigger": "item"},
            "series": [
                {
                    "type": "graph",
                    "layout": "circular",
                    "roam": True,
                    "edgeSymbol": ["none", "none"],
                    "label": {"show": True, "color": "#c9d6e5", "fontSize": 10},
                    "lineStyle": {"curveness": 0.1, "opacity": 0.8},
                    "data": nodes,
                    "links": links,
                }
            ],
        }
    else:
        option = empty_option()
    specs.append(
        ChartSpec(
            id="pathway-network",
            title="STRING interaction partners",
            subtitle="Source: STRING (combined score >= 0.7); edge width ~ score",
            option=option,
        )
    )
    return specs


def build_ptm(result: ModuleResult) -> list[ChartSpec]:
    types = result.tables.get("ptm_types")
    if isinstance(types, pd.DataFrame) and not types.empty:
        frame = types.dropna(subset=["type", "count"])
        option = _barh(
            [str(value) for value in frame["type"]],
            [int(_num(value)) for value in frame["count"]],
            color=PALETTE[3],
            x_name="Site count",
        )
    else:
        option = empty_option()
    specs = [
        ChartSpec(
            id="ptm-types",
            title="Curated PTM types",
            subtitle="Source: UniProt (curated features)",
            option=option,
        )
    ]

    sites = result.tables.get("ptm_sites")
    if isinstance(sites, pd.DataFrame) and not sites.empty:
        frame = sites.dropna(subset=["type", "position"])
        categories = list(dict.fromkeys(frame["type"].astype(str)))
        series = []
        for index, category in enumerate(categories):
            subset = frame[frame["type"].astype(str) == category]
            series.append(
                {
                    "type": "scatter",
                    "name": category,
                    "data": [[int(value), index] for value in subset["position"]],
                    "symbolSize": 11,
                    "itemStyle": {"color": PALETTE[index % len(PALETTE)]},
                }
            )
        default_max = int(sites["end"].max()) if "end" in sites else 0
        length = int(_num(result.facts.get("sequence_length"), default_max))
        option = {
            "tooltip": {"trigger": "item"},
            "grid": dict(GRID),
            "xAxis": {
                "type": "value",
                "min": 0,
                "max": length + 2,
                "name": "Residue position",
                "nameTextStyle": {"color": "#8b9bb0"},
                "axisLabel": {"color": "#8b9bb0"},
                "splitLine": {"lineStyle": {"color": "rgba(120,160,200,.12)"}},
            },
            "yAxis": {
                "type": "category",
                "data": categories,
                "axisLabel": {"color": "#c9d6e5", "width": 150, "overflow": "truncate"},
                "axisLine": {"lineStyle": {"color": "rgba(120,160,200,.2)"}},
            },
            "series": series,
        }
        domains = result.tables.get("domains")
        if isinstance(domains, pd.DataFrame) and not domains.empty and series:
            series[0]["markArea"] = {
                "silent": True,
                "itemStyle": {"color": "rgba(110,168,254,.10)"},
                "data": [
                    [{"xAxis": int(row.start)}, {"xAxis": int(row.end)}]
                    for row in domains.itertuples()
                ],
            }
    else:
        option = empty_option()
    specs.append(
        ChartSpec(
            id="ptm-sites",
            title="Curated PTM sites (shaded: domains / regions)",
            subtitle="Source: UniProt (curated features)",
            option=option,
        )
    )
    return specs


def build_disease(result: ModuleResult) -> list[ChartSpec]:
    diseases = result.tables.get("diseases")
    if isinstance(diseases, pd.DataFrame) and not diseases.empty:
        top = diseases.dropna(subset=["disease", "score"]).head(12)
        option = _barh(
            [str(value) for value in top["disease"]],
            [round(_num(value), 3) for value in top["score"]],
            x_name="Open Targets association score",
        )
    else:
        option = empty_option()
    specs = [
        ChartSpec(
            id="disease-top",
            title="Top associated diseases",
            subtitle="Source: Open Targets Platform",
            option=option,
        )
    ]

    sources = result.tables.get("datasources")
    if isinstance(sources, pd.DataFrame) and not sources.empty:
        top = sources.dropna(subset=["datasource", "diseases"]).head(12)
        option = _barh(
            [str(value) for value in top["datasource"]],
            [int(_num(value)) for value in top["diseases"]],
            color=PALETTE[5],
            x_name="Top-ranked diseases with evidence",
        )
    else:
        option = empty_option()
    specs.append(
        ChartSpec(
            id="disease-sources",
            title="Evidence by data source",
            subtitle="Source: Open Targets Platform",
            option=option,
        )
    )
    return specs


def build_tractability(result: ModuleResult) -> list[ChartSpec]:
    frame = result.tables.get("tractability")
    if isinstance(frame, pd.DataFrame) and not frame.empty:
        frame = frame.dropna(subset=["modality", "bucket"])
        modalities = list(dict.fromkeys(frame["modality"].astype(str)))
        buckets = list(dict.fromkeys(frame["bucket"].astype(str)))
        lookup = {
            (str(row.modality), str(row.bucket)): 1 if bool(row.available) else 0
            for row in frame.itertuples()
        }
        data = [
            [x_index, y_index, lookup.get((modality, bucket), 0)]
            for x_index, modality in enumerate(modalities)
            for y_index, bucket in enumerate(buckets)
        ]
        option = {
            "tooltip": {"position": "top"},
            "grid": {
                "left": 8,
                "right": 24,
                "top": 16,
                "bottom": 64,
                "containLabel": True,
            },
            "xAxis": {
                "type": "category",
                "data": modalities,
                "axisLabel": {"color": "#8b9bb0", "interval": 0, "rotate": 20},
                "axisLine": {"lineStyle": {"color": "rgba(120,160,200,.2)"}},
            },
            "yAxis": {
                "type": "category",
                "data": buckets,
                "axisLabel": {"color": "#c9d6e5", "width": 170, "overflow": "truncate"},
                "axisLine": {"lineStyle": {"color": "rgba(120,160,200,.2)"}},
            },
            "visualMap": {
                "min": 0,
                "max": 1,
                "show": False,
                "inRange": {"color": ["#0f1620", "#55d6be"]},
            },
            "series": [
                {
                    "type": "heatmap",
                    "data": data,
                    "label": {"show": True, "formatter": "{c}", "color": "#0b1118"},
                    "itemStyle": {"borderColor": "rgba(8,11,16,.6)", "borderWidth": 2},
                }
            ],
        }
    else:
        option = empty_option()
    specs = [
        ChartSpec(
            id="tractability-heat",
            title="Tractability buckets by modality",
            subtitle="Source: Open Targets Platform; 1 = available",
            option=option,
        )
    ]

    stages = result.tables.get("drug_stages")
    if isinstance(stages, pd.DataFrame) and not stages.empty:
        frame = stages.dropna(subset=["stage", "count"])
        option = _barh(
            [str(value) for value in frame["stage"]],
            [int(_num(value)) for value in frame["count"]],
            color=PALETTE[2],
            x_name="Count",
        )
    else:
        option = empty_option()
    specs.append(
        ChartSpec(
            id="tractability-stages",
            title="Drugs and clinical candidates",
            subtitle="Source: Open Targets Platform",
            option=option,
        )
    )
    return specs


def build_safety(result: ModuleResult) -> list[ChartSpec]:
    phenotypes = result.tables.get("mouse_phenotypes")
    if isinstance(phenotypes, pd.DataFrame) and not phenotypes.empty:
        top = phenotypes.dropna(subset=["phenotype_class", "models"]).head(12)
        option = _barh(
            [str(value) for value in top["phenotype_class"]],
            [int(_num(value)) for value in top["models"]],
            color=PALETTE[3],
            x_name="Models affected",
        )
    else:
        option = empty_option()
    specs = [
        ChartSpec(
            id="safety-mouse",
            title="IMPC mouse phenotypes",
            subtitle="Source: Open Targets / IMPC",
            option=option,
        )
    ]

    breadth = result.tables.get("expression_breadth")
    if isinstance(breadth, pd.DataFrame) and not breadth.empty:
        top = breadth.dropna(subset=["tissue", "median"]).head(15)
        option = _barh(
            [str(value) for value in top["tissue"]],
            [round(_num(value), 3) for value in top["median"]],
            color=PALETTE[1],
            x_name="Median TPM",
        )
    else:
        option = empty_option()
    specs.append(
        ChartSpec(
            id="safety-breadth",
            title="GTEx expression breadth",
            subtitle="Source: GTEx v8",
            option=option,
        )
    )
    return specs


def build_cancer(result: ModuleResult) -> list[ChartSpec]:
    frame = result.tables.get("hallmarks")
    if isinstance(frame, pd.DataFrame) and not frame.empty:
        top = frame.dropna(subset=["label"]).head(12)
        categories = [str(value) for value in top["label"]]
        promotes = [int(_num(value)) for value in top["promotes"]]
        suppresses = [int(_num(value)) for value in top["suppresses"]]
        option = {
            "grid": dict(GRID),
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
            "legend": {
                "data": ["promotes", "suppresses"],
                "textStyle": {"color": "#8b9bb0"},
                "top": 0,
            },
            "xAxis": {
                "type": "value",
                "axisLabel": {"color": "#8b9bb0"},
                "splitLine": {"lineStyle": {"color": "rgba(120,160,200,.12)"}},
            },
            "yAxis": {
                "type": "category",
                "inverse": True,
                "data": categories,
                "axisLabel": {"color": "#c9d6e5", "width": 200, "overflow": "truncate"},
                "axisLine": {"lineStyle": {"color": "rgba(120,160,200,.2)"}},
            },
            "series": [
                {
                    "type": "bar",
                    "name": "promotes",
                    "stack": "impact",
                    "data": promotes,
                    "barMaxWidth": 18,
                    "itemStyle": {"color": PALETTE[2]},
                },
                {
                    "type": "bar",
                    "name": "suppresses",
                    "stack": "impact",
                    "data": suppresses,
                    "barMaxWidth": 18,
                    "itemStyle": {"color": PALETTE[1]},
                },
            ],
        }
    else:
        option = empty_option()
    return [
        ChartSpec(
            id="cancer-hallmarks",
            title="Cancer hallmarks by impact",
            subtitle="Source: Open Targets Platform; counts of curated hallmark entries",
            option=option,
        )
    ]


_AF_BANDS = (
    ("Very high (≥90)", 90, 100, "rgba(85,214,190,.08)"),
    ("Confident (70–90)", 70, 90, "rgba(110,168,254,.07)"),
    ("Low (50–70)", 50, 70, "rgba(240,176,83,.07)"),
    ("Very low (<50)", 0, 50, "rgba(242,125,154,.06)"),
)

_AF_COLORS = {
    "Very high (≥90)": "#55d6be",
    "Confident (70–90)": "#6ea8fe",
    "Low (50–70)": "#f0b053",
    "Very low (<50)": "#f27d9a",
}


def build_basic(result: ModuleResult) -> list[ChartSpec]:
    charts: list[ChartSpec] = []

    plddt = result.tables.get("alphafold_plddt")
    if isinstance(plddt, pd.DataFrame) and not plddt.empty:
        frame = plddt.dropna(subset=["residue", "plddt"])
        data = [
            [int(row.residue), round(float(row.plddt), 1)]
            for row in frame.itertuples(index=False)
        ]
        if data:
            entry = str(result.facts.get("alphafold_entry_id") or "")
            version = str(result.facts.get("alphafold_model_version") or "")
            subtitle = "Source: AlphaFold DB"
            if entry:
                subtitle += f" · {entry}"
            if version:
                subtitle += f" · {version}"
            bands = [
                [
                    {
                        "name": name,
                        "yAxis": high,
                        "itemStyle": {"color": color},
                        "label": {
                            "show": True,
                            "position": "insideTopLeft",
                            "color": "#8b9bb0",
                            "fontSize": 10,
                        },
                    },
                    {"yAxis": low},
                ]
                for name, high, low, color in _AF_BANDS
            ]
            option = {
                "grid": {
                    "left": 48,
                    "right": 16,
                    "top": 30,
                    "bottom": 30,
                    "containLabel": True,
                },
                "tooltip": {"trigger": "axis", "axisPointer": {"type": "line"}},
                "xAxis": {
                    "type": "value",
                    "name": "Residue",
                    "min": 1,
                    "nameTextStyle": {"color": "#8b9bb0"},
                    "axisLabel": {"color": "#8b9bb0"},
                    "splitLine": {"lineStyle": {"color": "rgba(120,160,200,.12)"}},
                },
                "yAxis": {
                    "type": "value",
                    "name": "pLDDT",
                    "min": 0,
                    "max": 100,
                    "nameTextStyle": {"color": "#8b9bb0"},
                    "axisLabel": {"color": "#8b9bb0"},
                    "splitLine": {"lineStyle": {"color": "rgba(120,160,200,.12)"}},
                },
                "series": [
                    {
                        "type": "line",
                        "name": "pLDDT",
                        "data": data,
                        "showSymbol": False,
                        "lineStyle": {"width": 1.6, "color": "#55d6be"},
                        "areaStyle": {
                            "color": {
                                "type": "linear",
                                "x": 0,
                                "y": 0,
                                "x2": 0,
                                "y2": 1,
                                "colorStops": [
                                    {"offset": 0, "color": "rgba(85,214,190,.28)"},
                                    {"offset": 1, "color": "rgba(85,214,190,.02)"},
                                ],
                            }
                        },
                        "markArea": {"silent": True, "data": bands},
                    }
                ],
            }
            charts.append(
                ChartSpec(
                    id="alphafold-residue",
                    title="AlphaFold per-residue pLDDT",
                    subtitle=subtitle,
                    option=option,
                )
            )

    categories = result.tables.get("alphafold_categories")
    if isinstance(categories, pd.DataFrame) and not categories.empty:
        data = [
            {
                "name": str(row.category),
                "value": round(float(row.pct), 1),
                "itemStyle": {"color": _AF_COLORS.get(str(row.category), PALETTE[0])},
            }
            for row in categories.itertuples(index=False)
        ]
        mean = result.facts.get("alphafold_mean_plddt")
        graphic = []
        if mean is not None:
            graphic = [
                {
                    "type": "text",
                    "left": "center",
                    "top": "33%",
                    "style": {
                        "text": f"{float(mean):.1f}",
                        "fill": "#e7eef7",
                        "fontSize": 26,
                        "fontWeight": 700,
                        "textAlign": "center",
                    },
                },
                {
                    "type": "text",
                    "left": "center",
                    "top": "43%",
                    "style": {
                        "text": "mean pLDDT",
                        "fill": "#8b9bb0",
                        "fontSize": 11,
                        "textAlign": "center",
                    },
                },
            ]
        option = {
            "tooltip": {"trigger": "item"},
            "legend": {
                "bottom": 0,
                "textStyle": {"color": "#8b9bb0", "fontSize": 10},
                "itemWidth": 10,
                "itemHeight": 10,
            },
            "graphic": graphic,
            "series": [
                {
                    "type": "pie",
                    "radius": ["52%", "76%"],
                    "center": ["50%", "44%"],
                    "avoidLabelOverlap": True,
                    "label": {
                        "formatter": "{b}\n{c}%",
                        "color": "#c9d6e5",
                        "fontSize": 11,
                    },
                    "labelLine": {"lineStyle": {"color": "rgba(120,160,200,.35)"}},
                    "data": data,
                }
            ],
        }
        charts.append(
            ChartSpec(
                id="alphafold-confidence",
                title="AlphaFold confidence distribution",
                subtitle="Source: AlphaFold DB",
                option=option,
            )
        )

    return charts


def build_comparative(result: ModuleResult) -> list[ChartSpec]:
    frame = result.tables.get("homologues")
    if isinstance(frame, pd.DataFrame) and not frame.empty:
        top = frame.dropna(subset=["species", "identity"]).head(12)
        categories = [
            f"{row.species} · {str(row.type).replace('_', ' ')}" for row in top.itertuples()
        ]
        option = _barh(
            categories,
            [round(_num(value), 2) for value in top["identity"]],
            color=PALETTE[4],
            x_name="Query identity (%)",
            suffix="%",
        )
    else:
        option = empty_option()
    return [
        ChartSpec(
            id="comparative-identity",
            title="Homologue sequence identity",
            subtitle="Source: Open Targets Platform",
            option=option,
        )
    ]
