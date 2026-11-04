from typer.testing import CliRunner

from target_profile.cli import app


def test_version_command():
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert "target-profile 0.1.0" in result.output


def test_basic_module_has_chart_builder():
    from target_profile.cli import BUILDERS, MODULES

    assert any(module.__name__ == "analyze_basic" for module in MODULES)
    assert "basic" in BUILDERS
