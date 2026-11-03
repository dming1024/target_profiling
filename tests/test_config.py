from pathlib import Path

from target_profile.config import load_settings


def test_load_settings_resolves_relative_paths(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/settings.toml").write_text(
        'lake_root = "/lake"\ndata_root = "local_data"\nout_root = "local_out"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("TARGET_PROFILE_HOME", str(tmp_path))

    settings = load_settings()

    assert settings.lake_root == Path("/lake")
    assert settings.data_root == tmp_path / "local_data"
    assert settings.out_root == tmp_path / "local_out"
    assert settings.thresholds.strong_dependency_effect == -0.5
