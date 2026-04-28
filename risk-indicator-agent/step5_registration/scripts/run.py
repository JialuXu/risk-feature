"""Step 5 入口."""

from __future__ import annotations

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
from indicator_pipeline.io_utils import read_json, write_json
from indicator_pipeline.meta_store import MetaStore
from indicator_pipeline.pipeline import get_step_input_path, get_step_output_path

from step4_shadow_iv.scripts.ingest_response import (
    assign_priority_from_shadow,
    load_response,
    merge_response_into_proposals,
)
from step5_registration.scripts.export_delivery_doc import export_csv, export_docx, export_md
from step5_registration.scripts.prepare_review_packet import render_review_md
from step5_registration.scripts.scd2_writer import register_proposals

logger = logging.getLogger(__name__)


def run(
    batch_id: str,
    cfg: AgentConfig,
    auto_approve: bool = False,
    **_kwargs: Any,
) -> dict[str, Any]:
    """跑 Step 5."""
    # 读 validated (step 3 输出)
    validated_path = get_step_input_path(cfg, batch_id, 5)
    payload = read_json(validated_path)
    proposals: list[dict[str, Any]] = payload.get("proposals", [])
    logger.info("[step5] 读 validated %d 条", len(proposals))

    batch_dir = cfg.batch_dir(batch_id)
    contracts_dir = cfg.project_root / "step4_shadow_iv" / "contracts"

    # 尝试读 shadow_iv_response.json
    response_path = batch_dir / "shadow_iv_response.json"
    response_present = response_path.exists()
    if response_present:
        try:
            response = load_response(response_path, contracts_dir)
            logger.info("[step5] 数仓回填已就绪, %d 条结果",
                        len(response.get("results", [])))
            proposals_with_shadow = merge_response_into_proposals(proposals, response)
        except Exception as e:
            logger.warning("[step5] 数仓回填读取失败,降级 PENDING: %s", e)
            response_present = False
            proposals_with_shadow = [
                {**p, "shadow_iv_status": "PENDING_DATAWAREHOUSE"}
                for p in proposals
            ]
    else:
        logger.warning("[step5] 数仓回填未就绪, 全部以 PENDING_DATAWAREHOUSE 状态注册")
        proposals_with_shadow = [
            {**p, "shadow_iv_status": "PENDING_DATAWAREHOUSE"}
            for p in proposals
        ]

    # 重算 priority
    rules = cfg.priority_rules
    for p in proposals_with_shadow:
        # PENDING 状态保持原 priority (Step 2 给的)
        if p.get("shadow_iv_status") == "SUCCESS":
            p["priority"] = assign_priority_from_shadow(p, rules)

    # 落盘合并后
    write_json(batch_dir / "validated_with_shadow.json", {
        "batch_id": batch_id,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "shadow_response_present": response_present,
        "proposals": proposals_with_shadow,
    })

    # 写 review packet (闸口 2)
    review_md = render_review_md(batch_id, proposals_with_shadow, response_present)
    clear_sentinels(batch_dir, "step5", cfg.approval_gate)
    write_review_packet(batch_dir, "step5", review_md)

    if auto_approve:
        logger.info("[step5] auto_approve=True,跳过人审")
    else:
        try:
            wait_for_sentinel(batch_dir, "step5", cfg.approval_gate, auto_approve=False)
        except ApprovalRejected:
            logger.info("[step5] 人审拒绝,流水线退出")
            write_json(batch_dir / "ERROR_step5_rejected.json", {"batch_id": batch_id})
            raise

    # 元表 SCD2 写入
    store = MetaStore(
        sqlite_path=cfg.abs_path(cfg.paths.meta_sqlite),
        snapshots_dir=cfg.abs_path(cfg.paths.meta_snapshots_dir),
        audit_log=cfg.abs_path(cfg.paths.audit_log),
    )
    reg_result = register_proposals(proposals_with_shadow, store, batch_id)
    logger.info("[step5] 元表写入: %s", reg_result["stats"])

    # 错误明细
    if reg_result["errors"]:
        write_json(batch_dir / "ERROR_step5.json", reg_result["errors"])

    # 交付物导出
    out_dir = cfg.abs_path(cfg.paths.output_dir) / batch_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # 只导出成功注册的 (跳过 FAIL/SQL_ERROR)
    delivered = [p for p in proposals_with_shadow
                 if p.get("shadow_iv_status") not in ("FAIL", "SQL_ERROR")]
    md_path = export_md(out_dir, batch_id, delivered)
    csv_path = export_csv(out_dir, delivered)
    docx_path = export_docx(out_dir, batch_id, delivered)

    final = {
        "step": 5,
        "batch_id": batch_id,
        "registration": reg_result["stats"],
        "registration_errors": len(reg_result["errors"]),
        "shadow_response_present": response_present,
        "delivery_files": {
            "md": str(md_path),
            "csv": str(csv_path),
            "docx": str(docx_path) if docx_path else None,
        },
    }
    write_json(get_step_output_path(cfg, batch_id, 5), final)
    return final
