# -*- coding: utf-8 -*-
"""
risk_segment_univariate 配置

公共配置统一从 risk_core.config 导入，本文件仅保留模块专属配置。
"""
import sys
from pathlib import Path

# 将 risk-feature-pipeline/ 加入 sys.path，使 risk_core / risk_mining 包可被 import
_MY_SKILLS_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _MY_SKILLS_ROOT not in sys.path:
    sys.path.insert(0, _MY_SKILLS_ROOT)

# 导入全部公共配置（DATA_CONFIG, SEGMENT_DIMS, CREDIT_BINS, SAMPLE_THRESHOLDS 等）
from risk_core.config import *  # noqa: F401,F403
