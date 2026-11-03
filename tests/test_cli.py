from typer.testing import CliRunner

from target_profile.cli import app


def test_version_command():
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert "target-profile 0.1.0" in result.output
