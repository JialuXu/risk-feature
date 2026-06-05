# -*- coding: utf-8 -*-
"""兼容 shim：分析引擎已收敛到 `risk_pipeline.analysis.engine`。

保留本导入路径（`risk_iv_diagnosis.scripts.iv_group_diagnosis`）以兼容 pipeline.py
的 _load_module 取法、本包 __init__ 的再导出以及既有外部引用；实际实现见 engine。

新代码请直接：
    from risk_pipeline.analysis.engine import univariate_by_group, iv_by_group, lr_by_group, ...
"""
from risk_pipeline.analysis.engine import *  # noqa: F401,F403

# 显式带上 `import *` 不会引入的下划线辅助/被外部引用的名字
from risk_pipeline.analysis.engine import (  # noqa: F401
    _fit_lr_single,
    _print_sample_summary,
    _print_group_table,
    _univariate_single_group,
    _calc_iv_base,
    _assess_iv_reliability,
    _mapper,
    _T,
)
