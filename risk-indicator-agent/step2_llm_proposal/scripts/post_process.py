"""LLM 输出 → 元表 schema 标准化. 补默认值, 不改业务字段."""

from __future__ import annotations

from datetime import date
from typing import Any

from indicator_pipeline.config import AgentConfig
from indicator_pipeline.meta_schema import get_default_post_processing


_DOMAIN_DEFAULT_NULL_HANDLING = {
    "FIN": ["KEEP_NULL", "SAFE_DIVIDE_NULL"],
    "CRDTC": ["KEEP_NULL", "SAFE_DIVIDE_ZERO"],
    "OPN": ["DROP_KEY_NULL", "FALLBACK_OTHER"],
    "PUB": ["DROP_KEY_NULL", "FALLBACK_OTHER"],
}


def fill_defaults(prop: dict[str, Any], cfg: AgentConfig, seed: dict[str, Any] | None = None) -> dict[str, Any]:
    """补必填字段默认值. 不覆盖 LLM 已写的字段."""
    today = date.today().isoformat()
    out = dict(prop)

    # 拉链默认
    out.setdefault("ind_version", 1)
    out.setdefault("eff_dt", today)
    out.setdefault("exp_dt", "9999-12-31")
    out.setdefault("etl_dt", today)
    out.setdefault("part_ymd", today.replace("-", ""))

    # 来源
    out.setdefault("proposer", "LLM_AGENT")
    out.setdefault("lifecycle_status", "DRAFT")
    out.setdefault("owner", cfg.defaults.get("owner", "RISK_TEAM"))

    # 默认结构性字段
    out.setdefault("granularity", cfg.defaults.get("granularity", "M"))
    out.setdefault("window", cfg.defaults.get("window", "SNAP"))
    out.setdefault("ref_date_logic", cfg.defaults.get("ref_date_logic", "BATCH_MAX"))
    out.setdefault("is_dynamic_expansion", 0)

    # post_processing_rule 按域默认
    domain = out.get("domain", "")
    if "post_processing_rule" not in out or not out["post_processing_rule"]:
        out["post_processing_rule"] = get_default_post_processing(domain, cfg.project_root)

    # null_handling 按域默认
    if not out.get("null_handling"):
        out["null_handling"] = _DOMAIN_DEFAULT_NULL_HANDLING.get(domain, ["KEEP_NULL"])

    # IV / 信号 (从 seed 回填实测)
    if seed:
        if out.get("current_iv") is None:
            out["current_iv"] = seed.get("iv")
        if out.get("current_iv_credibility") is None:
            out["current_iv_credibility"] = seed.get("iv_credibility")
        if out.get("current_coverage_rate") is None:
            out["current_coverage_rate"] = seed.get("coverage_rate")
        if out.get("current_signal_strength") is None:
            out["current_signal_strength"] = seed.get("signal_strength")
        if out.get("current_risk_direction") is None:
            out["current_risk_direction"] = seed.get("risk_direction")

        # 初始 iv_history 一条
        if not out.get("iv_history") and seed.get("iv") is not None:
            out["iv_history"] = [{
                "snap_dt": today,
                "iv": seed.get("iv"),
                "credibility": seed.get("iv_credibility", "未做IV分析"),
                "sample_size": seed.get("sample_size_total", 0),
                "project": seed.get("source_project", ""),
            }]

    # 业务字段非空约束 — 给 LLM 明显遗漏的字段添 placeholder
    out.setdefault("biz_definition", "(LLM 未生成 biz_definition,需人审补充)")
    out.setdefault("calc_logic", "(LLM 未生成 calc_logic,需人审补充)")
    out.setdefault("source_tables", [])
    out.setdefault("source_fields", [])

    return out


def normalize_proposals(
    proposals: list[dict[str, Any]],
    cfg: AgentConfig,
    seed_index: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """批量标准化."""
    seed_index = seed_index or {}
    out = []
    for p in proposals:
        # 用 ind_name_cn 反查 seed (用于 IV 等数据回填)
        seed = None
        name_cn = p.get("ind_name_cn", "")
        if name_cn and name_cn in seed_index:
            seed = seed_index[name_cn]
        out.append(fill_defaults(p, cfg, seed))
    return out


__all__ = ["fill_defaults", "normalize_proposals"]
