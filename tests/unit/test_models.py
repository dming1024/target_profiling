from target_profile.models import ChartSpec, ModuleResult


def test_chart_spec_defaults():
    spec = ChartSpec(id="expression-gtex", title="GTEx tissue expression")
    assert spec.subtitle == ""
    assert spec.option == {}


def test_chart_spec_is_frozen():
    spec = ChartSpec(id="x", title="X")
    try:
        spec.option = {"a": 1}
    except Exception as exc:
        assert exc.__class__.__name__ == "FrozenInstanceError"
    else:
        raise AssertionError("ChartSpec must be frozen")


def test_module_result_new_fields():
    result = ModuleResult(name="expression")
    assert result.charts == []
    assert result.narrative is None
    assert result.label_cards == []
