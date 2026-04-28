"""加载 prompts/*.md 模板, 渲染 {var} 占位符."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .config_loader import load_prompts_routing

_VAR_PATTERN = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


class PromptError(Exception):
    pass


def load_prompt(prompt_filename: str, project_root: Path | None = None) -> str:
    """读 prompts/{filename} 原文."""
    if project_root is None:
        project_root = Path(__file__).resolve().parent.parent
    p = project_root / "prompts" / prompt_filename
    if not p.exists():
        raise PromptError(f"prompt 文件不存在: {p}")
    return p.read_text(encoding="utf-8")


def render_prompt(template: str, variables: dict[str, Any], strict: bool = True) -> str:
    """{var} 替换. strict=True 时未提供变量直接报错."""
    used: set[str] = set()

    def _replace(m: re.Match[str]) -> str:
        key = m.group(1)
        used.add(key)
        if key not in variables:
            if strict:
                raise PromptError(f"prompt 模板需要变量 '{key}', 但未在 variables 中提供")
            return m.group(0)
        v = variables[key]
        if isinstance(v, (dict, list)):
            import json
            return json.dumps(v, ensure_ascii=False, indent=2)
        return str(v)

    rendered = _VAR_PATTERN.sub(_replace, template)
    if strict:
        unused = set(variables.keys()) - used
        if unused:
            # 不抛错,但警告 (变量提供过多通常是上游迭代后有遗留)
            import logging
            logging.getLogger(__name__).debug("prompt 渲染时有未用变量: %s", unused)
    return rendered


def load_and_render(prompt_filename: str, variables: dict[str, Any],
                    project_root: Path | None = None) -> str:
    """便捷函数: 加载 + 渲染."""
    return render_prompt(load_prompt(prompt_filename, project_root), variables)


def get_prompt_path(step: str, key: str, project_root: Path | None = None) -> str:
    """从 prompts.yaml 路由表取出文件名."""
    routing = load_prompts_routing(project_root)
    section = routing.get(step) or {}
    if isinstance(section, dict) and key in section:
        v = section[key]
        if isinstance(v, str):
            return v
    raise PromptError(f"prompts.yaml 中无路由 {step}.{key}")
