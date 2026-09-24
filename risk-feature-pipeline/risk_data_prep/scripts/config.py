# -*- coding: utf-8 -*-
"""
risk_data_prep 配置

公共配置统一从 risk_core.config 导入（独立子 skill 只依赖 risk_core），
本文件仅保留模块专属配置。
"""

# 导入全部公共配置（DATA_CONFIG, SEGMENT_DIMS, CREDIT_BINS, SAMPLE_THRESHOLDS 等）
from risk_core.config import *  # noqa: F401,F403
