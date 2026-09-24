# -*- coding: utf-8 -*-
"""risk_legacy_chains 内部公共工具：动态子模块加载 + 步骤 banner。

刻意在本 skill 内自带 _load_module / _banner（而非从 risk_pipeline.pipeline 反向
import），以免形成 risk_legacy_chains -> risk_pipeline.pipeline 的回边。
"""
import importlib


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
