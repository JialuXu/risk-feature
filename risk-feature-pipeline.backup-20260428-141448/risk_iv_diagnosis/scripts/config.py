# -*- coding: utf-8 -*-
"""
risk_iv_diagnosis 配置

公共配置统一从 shared.config 导入，本文件仅保留模块专属配置。
"""
import sys
from pathlib import Path

# 将 risk-feature-pipeline/ 加入 sys.path，使 shared 包可被 import
_MY_SKILLS_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _MY_SKILLS_ROOT not in sys.path:
    sys.path.insert(0, _MY_SKILLS_ROOT)

# 导入全部公共配置（DATA_CONFIG, SEGMENT_DIMS, CREDIT_BINS, SAMPLE_THRESHOLDS 等）
from shared.config import *  # noqa: F401,F403

# =============================================================================
# 模块专属配置：IV 诊断
# =============================================================================

# IV 可信度分级（与 _assess_iv_reliability 规则一致）
IV_CREDIBILITY_MIN_BAD_STRICT = 20
IV_CREDIBILITY_UNRELIABLE_IV_IF_LOW_BAD = 0.5
IV_CREDIBILITY_LOW_SAMPLE_N = 200
IV_CREDIBILITY_REFERENCE_IV = 1.0

# 全量 IV「预测能力」分档上界（与 IV_THRESHOLD 弱/中/强对齐，额外定义「过强」起点）
IV_PREDICTION_OVERSTRONG_MIN = 0.5
