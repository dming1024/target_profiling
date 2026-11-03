import pandas as pd
import pyarrow.parquet as pq

from target_profile.config import Settings
from target_profile.errors import DataMissing
from target_profile.models import GeneContext, ModuleResult


def analyze_dependency(ctx: GeneContext, settings: Settings, offline: bool = True) -> ModuleResult:
    result = ModuleResult(name="dependency")
    parquet = settings.data_root / "parquet"
    effect_path = parquet / "depmap_gene_effect.parquet"
    model_path = parquet / "depmap_model.parquet"
    if not effect_path.exists() or not model_path.exists():
        raise DataMissing(f"missing DepMap data under {parquet}; run `target-profile data`")

    schema = pq.read_schema(effect_path).names
    column = next((c for c in schema if c.startswith(f"{ctx.symbol} (")), None)
    if not column:
        return result.degrade(f"dependency: no DepMap column for {ctx.symbol}")

    effect = pq.read_table(effect_path, columns=["ModelID", column]).to_pandas()
    effect = effect.rename(columns={column: "effect"}).dropna()
    model = pd.read_parquet(model_path)[
        ["ModelID", "CellLineName", "OncotreeLineage", "OncotreePrimaryDisease"]
    ]
    df = effect.merge(model, on="ModelID", how="left")

    threshold = settings.thresholds.strong_dependency_effect
    strong = df[df["effect"] <= threshold].sort_values("effect")
    by_lineage = (
        df.groupby("OncotreeLineage")["effect"]
        .agg(["median", "mean", "count"])
        .reset_index()
        .query("count >= 3")
        .sort_values("median")
    )

    result.tables["distribution"] = df
    result.tables["strong_lines"] = strong
    result.tables["by_lineage"] = by_lineage
    result.facts.update(
        {
            "n_lines": int(len(df)),
            "median_effect": round(float(df["effect"].median()), 3),
            "mean_effect": round(float(df["effect"].mean()), 3),
            "strong_dependency_count": int(len(strong)),
            "strong_dependency_fraction": round(float(len(strong) / len(df)), 3) if len(df) else 0.0,
            "threshold_effect": threshold,
            "top_lineage": str(by_lineage.iloc[0]["OncotreeLineage"]) if not by_lineage.empty else None,
            "top_lineage_median": (
                round(float(by_lineage.iloc[0]["median"]), 3) if not by_lineage.empty else None
            ),
            "most_dependent_line": (
                str(strong.iloc[0]["CellLineName"]) if not strong.empty else None
            ),
        }
    )
    return result
