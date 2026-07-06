# -*- coding: utf-8 -*-
"""risk-feature-pipeline 统一 CLI 入口 + 兼容 shim 包。

解耦重构（DECOUPLING-DESIGN §4，阶段 1）：稳定契约底座已抽入 ``risk_core``。
本包用**模块别名**把旧导入路径透明转发到 risk_core：
``import risk_pipeline.paths`` 与 ``risk_core.paths`` 是**同一模块对象**
（``import risk_pipeline.paths is risk_core.paths`` 为 True），私有名（如
``paths._warned_no_data_dir``）亦可达——这是 ``import *`` 做不到、而 20+ 测试
依赖的性质。

已退化为 shim 的子模块（转发到组合根 risk_mining）:
  cli           - 转发 risk_mining.cli（统一 CLI 入口，阶段 2）
  cli_commands  - 转发 risk_mining.commands（9 子命令实现，阶段 2）
  cli_io        - 转发 risk_core.contracts（wire/指纹/features.json，阶段 1）

仍物理留在本包的挖掘内核（下阶段迁移）:
  pipeline       - run_credit / run_gsfc / run_generic_pipeline
  pipeline_state - Level 状态机
  analysis       - 共享分析内核（iv_core / engine）

已升入 risk_core 的子模块（经下面的别名转发）:
  paths / config / config_loader / column_mapper / io_utils / font_utils / results_loader
"""
import sys as _sys

from risk_core import (  # noqa: F401  同一对象转发到 risk_core
    paths,
    config,
    config_loader,
    column_mapper,
    io_utils,
    font_utils,
    results_loader,
)

# 逐子模块登记别名：让 `import risk_pipeline.X` / `from risk_pipeline.X import Y`
# 解析到与 risk_core.X 完全相同的模块对象（保证私有名与身份判等一致）。
for _name in (
    'paths', 'config', 'config_loader', 'column_mapper',
    'io_utils', 'font_utils', 'results_loader',
):
    _sys.modules[f'{__name__}.{_name}'] = _sys.modules[f'risk_core.{_name}']
del _sys, _name
