import json

from target_profile.api.alphafold import alphafold_prediction
from target_profile.api.cache import CachedFetcher
from target_profile.api.stringdb import interaction_partners
from target_profile.api.uniprot import uniprot_record


def test_uniprot_record_reads_cache(tmp_path):
    global_dir = tmp_path / "_global"
    global_dir.mkdir(parents=True)
    (global_dir / "uniprot_P01116.json").write_text(
        json.dumps({"sequence": {"length": 189}})
    )
    fetcher = CachedFetcher(tmp_path, offline=True)
    record = uniprot_record("P01116", fetcher)
    assert record["sequence"]["length"] == 189


def test_uniprot_record_without_accession_returns_none(tmp_path):
    fetcher = CachedFetcher(tmp_path, offline=True)
    assert uniprot_record(None, fetcher) is None


def test_interaction_partners_reads_cache(tmp_path):
    gene_dir = tmp_path / "KRAS"
    gene_dir.mkdir(parents=True)
    (gene_dir / "string_partners.json").write_text(
        json.dumps([{"preferredName_B": "RAF1", "score": 0.99}])
    )
    fetcher = CachedFetcher(tmp_path, offline=True)
    partners = interaction_partners("KRAS", fetcher)
    assert partners[0]["preferredName_B"] == "RAF1"


def test_alphafold_reads_cache(tmp_path):
    global_dir = tmp_path / "_global"
    global_dir.mkdir(parents=True)
    (global_dir / "alphafold_P01116.json").write_text(
        json.dumps([{"globalMetricValue": 91.5}])
    )
    fetcher = CachedFetcher(tmp_path, offline=True)
    prediction = alphafold_prediction("P01116", fetcher)
    assert prediction["globalMetricValue"] == 91.5


def test_alphafold_without_accession_returns_none(tmp_path):
    fetcher = CachedFetcher(tmp_path, offline=True)
    assert alphafold_prediction(None, fetcher) is None
