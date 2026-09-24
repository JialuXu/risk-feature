# -*- coding: utf-8 -*-
"""兼容 shim：分群逻辑回归（lr_by_group / lr_by_qualification / _fit_lr_single）从共享引擎
risk_mining.analysis.engine 再导出。gsfc 链路通过
_load_module('risk_logistic_regression','group_logistic_regression') 取 lr_by_group
（见 tests/test_unit_lr_dedup.py 的 _load_module 模拟回归）。

新代码请直接：
    from risk_mining.analysis.engine import lr_by_group
"""

from risk_mining.analysis.engine import (  # noqa: F401
    lr_by_group,
    lr_by_qualification,
    _fit_lr_single,
)
