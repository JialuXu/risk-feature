"""异步人审闸口: 写 review packet → 等待 sentinel 文件 (APPROVED / REJECTED)."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Literal

from .config import ApprovalGateConfig

logger = logging.getLogger(__name__)


class ApprovalRejected(Exception):
    """人审拒绝."""


class ApprovalTimeout(Exception):
    """人审超时."""


GateName = Literal["step3", "step5"]


def wait_for_sentinel(
    batch_dir: Path,
    gate: GateName,
    cfg: ApprovalGateConfig,
    auto_approve: bool = False,
) -> str:
    """阻塞等待 sentinel 文件出现.

    返回 'APPROVED' 或 'REJECTED' (后者抛 ApprovalRejected).
    auto_approve=True 时立即返回 APPROVED, 用于自动化测试.
    """
    if auto_approve:
        logger.info("[approval_gate] auto_approve=True, 跳过等待 (gate=%s)", gate)
        return "APPROVED"

    sentinel_cfg = cfg.sentinel_files.get(gate, {})
    approve_name = sentinel_cfg.get("approve", "APPROVED")
    reject_name = sentinel_cfg.get("reject", "REJECTED")

    approve_path = batch_dir / approve_name
    reject_path = batch_dir / reject_name
    timeout_seconds = cfg.timeout_hours * 3600
    start = time.monotonic()

    logger.info("[approval_gate] 等待人审闸口 %s ; 文件: %s 或 %s ; 超时 %sh",
                gate, approve_path, reject_path, cfg.timeout_hours)

    while True:
        if reject_path.exists():
            logger.info("[approval_gate] 检测到 REJECTED")
            raise ApprovalRejected(f"人审拒绝: {reject_path}")
        if approve_path.exists():
            logger.info("[approval_gate] 检测到 APPROVED")
            return "APPROVED"
        if time.monotonic() - start > timeout_seconds:
            raise ApprovalTimeout(
                f"等待 {cfg.timeout_hours} 小时仍未审批 ({approve_path} 不存在)"
            )
        time.sleep(cfg.poll_interval_seconds)


def write_review_packet(
    batch_dir: Path,
    gate: GateName,
    content: str,
    extra_files: dict[str, str] | None = None,
) -> Path:
    """写评审包 markdown 文件 + 额外参考文件."""
    batch_dir.mkdir(parents=True, exist_ok=True)
    review_filename = f"{gate}_review.md"
    review_path = batch_dir / review_filename
    review_path.write_text(content, encoding="utf-8")
    if extra_files:
        for name, body in extra_files.items():
            (batch_dir / name).write_text(body, encoding="utf-8")
    logger.info("[approval_gate] 评审包已写入: %s", review_path)
    return review_path


def clear_sentinels(batch_dir: Path, gate: GateName, cfg: ApprovalGateConfig) -> None:
    """清理旧的 sentinel 文件 (重跑前调用)."""
    sentinel_cfg = cfg.sentinel_files.get(gate, {})
    for name in (sentinel_cfg.get("approve"), sentinel_cfg.get("reject")):
        if not name:
            continue
        p = batch_dir / name
        if p.exists():
            p.unlink()
            logger.info("[approval_gate] 已清理 sentinel: %s", p)
