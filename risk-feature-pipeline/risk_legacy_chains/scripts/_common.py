# -*- coding: utf-8 -*-
"""risk_legacy_chains 内部公共工具：动态子模块加载 + 步骤 banner。

从 risk_pipeline/pipeline.py 逐字迁出（_load_module / _banner）。刻意在本 skill 内
**复制**这两段（而非从 risk_pipeline.pipeline 反向 import），以免形成
risk_legacy_chains -> risk_pipeline.pipeline 的回边。
"""
import sys
import importlib
from pathlib import Path

# 确保 risk-feature-pipeline/ 在 sys.path 中（本文件在 risk_legacy_chains/scripts/ 下，
# 上溯三级到仓库根），使 _load_module 的 `risk_X.scripts.Y` 限定导入可解析。
_MY_SKILLS_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _MY_SKILLS_ROOT not in sys.path:
    sys.path.insert(0, _MY_SKILLS_ROOT)


def _load_module(skill_name, module_name):
    """从指定 Skill 以**限定名**导入模块（`risk_X.scripts.Y`）。

    例: _load_module('risk_data_prep', 'data_prep')
        等价于: import risk_data_prep.scripts.data_prep
    """
    return importlib.import_module(f'{skill_name}.scripts.{module_name}')


def _banner(step_num, title):
    print(f"\n{'=' * 60}")
    print(f"Step {step_num}: {title}")
    print('=' * 60)
