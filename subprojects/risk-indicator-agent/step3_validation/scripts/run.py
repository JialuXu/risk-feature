"""Step 3 入口. 6 道关串行 + 写评审包 + 闸口 1."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from indicator_pipeline.approval_gate import (
    ApprovalRejected,
    clear_sentinels,
    wait_for_sentinel,
    write_review_packet,
)
from indicator_pipeline.config import AgentConfig
from indicator_pipeline.field_dict import load_default_field_dict
from indicator_pipeline.io_utils import read_json, write_json
from indicator_pipeline.llm_client import BaseLLMClient, build_client
from indicator_pipeline.meta_store import MetaStore
from indicator_pipeline.pipeline import get_step_input_path, get_step_output_path

from .checks import CheckResult
from .checks import calc_logic, dedup, field_existence, naming, schema, semantic_llm

logger = logging.getLogger(__name__)


_CHECK_ORDER = [
    ("naming", naming.check),
    ("schema", schema.check),
    ("field_existence", field_existence.check),
    ("dedup", dedup.check),
    ("calc_logic", calc_logic.check),
    ("semantic_llm", semantic_llm.check),
]


def run(
    batch_id: str,
    cfg: AgentConfig,
    llm_client: BaseLLMClient | None = None,
    auto_approve: bool = False,
    skip_semantic_llm: bool = False,
    **_kwargs: Any,
) -> dict[str, Any]:
    """跑 6 道关 + 写评审包 + 等闸口."""
    proposals_path = get_step_input_path(cfg, batch_id, 3)
    payload = read_json(proposals_path)
    proposals: list[dict[str, Any]] = payload.get("proposals", [])
    logger.info("[step3] 读 %d 条提案 from %s", len(proposals), proposals_path)

    batch_dir = cfg.batch_dir(batch_id)
    batch_dir.mkdir(parents=True, exist_ok=True)
    clear_sentinels(batch_dir, "step3", cfg.approval_gate)

    if not proposals:
        logger.warning("[step3] 提案为空, 跳过校验")
        write_json(batch_dir / "validated.json", {"batch_id": batch_id, "proposals": []})
        write_json(batch_dir / "rejected.json", {"batch_id": batch_id, "proposals": []})
        write_json(batch_dir / "validation_report.json",
                   {"batch_id": batch_id, "details": [], "stats": {}})
        return {"step": 3, "batch_id": batch_id, "validated": 0, "rejected": 0}

    # 准备 ctx
    fd = load_default_field_dict(cfg.project_root)
    meta_store = MetaStore(
        sqlite_path=cfg.abs_path(cfg.paths.meta_sqlite),
        snapshots_dir=cfg.abs_path(cfg.paths.meta_snapshots_dir),
        audit_log=cfg.abs_path(cfg.paths.audit_log),
    )
    existing_active = meta_store.list_active()
    existing_pairs = [(r["ind_code"], r.get("ind_name_cn") or "") for r in existing_active]

    if llm_client is None and not skip_semantic_llm and cfg.step3.get("semantic_check", {}).get("enabled", True):
        try:
            llm_client = build_client(cfg.llm)
        except Exception as e:
            logger.warning("[step3] LLM client 初始化失败,跳过语义关: %s", e)
            llm_client = None

    ctx = {
        "project_root": cfg.project_root,
        "field_dict": fd,
        "existing_pairs": existing_pairs,
        "existing_active": existing_active,
        "dedup_threshold": cfg.step3.get("dedup", {}).get("threshold", 85),
        "dedup_method": cfg.step3.get("dedup", {}).get("fuzz_method", "token_set_ratio"),
        "semantic_check_enabled": (not skip_semantic_llm) and bool(
            cfg.step3.get("semantic_check", {}).get("enabled", True)
        ),
        "similar_top_k": cfg.step3.get("semantic_check", {}).get("similar_top_k", 5),
        "llm_client": llm_client,
    }

    validated: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    details: list[dict[str, Any]] = []

    for idx, prop in enumerate(proposals):
        per_proposal_results: list[CheckResult] = []
        rejected_at: str | None = None
        for check_name, fn in _CHECK_ORDER:
            r = fn(prop, ctx)
            per_proposal_results.append(r)
            if not r.passed and rejected_at is None:
                rejected_at = check_name
                # 短路: 后续关仍跑以收集 warnings 信息

        all_errors = sum((r.errors for r in per_proposal_results), [])
        all_warnings = sum((r.warnings for r in per_proposal_results), [])
        detail = {
            "index": idx,
            "ind_code": prop.get("ind_code"),
            "ind_name_cn": prop.get("ind_name_cn"),
            "domain": prop.get("domain"),
            "passed": rejected_at is None,
            "rejected_at": rejected_at,
            "errors": all_errors,
            "warnings": all_warnings,
            "checks": [
                {"check": r.check_name, "passed": r.passed,
                 "errors": r.errors, "warnings": r.warnings}
                for r in per_proposal_results
            ],
        }
        details.append(detail)

        if rejected_at is None:
            validated.append(prop)
        else:
            prop_with_reason = dict(prop)
            prop_with_reason["_rejection"] = {
                "rejected_at": rejected_at,
                "errors": all_errors,
                "warnings": all_warnings,
            }
            rejected.append(prop_with_reason)

    stats = {
        "input": len(proposals),
        "validated": len(validated),
        "rejected": len(rejected),
        "rejection_rate": round(len(rejected) / len(proposals), 3) if proposals else 0,
        "rejected_by_check": _count_rejected_by_check(details),
    }
    logger.info("[step3] 校验完成: %s", stats)

    # 写 3 份产物
    write_json(batch_dir / "validated.json",
               {"batch_id": batch_id, "stats": stats,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "proposals": validated})
    write_json(batch_dir / "rejected.json",
               {"batch_id": batch_id, "stats": stats, "proposals": rejected})
    write_json(batch_dir / "validation_report.json",
               {"batch_id": batch_id, "stats": stats, "details": details})

    # 写 review packet
    review_md = _render_review_md(batch_id, stats, validated, rejected, details)
    write_review_packet(batch_dir, "step3", review_md)

    # 拒绝率超阈值告警
    max_rej = cfg.step3.get("rejection_threshold", {}).get("max_rejected_ratio", 0.5)
    if stats["rejection_rate"] > max_rej:
        logger.warning("[step3] 拒绝率 %.1f%% 超过阈值 %.1f%%, 建议重做整批",
                       stats["rejection_rate"] * 100, max_rej * 100)

    # 等闸口 1
    if auto_approve:
        logger.info("[step3] auto_approve=True, 跳过人审")
    else:
        try:
            wait_for_sentinel(batch_dir, "step3", cfg.approval_gate, auto_approve=False)
        except ApprovalRejected:
            logger.info("[step3] 人审拒绝,流水线退出")
            write_json(batch_dir / "ERROR_step3_rejected.json", {"batch_id": batch_id})
            raise

    # 同时把 step5 sentinel 也清一下,避免误触
    clear_sentinels(batch_dir, "step5", cfg.approval_gate)

    out_path = get_step_output_path(cfg, batch_id, 3)
    return {"step": 3, "batch_id": batch_id, "output": str(out_path), "stats": stats}


def _count_rejected_by_check(details: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for d in details:
        if d["rejected_at"]:
            out[d["rejected_at"]] = out.get(d["rejected_at"], 0) + 1
    return out


def _render_review_md(batch_id: str, stats: dict[str, Any],
                       validated: list[dict[str, Any]],
                       rejected: list[dict[str, Any]],
                       details: list[dict[str, Any]]) -> str:
    """渲染人审 markdown 文档."""
    lines = [
        f"# Step 3 评审包 · batch={batch_id}",
        "",
        f"生成时间: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## 概览",
        "",
        f"- 输入提案: **{stats['input']}**",
        f"- 通过: **{stats['validated']}** ({(stats['validated']/stats['input']*100 if stats['input'] else 0):.1f}%)",
        f"- 拒绝: **{stats['rejected']}** ({stats['rejection_rate']*100:.1f}%)",
        "",
        "### 拒绝原因分布",
        "",
        "| 关 | 拒绝数 |",
        "|---|---|",
    ]
    for k, v in stats.get("rejected_by_check", {}).items():
        lines.append(f"| {k} | {v} |")
    lines.append("")

    # 通过的
    lines.append(f"## 通过的提案 ({len(validated)})")
    lines.append("")
    if not validated:
        lines.append("(无)")
    for d in details:
        if d["passed"]:
            lines.append(f"### `{d['ind_code']}` — {d['ind_name_cn']} [{d['domain']}]")
            if d["warnings"]:
                lines.append("")
                lines.append("**Warnings:**")
                for w in d["warnings"]:
                    lines.append(f"- {w}")
            lines.append("")

    # 拒绝的
    lines.append(f"## 被拒提案 ({len(rejected)})")
    lines.append("")
    if not rejected:
        lines.append("(无)")
    for d in details:
        if not d["passed"]:
            lines.append(f"### ❌ `{d['ind_code']}` — {d['ind_name_cn']} [{d['domain']}]")
            lines.append(f"在 **{d['rejected_at']}** 关被拒")
            lines.append("")
            for e in d["errors"]:
                lines.append(f"- ❌ {e}")
            for w in d["warnings"]:
                lines.append(f"- ⚠️ {w}")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 审批操作")
    lines.append("")
    lines.append("```bash")
    lines.append(f"# 通过 (后续进 Step 4):")
    lines.append(f"touch data/processed/{batch_id}/APPROVED")
    lines.append("")
    lines.append(f"# 拒绝 (流水线退出):")
    lines.append(f"touch data/processed/{batch_id}/REJECTED")
    lines.append("```")
    lines.append("")
    lines.append("如需修改提案集,直接编辑 `validated.json` 后再 APPROVED.")
    return "\n".join(lines)
