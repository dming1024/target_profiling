from target_profile.llm.guard import validate_numbers


FACTS = {
    "overall_freq_pct": 6.96,
    "n_lines": 1183,
    "top_partner": "PIK3CA",
    "tau": 0.575,
    "top_disease": "Noonan syndrome",
}


def test_guard_accepts_fact_numbers():
    text = "KRAS 泛癌突变率为 6.96%，在 1183 个细胞系中评估，组织特异性 τ 为 0.575。"
    assert validate_numbers(text, FACTS, "KRAS") == []


def test_guard_rejects_invented_number():
    assert validate_numbers("KRAS 突变率为 99.9%。", FACTS, "KRAS") == ["99.9"]


def test_guard_ignores_gene_symbols_and_variants():
    text = "KRAS 与 PIK3CA 互作，G12D 变异常见，突变率 6.96%。"
    assert validate_numbers(text, FACTS, "KRAS") == []


def test_guard_accepts_integers_within_float_facts():
    assert validate_numbers("共 1183 条记录。", FACTS, "KRAS") == []


def test_guard_accepts_negative_fact_numbers():
    facts = {"median_effect": -0.371, "threshold_effect": -0.5}
    text = "中位效应为 -0.371，强依赖阈值为 -0.5。"
    assert validate_numbers(text, facts, "KRAS") == []


def test_guard_accepts_magnitude_without_sign():
    facts = {"median_effect": -0.371}
    assert validate_numbers("中位效应为 0.371。", facts, "KRAS") == []
    assert validate_numbers("中位效应为 −0.371。", facts, "KRAS") == []


def test_guard_accepts_thousands_separators():
    facts = {"n_samples": 10967}
    assert validate_numbers("共 10,967 个样本。", facts, "KRAS") == []


def test_guard_ignores_identifier_digits_in_facts():
    facts = {"top_partner": "PIK3CA", "n_partners_high_conf": 100}
    assert validate_numbers("高置信互作伙伴 3 个。", facts, "KRAS") == ["3"]

    variant_facts = {"top_protein_change": "G12D", "top_protein_change_count": 197}
    assert validate_numbers("G12D 出现 12 次。", variant_facts, "KRAS") == ["12"]


def test_guard_rejects_invented_negative_number():
    assert validate_numbers("中位效应为 -1.2。", {"median_effect": -0.371}, "KRAS") == ["-1.2"]
