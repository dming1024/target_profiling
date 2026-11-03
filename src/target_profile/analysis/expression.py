import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from target_profile.config import Settings
from target_profile.errors import DataMissing
from target_profile.models import GeneContext, ModuleResult


def _read(path):
    if not path.exists():
        raise DataMissing(f"missing local data: {path}; run `target-profile data`")
    return pd.read_parquet(path)


def _tau(values: pd.Series) -> float:
    arr = values.to_numpy(dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 2 or arr.max() <= 0:
        return 0.0
    return float(((1 - arr / arr.max()).sum()) / (len(arr) - 1))


def analyze_expression(ctx: GeneContext, settings: Settings, offline: bool = True) -> ModuleResult:
    result = ModuleResult(name="expression")
    parquet = settings.data_root / "parquet"

    gtex = _read(parquet / "gtex.parquet")
    sub = gtex[gtex["Gene"] == ctx.symbol].copy()
    if sub.empty:
        return result.degrade("GTEx: no expression record")

    tissue = (
        sub.groupby("Tissue")["Expression"]
        .agg(["median", "mean", "max", "count"])
        .reset_index()
        .sort_values("median", ascending=False)
    )
    tissues = sub["Tissue"].unique()
    percentiles = []
    all_genes = gtex[gtex["Tissue"].isin(tissues)]
    for tissue_name, group in all_genes.groupby("Tissue"):
        value = sub.loc[sub["Tissue"] == tissue_name, "Expression"].iloc[0]
        percentiles.append(
            {
                "Tissue": tissue_name,
                "percentile": round(float((group["Expression"] < value).mean() * 100), 1),
            }
        )
    percentile_df = pd.DataFrame(percentiles).sort_values("percentile", ascending=False)

    result.tables["gtex"] = tissue
    result.tables["gtex_percentile"] = percentile_df
    result.facts.update(
        {
            "gtex_tissue_count": int(len(tissue)),
            "gtex_top_tissue": str(tissue.iloc[0]["Tissue"]),
            "gtex_top_median_tpm": round(float(tissue.iloc[0]["median"]), 2),
            "gtex_median_across_tissues": round(float(tissue["median"].median()), 2),
            "tau": round(_tau(tissue["median"]), 3),
            "gtex_mean_percentile": round(float(percentile_df["percentile"].mean()), 1),
        }
    )

    expr_path = parquet / "depmap_expression.parquet"
    if expr_path.exists():
        schema = pq.read_schema(expr_path).names
        column = next((c for c in schema if c.startswith(f"{ctx.symbol} (")), None)
        if column:
            expr = pq.read_table(expr_path, columns=["ModelID", column]).to_pandas()
            expr = expr.rename(columns={column: "value"}).dropna()
            model = _read(parquet / "depmap_model.parquet")
            wanted = ["ModelID", "CellLineName", "OncotreeLineage", "OncotreePrimaryDisease"]
            model = model[[c for c in wanted if c in model.columns]]
            expr = expr.merge(model, on="ModelID", how="left")
            lineage = (
                expr.groupby("OncotreeLineage")["value"]
                .agg(["median", "mean", "count"])
                .reset_index()
                .query("count >= 3")
                .sort_values("median", ascending=False)
            )
            result.tables["depmap_lineage"] = lineage
            result.tables["depmap_lines"] = expr.sort_values("value", ascending=False)
            result.facts.update(
                {
                    "depmap_n_lines": int(len(expr)),
                    "depmap_median_logtpm": round(float(expr["value"].median()), 2),
                    "depmap_top_lineage": (
                        str(lineage.iloc[0]["OncotreeLineage"]) if not lineage.empty else None
                    ),
                }
            )

    hpa_path = parquet / "hpa.parquet"
    if hpa_path.exists():
        hpa = _read(hpa_path)
        row = hpa[hpa["Gene"] == ctx.symbol]
        if not row.empty:
            record = row.iloc[0]
            result.facts["hpa_tissue_specificity"] = str(record.get("RNA tissue specificity"))
            result.facts["hpa_subcellular_location"] = str(record.get("Subcellular location"))

    return result
