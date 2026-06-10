"""人审闸口单测."""

import time
from threading import Thread
from pathlib import Path

import pytest

from indicator_pipeline.approval_gate import (
    ApprovalRejected,
    ApprovalTimeout,
    clear_sentinels,
    wait_for_sentinel,
    write_review_packet,
)
from indicator_pipeline.config import ApprovalGateConfig


def _make_cfg() -> ApprovalGateConfig:
    return ApprovalGateConfig(poll_interval_seconds=0.1, timeout_hours=1)


def test_auto_approve(tmp_batch_dir):
    cfg = _make_cfg()
    result = wait_for_sentinel(tmp_batch_dir, "step3", cfg, auto_approve=True)
    assert result == "APPROVED"


def test_approve_via_sentinel(tmp_batch_dir):
    cfg = _make_cfg()
    # 后台线程 0.2s 后 touch APPROVED
    def _later():
        time.sleep(0.2)
        (tmp_batch_dir / "APPROVED").touch()
    Thread(target=_later, daemon=True).start()
    result = wait_for_sentinel(tmp_batch_dir, "step3", cfg)
    assert result == "APPROVED"


def test_reject(tmp_batch_dir):
    cfg = _make_cfg()
    (tmp_batch_dir / "REJECTED").touch()
    with pytest.raises(ApprovalRejected):
        wait_for_sentinel(tmp_batch_dir, "step3", cfg)


def test_write_review_packet(tmp_batch_dir):
    p = write_review_packet(tmp_batch_dir, "step3", "# Review\n\ndetails")
    assert p.exists()
    assert "Review" in p.read_text(encoding="utf-8")


def test_clear_sentinels(tmp_batch_dir):
    cfg = _make_cfg()
    (tmp_batch_dir / "APPROVED").touch()
    (tmp_batch_dir / "REJECTED").touch()
    clear_sentinels(tmp_batch_dir, "step3", cfg)
    assert not (tmp_batch_dir / "APPROVED").exists()
    assert not (tmp_batch_dir / "REJECTED").exists()
