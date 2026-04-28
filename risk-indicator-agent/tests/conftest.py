"""共享 fixtures: MockLLM + 临时元表 + 临时 batch 目录."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

# 把项目根加入 sys.path 以便 import indicator_pipeline / step*
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# 防止真实 LLM 调用
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-disabled")


@pytest.fixture
def project_root() -> Path:
    return _PROJECT_ROOT


@pytest.fixture
def tmp_batch_dir(tmp_path: Path) -> Path:
    """临时 batch 工作目录."""
    d = tmp_path / "data" / "processed" / "test_batch"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def tmp_meta_store(tmp_path: Path):
    """临时 SQLite 元表."""
    from indicator_pipeline.meta_store import MetaStore
    store = MetaStore(
        sqlite_path=tmp_path / "meta.sqlite",
        snapshots_dir=tmp_path / "snap",
        audit_log=tmp_path / "audit.log",
    )
    return store


@pytest.fixture
def tmp_cfg(tmp_path: Path):
    """临时 AgentConfig (data_root 重定向到 tmp_path)."""
    from indicator_pipeline.config_loader import load
    cfg = load()
    # 重定向数据路径到 tmp_path
    cfg.paths.data_root = str(tmp_path / "data")
    cfg.paths.raw_dir = str(tmp_path / "data" / "raw")
    cfg.paths.processed_dir = str(tmp_path / "data" / "processed")
    cfg.paths.meta_store_dir = str(tmp_path / "data" / "meta_store")
    cfg.paths.meta_sqlite = str(tmp_path / "data" / "meta_store" / "indicator_meta.sqlite")
    cfg.paths.meta_snapshots_dir = str(tmp_path / "data" / "meta_store" / "snapshots")
    cfg.paths.audit_log = str(tmp_path / "data" / "meta_store" / "audit.log")
    cfg.paths.output_dir = str(tmp_path / "output")
    # 关闭 LLM 语义关 (默认测试不调真实 API)
    cfg.step3.setdefault("semantic_check", {})["enabled"] = False
    # 减少超时,加速测试
    cfg.approval_gate.timeout_hours = 1
    cfg.approval_gate.poll_interval_seconds = 1
    return cfg


# ============================================================================
# MockLLM
# ============================================================================


class MockLLM:
    """根据 ind_name_cn 返回预录的提案 JSON."""

    def __init__(self, recorded: dict[str, Any] | None = None):
        # recorded: dict { "domain": [proposal, ...] } —— 按 domain 返回
        self.recorded = recorded or {}
        self.calls: list[dict[str, Any]] = []

    @property
    def cfg(self):
        from indicator_pipeline.config import LLMConfig
        return LLMConfig()

    def generate(self, system: str, user: str,
                 response_schema: Any = None,
                 max_tokens: int | None = None,
                 temperature: float | None = None) -> Any:
        self.calls.append({"system": system[:80], "user": user[:200],
                           "schema": response_schema})
        # 简易识别 domain (从 user prompt 中找 "domain": "X")
        domain = self._guess_domain(user)
        if response_schema and isinstance(response_schema, dict):
            t = response_schema.get("type")
            if t == "array":
                return self.recorded.get(domain, [])
            if t == "object":
                # 语义关默认: 不重复
                return {
                    "is_semantic_duplicate": False,
                    "duplicate_of": None,
                    "duplicate_reason": "mock: no dup",
                    "biz_definition_quality": "good",
                    "risk_direction_consistent": True,
                    "concerns": [],
                }
        return ""

    def _guess_domain(self, user_prompt: str) -> str:
        for d in ["FIN", "CRDTC", "OPN", "PUB"]:
            if f'"domain": "{d}"' in user_prompt or f"## {d} 域" in user_prompt:
                return d
        return "UNKNOWN"


@pytest.fixture
def mock_llm() -> MockLLM:
    """默认 MockLLM (空回放). 测试可以 monkeypatch 它的 recorded."""
    return MockLLM()


@pytest.fixture
def mock_llm_with_proposals() -> MockLLM:
    """带预录 4 个域提案的 MockLLM, 用于 e2e."""
    proposals = {
        "CRDTC": [_make_proposal(
            "CRDTC_M_GUARQRY_UNPAYOFF_SNAP_RATIO",
            "担保查询未结清比",
            "CRDTC",
            "担保人征信查询次数与信贷未结清机构数之比, 反映融资行为",
            "GUAR_QRY_CNT / NULLIF(UNPAYOFF_ORG_CNT, 0)",
            ["DEMO_CORP_CREDIT_REPORT", "DEMO_CORP_CREDIT_REPORT_EXT"],
            ["DEMO_CORP_CREDIT_REPORT.GUAR_QRY_CNT(担保人征信查询次数)",
             "DEMO_CORP_CREDIT_REPORT_EXT.UNPAYOFF_ORG_CNT(信贷交易未结清总机构数)"],
            "P0",
        )],
        "PUB": [_make_proposal(
            "PUB_M_TAG_OVDUE_M12_CNT",
            "风险标签_信贷逾期_数量",
            "PUB",
            "近 12 月信贷逾期类舆情条数",
            "COUNT(*) WHERE TAG_NAME='信贷逾期' AND PUB_TIME ∈ M12",
            ["DEMO_CORP_PUBLIC_OPINION"],
            ["DEMO_CORP_PUBLIC_OPINION.TAG_NAME(风险标签)",
             "DEMO_CORP_PUBLIC_OPINION.PUB_TIME(发布时间)"],
            "P2",
            window="M12",
        )],
        "OPN": [],
        "FIN": [],
    }
    return MockLLM(recorded=proposals)


def _make_proposal(code: str, name_cn: str, domain: str, biz: str,
                   calc: str, tables: list[str], fields: list[str],
                   priority: str, window: str = "SNAP") -> dict:
    return {
        "ind_code": code,
        "ind_version": 1,
        "ind_name_cn": name_cn,
        "domain": domain,
        "granularity": "M",
        "window": window,
        "value_type": "RATIO" if "RATIO" in code else "NUM",
        "biz_definition": biz,
        "calc_logic": calc,
        "source_tables": tables,
        "source_fields": fields,
        "priority": priority,
        "lifecycle_status": "DRAFT",
        "proposer": "LLM_AGENT",
        "owner": "RISK_TEAM",
        "is_dynamic_expansion": 0,
        "ref_date_logic": "BATCH_MAX",
        "post_processing_rule": "PAD_ZERO_ON_LEFT_JOIN" if domain in ("OPN", "PUB") else "KEEP_NULL_ON_LEFT_JOIN",
        "eff_dt": "2026-04-28",
        "exp_dt": "9999-12-31",
    }
