# -*- coding: utf-8 -*-
"""risk-feature-pipeline 统一 CLI 入口 + 兼容 shim 包（不含任何实现）。

对 agent 暴露的入口 ``python -m risk_pipeline <子命令>`` 不变（``__main__`` 转发
``risk_mining.cli:main``）。其余子模块都是旧导入路径的兼容层，新代码请直接 import 目标：

别名（与目标是同一模块对象，见 ``_alias.py``；按需加载）:
  paths / config / config_loader / column_mapper / io_utils / font_utils / results_loader
                          → risk_core.<同名>
  pipeline_state          → risk_mining.pipeline_state
  analysis.iv_core/engine → risk_mining.analysis.<同名>

再导出:
  pipeline      - run_generic_pipeline（risk_mining.pipeline）+ run_credit/gsfc（risk_legacy_chains）
                  + 旧 ``python -m shared`` 的 argparse 入口 main()
  cli           - risk_mining.cli
  cli_commands  - risk_mining.commands
  cli_io        - risk_core.contracts

依赖方向：risk_core / risk_mining / 各子 skill 均不得 import 本包
（``tests/test_unit_kernel_boundary.py`` 锁定），本包可在下个版本整体删除。
"""
import importlib as _importlib

_SUBMODULES = frozenset({
    'paths', 'config', 'config_loader', 'column_mapper', 'io_utils', 'font_utils',
    'results_loader', 'pipeline_state', 'analysis', 'pipeline', 'cli', 'cli_commands',
    'cli_io',
})


def __getattr__(name):
    """PEP 562：``risk_pipeline.paths`` 式属性访问按需导入子模块（兼容旧的急加载行为）。"""
    if name in _SUBMODULES:
        return _importlib.import_module(f'{__name__}.{name}')
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
