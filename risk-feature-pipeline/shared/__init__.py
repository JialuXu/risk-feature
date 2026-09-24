# -*- coding: utf-8 -*-
"""DEPRECATION SHIM：`shared` 包是兼容层，下一版本移除。

把 `from shared.X import Y` 透明转发到 `risk_pipeline.X`（它本身也是兼容 shim）。
请改用真实模块：
  - config / config_loader / column_mapper / paths → `risk_core.<模块>`
  - run_generic_pipeline → `risk_mining.pipeline`
  - run_credit_pipeline / run_gsfc_pipeline → `risk_legacy_chains.scripts`
  - 命令行 → `python -m risk_pipeline <子命令>`
"""
import sys
import warnings

warnings.warn(
    "`shared` 是兼容 shim，下一版本移除。请改用："
    "risk_core.config / config_loader / column_mapper / paths；"
    "run_generic_pipeline → risk_mining.pipeline；"
    "run_credit_pipeline / run_gsfc_pipeline → risk_legacy_chains.scripts；"
    "命令行 → python -m risk_pipeline <子命令>。",
    DeprecationWarning,
    stacklevel=2,
)

import risk_pipeline as _rp  # noqa: E402
import risk_pipeline.config  # noqa: E402
import risk_pipeline.config_loader  # noqa: E402
import risk_pipeline.column_mapper  # noqa: E402
import risk_pipeline.pipeline  # noqa: E402

# 让 `import shared.config` / `from shared.config import X` 等同于 risk_pipeline.config
sys.modules['shared.config'] = _rp.config
sys.modules['shared.config_loader'] = _rp.config_loader
sys.modules['shared.column_mapper'] = _rp.column_mapper
sys.modules['shared.pipeline'] = _rp.pipeline
