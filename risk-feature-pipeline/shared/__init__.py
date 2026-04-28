# -*- coding: utf-8 -*-
"""DEPRECATION SHIM：`shared` 包已重命名为 `risk_pipeline`。

本文件作为兼容层，把 `from shared.X import Y` 透明转发到 `risk_pipeline.X`。
下一版本会移除此 shim，请尽快把 import 改为 `from risk_pipeline.X import Y`。
"""
import sys
import warnings

warnings.warn(
    "`shared` 包已重命名为 `risk_pipeline`；请改用 `from risk_pipeline.X import Y`。"
    "兼容 shim 仅作为过渡，下一版本会移除。",
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
