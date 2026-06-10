"""关 6: LLM 语义级查重 + 业务方向合理性检查."""

from __future__ import annotations

import json
import logging
from typing import Any

from indicator_pipeline.dedup import find_top_similar
from indicator_pipeline.llm_client import BaseLLMClient
from indicator_pipeline.prompt_loader import load_prompt, render_prompt

from . import CheckResult

logger = logging.getLogger(__name__)


def check(proposal: dict[str, Any], ctx: dict[str, Any]) -> CheckResult:
    """LLM 语义关. 仅在配置 `enabled=True` 且 LLM 客户端可用时跑."""
    enabled = ctx.get("semantic_check_enabled", True)
    if not enabled:
        return CheckResult(check_name="semantic_llm", passed=True,
                          warnings=["语义关已关闭"])

    client: BaseLLMClient | None = ctx.get("llm_client")
    if client is None:
        return CheckResult(check_name="semantic_llm", passed=True,
                          warnings=["LLM client 未提供, 跳过语义关"])

    project_root = ctx.get("project_root")
    existing_active: list[dict[str, Any]] = ctx.get("existing_active", [])
    top_k = int(ctx.get("similar_top_k", 5))

    # 限定到同 domain
    domain = proposal.get("domain", "")
    same_domain = [r for r in existing_active if r.get("domain") == domain]
    if not same_domain:
        return CheckResult(check_name="semantic_llm", passed=True,
                          warnings=[f"元表 {domain} 域无已有指标, 跳过"])

    candidate_text = (
        f"{proposal.get('ind_name_cn','')} {proposal.get('biz_definition','')}"
    )
    pairs = [(r["ind_code"], r["ind_name_cn"] or "") for r in same_domain]
    top_similar_codes = find_top_similar(candidate_text, pairs, top_k=top_k)
    top_similar = []
    for code, _name, score in top_similar_codes:
        rec = next((r for r in same_domain if r["ind_code"] == code), None)
        if rec:
            top_similar.append({
                "ind_code": rec["ind_code"],
                "ind_name_cn": rec["ind_name_cn"],
                "biz_definition": rec.get("biz_definition", ""),
                "calc_logic": rec.get("calc_logic", ""),
                "fuzz_score": round(score, 1),
            })

    if not top_similar:
        return CheckResult(check_name="semantic_llm", passed=True)

    # 调 LLM
    sys_prompt = load_prompt("step3_semantic_system.md", project_root)
    user_template = load_prompt("step3_semantic_user_template.md", project_root)

    candidate_brief = {
        "ind_code": proposal.get("ind_code"),
        "ind_name_cn": proposal.get("ind_name_cn"),
        "biz_definition": proposal.get("biz_definition"),
        "calc_logic": proposal.get("calc_logic"),
        "domain": proposal.get("domain"),
        "current_risk_direction": proposal.get("current_risk_direction"),
        "current_iv": proposal.get("current_iv"),
    }
    user_prompt = render_prompt(user_template, {
        "candidate_json": json.dumps(candidate_brief, ensure_ascii=False, indent=2),
        "similar_existing_json": json.dumps(top_similar, ensure_ascii=False, indent=2),
        "top_k": top_k,
    })

    try:
        result = client.generate(system=sys_prompt, user=user_prompt,
                                response_schema={"type": "object"})
    except Exception as e:
        logger.warning("LLM 语义关调用失败: %s", e)
        return CheckResult(check_name="semantic_llm", passed=True,
                          warnings=[f"LLM 调用失败,跳过语义关: {e}"])

    if not isinstance(result, dict):
        return CheckResult(check_name="semantic_llm", passed=True,
                          warnings=["LLM 返回非对象,跳过"])

    is_dup = bool(result.get("is_semantic_duplicate", False))
    concerns = result.get("concerns") or []
    quality = result.get("biz_definition_quality", "")
    direction_ok = bool(result.get("risk_direction_consistent", True))

    errors = []
    warnings = []

    if is_dup:
        errors.append(
            f"LLM 判定语义重复 → {result.get('duplicate_of', '')}"
            f": {result.get('duplicate_reason', '')}"
        )

    if quality == "unclear":
        warnings.append("业务口径表述不清晰,建议人审补充")

    if not direction_ok:
        warnings.append("LLM 判定风险方向与业务直觉不符,建议人审")

    for c in concerns:
        warnings.append(f"LLM 关注点: {c}")

    return CheckResult(
        check_name="semantic_llm",
        passed=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        extra={"llm_result": result, "top_similar": top_similar[:3]},
    )
