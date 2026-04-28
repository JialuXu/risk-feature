"""强类型配置 dataclass."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class LLMConfig:
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-5-20250929"
    max_tokens: int = 4096
    temperature: float = 0.2
    retry_attempts: int = 3
    retry_wait_seconds: list[int] = field(default_factory=lambda: [1, 2, 4])
    json_strict: bool = True


@dataclass
class PathsConfig:
    data_root: str = "data"
    raw_dir: str = "data/raw"
    processed_dir: str = "data/processed"
    meta_store_dir: str = "data/meta_store"
    meta_sqlite: str = "data/meta_store/indicator_meta.sqlite"
    meta_snapshots_dir: str = "data/meta_store/snapshots"
    audit_log: str = "data/meta_store/audit.log"
    results_dir: str = "data/results"
    output_dir: str = "output"
    references_dir: str = "references"
    prompts_dir: str = "prompts"


@dataclass
class ApprovalGateConfig:
    poll_interval_seconds: int = 5
    timeout_hours: int = 24
    sentinel_files: dict[str, dict[str, str]] = field(
        default_factory=lambda: {
            "step3": {"approve": "APPROVED", "reject": "REJECTED"},
            "step5": {"approve": "STEP5_APPROVED", "reject": "STEP5_REJECTED"},
        }
    )


@dataclass
class AgentConfig:
    """聚合所有配置. 由 config_loader.load() 构造."""
    paths: PathsConfig = field(default_factory=PathsConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    approval_gate: ApprovalGateConfig = field(default_factory=ApprovalGateConfig)
    upstream: dict[str, Any] = field(default_factory=dict)
    step1: dict[str, Any] = field(default_factory=dict)
    step2: dict[str, Any] = field(default_factory=dict)
    step3: dict[str, Any] = field(default_factory=dict)
    step4: dict[str, Any] = field(default_factory=dict)
    step5: dict[str, Any] = field(default_factory=dict)
    priority_rules: dict[str, Any] = field(default_factory=dict)
    defaults: dict[str, Any] = field(default_factory=dict)
    logging_cfg: dict[str, Any] = field(default_factory=dict)

    project_root: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent)

    def abs_path(self, rel: str) -> Path:
        """把配置中的相对路径转成绝对路径."""
        p = Path(rel)
        return p if p.is_absolute() else self.project_root / p

    def batch_dir(self, batch_id: str) -> Path:
        """返回 data/processed/{batch_id}/."""
        return self.abs_path(self.paths.processed_dir) / batch_id
