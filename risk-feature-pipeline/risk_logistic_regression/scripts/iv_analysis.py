# -*- coding: utf-8 -*-
"""兼容 shim：IV 计算逻辑已收敛到 risk_mining.analysis.iv_core。

保留本路径仅为兼容既有 `from .iv_analysis import ...`；新代码请直接：
    from risk_mining.analysis.iv_core import calc_iv, run_iv_analysis, ...
"""
import sys
from pathlib import Path

# 确保 risk-feature-pipeline/ 在 sys.path，使 risk_core / risk_mining 包可被 import
_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# import * 不会带入下划线名，故对内部使用到的下划线符号显式再导出
from risk_mining.analysis.iv_core import *  # noqa: F401,F403
from risk_mining.analysis.iv_core import (  # noqa: F401
    _adaptive_bins,
    _assess_iv_reliability,
    _run_segment_iv,
    calc_iv,
    run_iv_analysis,
)
