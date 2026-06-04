# -*- coding: utf-8 -*-
"""兼容 shim：分群逻辑回归实现已与分析引擎合并为单一实现。

历史：本文件曾携带一份与引擎逐字相同的 LR 闭包（lr_by_group / lr_by_qualification /
_fit_lr_single）。现从共享引擎 risk_pipeline.analysis.engine 再导出，消除重复。gsfc
链路通过 _load_module('risk_logistic_regression','group_logistic_regression') 取
lr_by_group，仍照常工作（见 tests/test_unit_lr_dedup.py 的 _load_module 模拟回归）。

新代码请直接：
    from risk_pipeline.analysis.engine import lr_by_group
"""
import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from risk_pipeline.analysis.engine import (  # noqa: F401
    lr_by_group,
    lr_by_qualification,
    _fit_lr_single,
)
