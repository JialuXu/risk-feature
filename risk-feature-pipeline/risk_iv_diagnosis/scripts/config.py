# -*- coding: utf-8 -*-
"""
risk_iv_diagnosis 配置

公共配置统一从 risk_pipeline.config 导入，本文件仅保留模块专属配置。
"""
import sys
from pathlib import Path

# 将 risk-feature-pipeline/ 加入 sys.path，使 risk_pipeline 包可被 import
_MY_SKILLS_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _MY_SKILLS_ROOT not in sys.path:
    sys.path.insert(0, _MY_SKILLS_ROOT)

# 导入全部公共配置（DATA_CONFIG, SEGMENT_DIMS, CREDIT_BINS, SAMPLE_THRESHOLDS 等）
from risk_pipeline.config import *  # noqa: F401,F403

# =============================================================================
# 模块专属配置：IV 诊断
# =============================================================================

# IV 可信度分级阈值（IV_CREDIBILITY_*）与「过强」分档起点（IV_PREDICTION_OVERSTRONG_MIN）
# 均已收敛到 risk_core/config/default.yaml 的 iv.* 段，经由上面的 `from risk_pipeline.config import *`
# 引入，此处不再重复定义（本文件已无模块专属常量）。
