import pandas as pd

from target_profile.models import GeneContext, ModuleResult
from target_profile.report.render import _speed_rows, build_report_context


def _context():
    gene = GeneContext(
        symbol="TP53",
        ensembl_id="ENSG00000141510",
        uniprot_id="P04637",
    )
    basic = ModuleResult(
        name="basic",
        facts={
            "protein_length": 393,
            "target_class": "Transcription factor",
            "subcellular_locations": "Nucleus",
            "alphafold_mean_plddt": 75.1,
            "alphafold_very_high_pct": 52.7,
            "alphafold_coverage": "1–393 aa (100%)",
        },
        tables={
            "alphafold_categories": pd.DataFrame(
                {"category": ["Very high (≥90)"], "residues": [207], "pct": [52.7]}
            ),
            "alphafold_plddt": pd.DataFrame(
                {"residue": [1], "plddt": [90.0], "category": ["A"]}
            ),
        },
        links=[
            {
                "label": "AlphaFold DB",
                "url": "https://alphafold.ebi.ac.uk/entry/P04637",
            }
        ],
    )
    return build_report_context(gene, [basic])


def test_basic_block_has_links_and_hides_plddt_table():
    context = _context()
    section = next(s for s in context["sections"] if s["id"] == "ch-2")
    block = section["blocks"][0]

    assert block["links"][0]["label"] == "AlphaFold DB"
    table_ids = [table["id"] for table in block["details"]["tables"]]
    assert "alphafold_categories" in table_ids
    assert "alphafold_plddt" not in table_ids


def test_summary_has_alphafold_item():
    context = _context()
    group = next(g for g in context["summary_view"]["groups"] if g["title"] == "靶点定位")
    item = next(item for item in group["items"] if item["label"] == "AlphaFold pLDDT")
    assert item["value"] == "75.1 · 高置信 52.7%"


def test_print_speed_rows_include_structure_row():
    context = _context()
    rows = _speed_rows(context["sections"])
    row = next(row for row in rows if row["title"] == "结构置信度")
    assert "75.100" in row["value"]
    assert "高置信 52.70%" in row["value"]
    assert row["status"] == "覆盖 100%"
