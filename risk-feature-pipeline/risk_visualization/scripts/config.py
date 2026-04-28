# -*- coding: utf-8 -*-
"""risk_visualization 配置：复用 risk_pipeline 公共配置 + 模块专属图表常量。"""
import sys
from pathlib import Path

_MY_SKILLS_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _MY_SKILLS_ROOT not in sys.path:
    sys.path.insert(0, _MY_SKILLS_ROOT)

from risk_pipeline.config import *  # noqa: F401,F403

# IV 预测能力分级阈值（与 risk_iv_diagnosis 口径一致）
try:
    from risk_pipeline.config import IV_SUSPECT_THRESHOLD as _IV_SUSPECT_THRESHOLD  # type: ignore
except Exception:
    _IV_SUSPECT_THRESHOLD = 2.0

IV_SUSPECT_THRESHOLD = _IV_SUSPECT_THRESHOLD

# IV 预测能力分箱（强 / 中 / 弱 / 无）—— 与 default.yaml prediction_levels 对齐
IV_LEVEL_BINS = [
    ('无', 0.0, 0.02),
    ('弱', 0.02, 0.1),
    ('中', 0.1, 0.3),
    ('强', 0.3, IV_SUSPECT_THRESHOLD),
    ('过拟合嫌疑', IV_SUSPECT_THRESHOLD, float('inf')),
]
