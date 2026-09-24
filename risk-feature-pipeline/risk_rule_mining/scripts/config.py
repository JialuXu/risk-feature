# -*- coding: utf-8 -*-
"""
risk_rule_mining 配置

公共配置统一从 risk_core.config 导入，本文件仅保留模块专属配置。
"""
import sys
from pathlib import Path

# 将 risk-feature-pipeline/ 加入 sys.path，使 risk_core / risk_mining 包可被 import
_MY_SKILLS_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _MY_SKILLS_ROOT not in sys.path:
    sys.path.insert(0, _MY_SKILLS_ROOT)

# 导入全部公共配置（含 RULE_MINING_CONFIG, SAMPLE_THRESHOLDS, IV_THRESHOLD 等）
from risk_core.config import *  # noqa: F401,F403

# =============================================================================
# 模块专属配置：规则挖掘
# =============================================================================

# 稳定性等级判定边界（CV 坏账率变异系数 = std/mean）
STABILITY_CV_STABLE = 0.20      # <=0.20 视为"稳定"
STABILITY_CV_MODERATE = 0.40    # <=0.40 视为"较稳定"，以上视为"不稳定"

# 建议用途的 Lift 分档
SUGGESTION_LIFT_STRICT = 3.0    # Lift>=3 建议"审批红线"
SUGGESTION_LIFT_WARN = 2.0      # Lift>=2 建议"预警规则"
# 低于以上两档 → "参考"

# 规则条件文本化：中文运算符映射
OPERATOR_CN = {
    '<=': '小于等于',
    '>': '大于',
    '<': '小于',
    '>=': '大于等于',
    '==': '等于',
}

# 阈值显示精度
THRESHOLD_DECIMALS = 4
