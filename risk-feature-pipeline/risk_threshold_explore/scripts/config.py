# -*- coding: utf-8 -*-
"""risk_threshold_explore 专用配置。继承公共 SAMPLE_THRESHOLDS / IV_THRESHOLD。"""
from __future__ import annotations

from risk_core.config import (  # noqa: F401  重新导出供脚本使用
    IV_THRESHOLD,
    MIN_SAMPLES,
    MIN_BAD_SAMPLES,
)


# ---- 规则有效性门槛（中等严格；CLI 可逐项覆盖） ----
THRESHOLD_EXPLORE_CFG = {
    # 风险倍数 = 高风险侧坏率 / 低风险侧坏率，≥ 2.0 才入选
    'MIN_RISK_RATIO': 2.0,
    # 卡方 p 值，≤ 0.05 才入选
    'MAX_P_VALUE': 0.05,
    # 高风险侧坏客户数下限，避免长尾偶发触发
    'MIN_BAD_HIGH_SIDE': 10,
    # 触警率（高风险侧占段总样本数）取值区间
    'ALERT_RATE_MIN': 0.01,
    'ALERT_RATE_MAX': 0.30,
    # 参考 IV 下限。语义：优先分群 IV，缺失回落到全样本 IV（详见 threshold_explore._lookup_iv）。
    # 默认取「弱预测」线
    'MIN_IV': IV_THRESHOLD.get('weak', 0.02),
    # segment 准入（与 SAMPLE_THRESHOLDS 对齐）
    'MIN_SEGMENT_SAMPLES': MIN_SAMPLES,
    'MIN_SEGMENT_BADS': MIN_BAD_SAMPLES,
    # 低风险侧坏率为 0 时风险倍数会爆 inf；统一截断到此上限
    'RISK_RATIO_CAP': 999.0,
    # zero-inflated 兜底：某常值（通常为 0）占比 ≥ 此阈值时启用 "> 常值" 切点
    'ZERO_INFLATE_RATIO_THRESHOLD': 0.80,
    # optbinning min_bin_size；CLI 可通过 --min-bin-size 覆盖
    'OPTBIN_MIN_BIN_SIZE': 0.05,
}
# 兼容旧 key（下版本移除）：MIN_IV_FULL ≡ MIN_IV
THRESHOLD_EXPLORE_CFG['MIN_IV_FULL'] = THRESHOLD_EXPLORE_CFG['MIN_IV']


# ---- optbinning 参数 ----
OPTBIN_PARAMS = {
    'dtype': 'numerical',
    'solver': 'cp',
    'monotonic_trend': 'auto',
    'min_bin_size': 0.05,
    'max_n_bins': 8,
}


# ---- 显著性等级（按 p 值从小到大；首个匹配的标签即为结果） ----
SIGNIFICANCE_LABELS = [
    (0.001, '***'),
    (0.01, '**'),
    (0.05, '*'),
    (1.01, 'ns'),
]


def merge_cfg(overrides: dict | None) -> dict:
    """把 CLI 覆盖项合并到默认配置上（仅覆盖给定 key，缺失键保留默认）。

    同时做兼容迁移：若调用方仍传 MIN_IV_FULL（已废弃），自动映射到 MIN_IV。
    """
    cfg = dict(THRESHOLD_EXPLORE_CFG)
    if overrides:
        for k, v in overrides.items():
            if v is None:
                continue
            if k == 'MIN_IV_FULL':
                cfg['MIN_IV'] = v
                cfg['MIN_IV_FULL'] = v  # 双写保持别名一致
            else:
                cfg[k] = v
    # 同步 MIN_IV_FULL 别名（无论是否被覆盖过，始终 = MIN_IV）
    cfg['MIN_IV_FULL'] = cfg['MIN_IV']
    return cfg
