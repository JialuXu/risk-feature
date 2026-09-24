# -*- coding: utf-8 -*-
"""兼容 shim：IV 计算逻辑已收敛到 risk_mining.analysis.iv_core。

保留本路径仅为兼容既有 `from .iv_analysis import ...`；新代码请直接：
    from risk_mining.analysis.iv_core import calc_iv, run_iv_analysis, ...
"""

# import * 不会带入下划线名，故对内部使用到的下划线符号显式再导出
from risk_mining.analysis.iv_core import *  # noqa: F401,F403
from risk_mining.analysis.iv_core import (  # noqa: F401
    _adaptive_bins,
    _assess_iv_reliability,
    _run_segment_iv,
    calc_iv,
    run_iv_analysis,
)
