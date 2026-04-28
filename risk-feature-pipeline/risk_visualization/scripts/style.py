# -*- coding: utf-8 -*-
"""共享样式常量：调色板、figsize、IV 等级颜色等。

模块加载时自动调用 configure_chinese_font() 一次（幂等）。
"""
from __future__ import annotations

from .font_utils import configure_chinese_font

# 模块加载时自动配置中文字体
configure_chinese_font()


# ===== 通用调色板 =====

POS_COLOR = '#2E86C1'   # 蓝（正向 / 风险方向 = 与坏客户正相关）
NEG_COLOR = '#C0392B'   # 红（负向 / 与坏客户负相关）
NEUTRAL_COLOR = '#7F8C8D'
GRID_COLOR = '#E5E7E9'
ANNO_COLOR = '#34495E'

# IV 预测能力分级颜色
IV_LEVEL_COLORS = {
    '无':       '#BDC3C7',
    '弱':       '#85C1E9',
    '中':       '#5DADE2',
    '强':       '#E74C3C',
    '过拟合嫌疑': '#7B241C',
}

# AUC 类型颜色
AUC_TYPE_COLORS = {
    '交叉验证':       '#27AE60',
    '训练集-样本不足': '#F39C12',
    '训练集-CV失败':   '#C0392B',
}

# 稳定性等级颜色（rule mining）
STABILITY_COLORS = {
    '稳定':   '#27AE60',
    '一般':   '#F39C12',
    '不稳定': '#C0392B',
    '': NEUTRAL_COLOR,
}


# ===== Figure 尺寸（英寸） =====

FIGSIZE_BAR_WIDE = (12, 7)         # 标准条形图（横向）
FIGSIZE_BAR_TALL = (10, 9)         # top-N 多的横向条形图
FIGSIZE_HEATMAP = (14, 8)
FIGSIZE_NETWORK = (11, 10)
FIGSIZE_TREE = (16, 10)
FIGSIZE_SCATTER = (11, 7)


# ===== 标题前缀 =====

TITLE_PREFIX = '风险特征分析'
