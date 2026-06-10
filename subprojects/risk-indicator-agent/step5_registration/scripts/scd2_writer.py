"""把 validated + shadow IV 结果写入元表 SCD2."""

from __future__ import annotations

import logging
from typing import Any

from indicator_pipeline.meta_store import MetaStore

logger = logging.getLogger(__name__)


def register_proposals(
    proposals: list[dict[str, Any]],
    store: MetaStore,
    batch_id: str,
) -> dict[str, Any]:
    """逐条 SCD2 写入. 返回统计."""
    stats = {"inserted": 0, "new_version": 0, "soft_update": 0,
             "skipped": 0, "errors": 0}
    error_details: list[dict[str, Any]] = []

    for p in proposals:
        # 跳过 shadow IV 失败的 (可配置)
        status = p.get("shadow_iv_status")
        if status in ("FAIL", "SQL_ERROR"):
            stats["skipped"] += 1
            continue

        # 注册前规范化 lifecycle
        p = dict(p)
        p["lifecycle_status"] = "ACTIVE"

        try:
            action = store.write_scd2(p, batch_id=batch_id)
            stats[action] = stats.get(action, 0) + 1
        except Exception as e:
            stats["errors"] += 1
            error_details.append({
                "ind_code": p.get("ind_code"),
                "error": str(e),
            })
            logger.error("[scd2] 写入 %s 失败: %s", p.get("ind_code"), e)

    return {"stats": stats, "errors": error_details}
