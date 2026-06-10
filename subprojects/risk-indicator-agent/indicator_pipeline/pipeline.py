"""5 步状态机. 每步从上一步 JSON 读 → 处理 → 写下一步 JSON.

每步对应一个独立子 Skill 的 run.py (动态 import).
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any

from .config import AgentConfig
from .config_loader import load
from .io_utils import read_json, write_json

logger = logging.getLogger(__name__)


_STEP_MODULES = {
    1: "step1_candidate_screening.scripts.run",
    2: "step2_llm_proposal.scripts.run",
    3: "step3_validation.scripts.run",
    4: "step4_shadow_iv.scripts.run",
    5: "step5_registration.scripts.run",
}


def run_step(step: int, batch_id: str, cfg: AgentConfig | None = None,
             **kwargs: Any) -> dict[str, Any]:
    """跑流水线某一步. 各子 Skill run.py 必须定义 run(batch_id, cfg, **kwargs) -> dict."""
    if step not in _STEP_MODULES:
        raise ValueError(f"step 必须在 {sorted(_STEP_MODULES)}, got {step}")
    if cfg is None:
        cfg = load()
    module_name = _STEP_MODULES[step]
    logger.info("[pipeline] 进入 step %s (module=%s, batch=%s)", step, module_name, batch_id)
    mod = importlib.import_module(module_name)
    if not hasattr(mod, "run"):
        raise RuntimeError(f"{module_name} 缺少 run() 函数")
    result = mod.run(batch_id=batch_id, cfg=cfg, **kwargs)
    logger.info("[pipeline] step %s 完成", step)
    return result


def get_batch_dir(cfg: AgentConfig, batch_id: str) -> Path:
    return cfg.batch_dir(batch_id)


def get_step_input_path(cfg: AgentConfig, batch_id: str, step: int) -> Path:
    """约定: step N 的输入是 step N-1 的标准输出."""
    batch_dir = get_batch_dir(cfg, batch_id)
    return {
        2: batch_dir / "seeds.json",
        3: batch_dir / "proposals_draft.json",
        4: batch_dir / "validated.json",
        5: batch_dir / "validated.json",  # step 5 同时读 validated + shadow_iv_response
    }.get(step, batch_dir / f"step{step}_input.json")


def get_step_output_path(cfg: AgentConfig, batch_id: str, step: int) -> Path:
    batch_dir = get_batch_dir(cfg, batch_id)
    return {
        1: batch_dir / "seeds.json",
        2: batch_dir / "proposals_draft.json",
        3: batch_dir / "validated.json",
        4: batch_dir / "shadow_iv_request.json",
        5: batch_dir / "step5_result.json",
    }.get(step, batch_dir / f"step{step}_output.json")


def load_step_input(cfg: AgentConfig, batch_id: str, step: int) -> Any:
    return read_json(get_step_input_path(cfg, batch_id, step))


def save_step_output(cfg: AgentConfig, batch_id: str, step: int, payload: Any) -> Path:
    path = get_step_output_path(cfg, batch_id, step)
    write_json(path, payload)
    return path
