# -*- coding: utf-8 -*-
"""
risk_iv_diagnosis 配置

公共配置统一从 risk_core.config 导入，本文件仅保留模块专属配置。
"""

# 导入全部公共配置（DATA_CONFIG, SEGMENT_DIMS, CREDIT_BINS, SAMPLE_THRESHOLDS 等）
from risk_core.config import *  # noqa: F401,F403

# =============================================================================
# 模块专属配置：IV 诊断
# =============================================================================

# IV 可信度分级阈值（IV_CREDIBILITY_*）与「过强」分档起点（IV_PREDICTION_OVERSTRONG_MIN）
# 定义在 risk_core/config/default.yaml 的 iv.* 段，经由上面的 `from risk_core.config import *`
# 引入；本文件无模块专属常量。
