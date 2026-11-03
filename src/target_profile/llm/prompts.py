from __future__ import annotations

import json

from target_profile.models import ModuleResult

PROMPT_VERSION = "v1"

SYSTEM_PROMPT = (
    "你是生物医药靶点分析写作助手。只能改写措辞，不得新增、删除或修改任何数字、"
    "基因符号与数据事实；不得引入外部知识；不得给出临床或用药建议。"
    "使用简体中文，1 到 3 句，专业、克制、客观。"
)


def _value(facts: dict, key: str, default: str = "—"):
    value = facts.get(key)
    return default if value is None else value


def template_narrative(gene: str, module: ModuleResult) -> str:
    facts = module.facts
    name = module.name
    if name == "basic":
        return (
            f"{gene} 属于 {_value(facts, 'target_class')}，蛋白长度 "
            f"{_value(facts, 'protein_length')} aa，亚细胞定位为 "
            f"{_value(facts, 'subcellular_locations')}。"
        )
    if name == "disease":
        return (
            f"Open Targets 关联 {_value(facts, 'disease_count')} 种疾病，最高为 "
            f"{_value(facts, 'top_disease')}（评分 {_value(facts, 'top_disease_score')}）；"
            f"LoF pLI {_value(facts, 'pli')}、LOEUF {_value(facts, 'loeuf')}，"
            f"ClinVar 记录 {_value(facts, 'clinvar_total')} 条。"
        )
    if name == "expression":
        return (
            f"{gene} 在 {_value(facts, 'gtex_tissue_count')} 个 GTEx 组织中可检测，"
            f"最高表达于 {_value(facts, 'gtex_top_tissue')}（中位 "
            f"{_value(facts, 'gtex_top_median_tpm')} TPM），组织特异性 τ 为 "
            f"{_value(facts, 'tau')}。"
        )
    if name == "mutation":
        return (
            f"TCGA PanCancer 合并样本中 {gene} 的突变率为 "
            f"{_value(facts, 'overall_freq_pct')}%，最高见于 "
            f"{_value(facts, 'top_cancer')}（{_value(facts, 'top_cancer_freq_pct')}%）；"
            f"最常见蛋白改变为 {_value(facts, 'top_protein_change')}"
            f"（{_value(facts, 'top_protein_change_count')} 次）。"
        )
    if name == "dependency":
        return (
            f"DepMap 共 {_value(facts, 'n_lines')} 个细胞系中，{gene} 的中位 Chronos "
            f"效应为 {_value(facts, 'median_effect')}，强依赖（≤ "
            f"{_value(facts, 'threshold_effect')}）细胞系 "
            f"{_value(facts, 'strong_dependency_count')} 个，占比 "
            f"{_value(facts, 'strong_dependency_fraction')}。"
        )
    if name == "cancer":
        return (
            f"{gene} 命中 {_value(facts, 'n_cancer_hallmarks')} 项癌症 hallmark，"
            f"代表性为 {_value(facts, 'top_hallmark')}；驱动状态评估为 "
            f"{_value(facts, 'driver_status')}，泛癌必需为 "
            f"{_value(facts, 'essential')}。"
        )
    if name == "pathway":
        return (
            f"{gene} 参与 {_value(facts, 'n_pathways')} 条 Reactome 通路，主要类别为 "
            f"{_value(facts, 'top_level_term')}；高置信互作伙伴 "
            f"{_value(facts, 'n_partners_high_conf')} 个，最强为 "
            f"{_value(facts, 'top_partner')}（{_value(facts, 'top_partner_score')}）。"
        )
    if name == "ptm":
        return (
            f"UniProt 注释了 {gene} 的 {_value(facts, 'n_ptm_sites')} 个 PTM 位点，"
            f"主要为 {_value(facts, 'top_ptm_type')}；序列长度 "
            f"{_value(facts, 'sequence_length')} aa，注释结构域/区域 "
            f"{_value(facts, 'n_domains')} 个。"
        )
    if name == "tractability":
        return (
            f"{gene} 的可成药性为 {_value(facts, 'tractable')}，已批准药物模态为 "
            f"{_value(facts, 'approved_modalities')}；化学探针 "
            f"{_value(facts, 'n_probes')} 个，药物/临床候选 "
            f"{_value(facts, 'n_drugs')} 个。"
        )
    if name == "safety":
        return (
            f"Open Targets 安全事件记录 {_value(facts, 'n_safety_liabilities')} 条，"
            f"IMPC 小鼠表型 {_value(facts, 'n_mouse_phenotypes')} 个，泛癌必需为 "
            f"{_value(facts, 'common_essential')}。无安全记录不代表安全。"
        )
    if name == "comparative":
        return (
            f"{gene} 共记录 {_value(facts, 'n_homologues')} 个同源基因，最高一致性为 "
            f"{_value(facts, 'top_homologue')}（{_value(facts, 'top_homologue_identity')}%），"
            f"最近旁系一致性为 {_value(facts, 'top_paralogue_identity')}%。"
        )
    return ""


def build_user_prompt(gene: str, module: ModuleResult, draft: str) -> str:
    facts = json.dumps(module.facts, ensure_ascii=False, sort_keys=True, default=str)
    return (
        f"基因：{gene}\n"
        f"维度：{module.name}\n"
        f"事实 JSON：{facts}\n"
        f"模板草稿：{draft}\n"
        "请仅改写模板草稿的措辞，保留全部数字、基因符号与事实，输出 1-3 句简体中文。"
    )
