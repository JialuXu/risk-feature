# -*- coding: utf-8 -*-
"""解耦重构批次 B（阶段 6/7）不变量锁：独立子 skill 只依赖 risk_core。

对 INDEPENDENT_SKILLS 里的每个 skill 锁两件事（模式沿用阶段 5 首拆样板
test_unit_result_query_standalone，result_query 的锁在那个文件里）：
  1. **AST 红线**：skill 全部 .py 的绝对 import 不得出现 risk_pipeline /
     risk_mining / shared / 其它 risk_* 子 skill——只许 stdlib、三方库、
     risk_core 与自身相对 import。含函数体内的延迟 import。
  2. **进程级 import 隔离**：全新子进程 import 该 skill 的**每一个模块**后，
     sys.modules 不得出现 risk_pipeline / risk_mining / shared——证明 skill
     可在不加载挖掘内核与组合根的前提下独立加载（模块顶层代码真实执行，
     兜住 AST 抓不到的 import 时序问题）。

随阶段 6/7 逐 skill 接入：拆完一个，把名字加进 INDEPENDENT_SKILLS。
全部拆完后，本文件即两条 grep 红线中「子 skill 零横向 import」的机器化版本。
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# 已完成独立化的子 skill（阶段 6b: data_prep；6c: trigger；6d: docx；7: vis/threshold）
INDEPENDENT_SKILLS = [
    'risk_data_prep',
    'risk_trigger_extraction',
    'risk_docx_report',
    'risk_visualization',
    'risk_threshold_explore',
]


def _iter_py(root: Path):
    for py in root.rglob('*.py'):
        if '__pycache__' not in py.parts:
            yield py


def _abs_imports(py_path: Path):
    tree = ast.parse(py_path.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                yield node.module


@pytest.mark.parametrize('skill', INDEPENDENT_SKILLS)
def test_skill_imports_only_risk_core(skill):
    offenders = []
    for py in _iter_py(REPO_ROOT / skill):
        for mod in _abs_imports(py):
            top = mod.split('.')[0]
            if top == 'shared' or (
                top.startswith('risk_') and top not in ('risk_core', skill)
            ):
                offenders.append(f'{py.relative_to(REPO_ROOT)}: import {mod}')
    assert not offenders, (
        f'{skill} 出现 risk_core 之外的项目内 import（独立性破坏）：\n'
        + '\n'.join(offenders)
    )


@pytest.mark.parametrize('skill', INDEPENDENT_SKILLS)
def test_skill_import_isolation(skill):
    """子进程 import 该 skill 全部模块 → sys.modules 无内核/组合根/shared 污染。"""
    modules = []
    for py in _iter_py(REPO_ROOT / skill):
        rel = py.relative_to(REPO_ROOT).with_suffix('')
        parts = rel.parts
        if parts[-1] == '__init__':
            parts = parts[:-1]
        if parts[-1] == '__main__':
            continue  # python -m 入口不在裸 import 之列
        modules.append('.'.join(parts))
    assert modules, f'{skill} 下没找到任何模块？'

    code = (
        'import sys\n'
        + '\n'.join(f'import {m}' for m in sorted(modules))
        + '\n'
        "bad = sorted({m.split('.')[0] for m in sys.modules\n"
        "              if m.split('.')[0] in ('risk_pipeline', 'risk_mining', 'shared')})\n"
        "assert not bad, f'import 全部模块后被污染: {bad}'\n"
    )
    proc = subprocess.run(
        [sys.executable, '-c', code],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, (
        f'{skill} 进程级隔离验证失败：\n{proc.stderr}'
    )
