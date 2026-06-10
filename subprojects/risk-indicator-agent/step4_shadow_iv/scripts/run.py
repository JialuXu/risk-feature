"""Step 4 入口."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from indicator_pipeline.config import AgentConfig
from indicator_pipeline.io_utils import read_json, write_json
from indicator_pipeline.pipeline import get_step_input_path, get_step_output_path

from .build_request import build_request_payload, render_sql_skeletons

logger = logging.getLogger(__name__)


def run(batch_id: str, cfg: AgentConfig, **_kwargs: Any) -> dict[str, Any]:
    """跑 Step 4. 出工单 + SQL 骨架. 不执行 SQL."""
    validated_path = get_step_input_path(cfg, batch_id, 4)
    payload = read_json(validated_path)
    proposals: list[dict[str, Any]] = payload.get("proposals", [])
    logger.info("[step4] 读 validated %d 条 from %s", len(proposals), validated_path)

    if not proposals:
        logger.warning("[step4] validated 为空, 不出工单")
        request = build_request_payload(batch_id, [])
        out_path = get_step_output_path(cfg, batch_id, 4)
        write_json(out_path, request)
        return {"step": 4, "batch_id": batch_id, "indicators": 0,
                "output": str(out_path)}

    response_timeout_hours = int(cfg.step4.get("response_timeout_hours", 168))
    submitter = "risk-indicator-agent"

    request = build_request_payload(
        batch_id=batch_id,
        validated_proposals=proposals,
        submitter=submitter,
        response_timeout_hours=response_timeout_hours,
    )
    out_path = get_step_output_path(cfg, batch_id, 4)
    write_json(out_path, request)

    # 渲染 SQL 骨架
    batch_dir = cfg.batch_dir(batch_id)
    skel_dir = batch_dir / "sql_skeletons"
    paths = render_sql_skeletons(cfg.project_root, request["indicators"], skel_dir)
    logger.info("[step4] 渲染 %d 份 SQL 骨架到 %s", len(paths), skel_dir)

    # 写一份 README 给数仓
    readme = (
        f"# 影子 IV 验证工单 · batch={batch_id}\n\n"
        f"- 工单 JSON: `{out_path.name}`\n"
        f"- SQL 骨架: `sql_skeletons/` 下每条指标一个 `.sql` 文件 (仅参考)\n"
        f"- 期望回填: `shadow_iv_response.json` 到本目录, schema 见 "
        f"`step4_shadow_iv/contracts/shadow_iv_response_schema.json`\n\n"
        f"提案数: {len(proposals)}\n"
        f"提交时间: {datetime.now().isoformat(timespec='seconds')}\n"
        f"超时: {response_timeout_hours}h\n"
    )
    (batch_dir / "shadow_iv_README.md").write_text(readme, encoding="utf-8")

    return {
        "step": 4,
        "batch_id": batch_id,
        "indicators": len(proposals),
        "output": str(out_path),
        "sql_skeletons_dir": str(skel_dir),
    }
