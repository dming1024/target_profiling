import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field


class Thresholds(BaseModel):
    tissue_specific_tau: float = 0.9
    tissue_partial_tau: float = 0.6
    pan_cancer_hotspot_pct: float = 5.0
    strong_dependency_effect: float = -0.5
    loeuf_constrained: float = 0.6
    string_min_score: float = 0.7
    expression_breadth_tpm: float = 1.0


class LLMSettings(BaseModel):
    enabled: bool = False
    base_url: str = "https://api.openai.com/v1"
    model: str = ""
    api_key_env: str = "TARGET_PROFILE_LLM_API_KEY"


class Settings(BaseModel):
    lake_root: Path
    data_root: Path
    out_root: Path
    thresholds: Thresholds = Field(default_factory=Thresholds)
    llm: LLMSettings = Field(default_factory=LLMSettings)


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def load_settings(config_path: Path | None = None) -> Settings:
    root = Path(os.environ.get("TARGET_PROFILE_HOME", Path.cwd()))
    path = config_path or root / "config/settings.toml"
    raw: dict = tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    raw.setdefault("lake_root", "/root/Biomni/Biomni/data/biomni_data/data_lake")
    raw.setdefault("data_root", "data")
    raw.setdefault("out_root", "out")
    raw["lake_root"] = _resolve(root, raw["lake_root"])
    raw["data_root"] = _resolve(root, raw["data_root"])
    raw["out_root"] = _resolve(root, raw["out_root"])
    return Settings(**raw)
