"""加载 default.yaml + .env, 构造 AgentConfig."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from .config import AgentConfig, ApprovalGateConfig, LLMConfig, PathsConfig

_ENV_VAR_PATTERN = re.compile(r"\$\{env:([^,}]+)(?:,([^}]+))?\}")


def _resolve_env(value: Any) -> Any:
    """递归把 ${env:KEY,DEFAULT} 替换成环境变量值."""
    if isinstance(value, str):
        m = _ENV_VAR_PATTERN.fullmatch(value)
        if m:
            return os.getenv(m.group(1), m.group(2) or "")
        return value
    if isinstance(value, dict):
        return {k: _resolve_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env(v) for v in value]
    return value


def load(config_path: str | Path | None = None, project_root: Path | None = None) -> AgentConfig:
    """加载配置. 默认读项目 config/default.yaml."""
    if project_root is None:
        project_root = Path(__file__).resolve().parent.parent

    # 加载 .env
    env_path = project_root / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    # 加载 YAML
    if config_path is None:
        config_path = project_root / "config" / "default.yaml"
    config_path = Path(config_path)
    with config_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    raw = _resolve_env(raw)

    # 构造 dataclass
    paths = PathsConfig(**(raw.get("paths") or {}))
    llm_data = raw.get("llm") or {}
    llm = LLMConfig(
        provider=llm_data.get("provider", "anthropic"),
        model=llm_data.get("model", "claude-sonnet-4-5-20250929"),
        max_tokens=int(llm_data.get("max_tokens", 4096)),
        temperature=float(llm_data.get("temperature", 0.2)),
        retry_attempts=int(llm_data.get("retry_attempts", 3)),
        retry_wait_seconds=list(llm_data.get("retry_wait_seconds", [1, 2, 4])),
        json_strict=bool(llm_data.get("json_strict", True)),
    )
    approval = ApprovalGateConfig(**(raw.get("approval_gate") or {}))

    cfg = AgentConfig(
        paths=paths,
        llm=llm,
        approval_gate=approval,
        upstream=raw.get("upstream") or {},
        step1=raw.get("step1") or {},
        step2=raw.get("step2") or {},
        step3=raw.get("step3") or {},
        step4=raw.get("step4") or {},
        step5=raw.get("step5") or {},
        priority_rules=raw.get("priority_rules") or {},
        defaults=raw.get("defaults") or {},
        logging_cfg=raw.get("logging") or {},
        project_root=project_root,
    )
    return cfg


def load_meta_schema(project_root: Path | None = None) -> dict[str, Any]:
    """加载 meta_schema.yaml."""
    if project_root is None:
        project_root = Path(__file__).resolve().parent.parent
    p = project_root / "config" / "meta_schema.yaml"
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_prompts_routing(project_root: Path | None = None) -> dict[str, Any]:
    """加载 prompts.yaml 路由."""
    if project_root is None:
        project_root = Path(__file__).resolve().parent.parent
    p = project_root / "config" / "prompts.yaml"
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)
