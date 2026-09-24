# -*- coding: utf-8 -*-
"""
工商变更等维度的衍生特征（feature_engineering_gsbb）。

与 SKILL 对齐：仅特征构造；不包含分维度 IV 筛选或跨维度建模（已移除，避免与
risk_iv_diagnosis / risk_segment_univariate 职责重叠）。
"""


from .config import (
    CHANGE_HIGH_RISK_CUMULATIVE_COLS,
    CHANGE_HIGH_RISK_SHORT_WINDOWS,
    CHANGE_RECENT_DAY_WINDOWS,
)
from .io_utils import safe_divide


def feature_engineering_gsbb(df):
    """
    工商变更维度的特征工程

    构造衍生特征：
    - 近期变更占比（30天/90天/180天/365天）
    - 变更类型集中度
    - 高风险变更占比
    - 标记净增减
    """
    print("[INFO] 工商变更特征工程...")

    if '变更总次数' in df.columns and df['变更总次数'].notna().any():
        for period in CHANGE_RECENT_DAY_WINDOWS:
            col_name = f'最近{period}天_变更次数'
            if col_name in df.columns:
                df[f'近{period}天变更占比'] = safe_divide(
                    df[col_name], df['变更总次数']
                )

    if '变更类型数' in df.columns and '变更总次数' in df.columns:
        df['变更类型集中度'] = 1 - safe_divide(
            df['变更类型数'], df['变更总次数']
        )

    available_hr_cols = [
        c for c in CHANGE_HIGH_RISK_CUMULATIVE_COLS if c in df.columns
    ]
    if available_hr_cols and '变更总次数' in df.columns:
        df['高风险变更总数'] = df[available_hr_cols].fillna(0).sum(axis=1)
        df['高风险变更占比'] = safe_divide(
            df['高风险变更总数'], df['变更总次数']
        )

    for period in CHANGE_HIGH_RISK_SHORT_WINDOWS:
        high_risk_cols = [
            f'最近{period}天_法定代表人/负责人变更',
            f'最近{period}天_股东/投资人变更',
            f'最近{period}天_注册资本变更',
        ]
        available_cols = [c for c in high_risk_cols if c in df.columns]
        if available_cols:
            df[f'近{period}天高风险变更数'] = (
                df[available_cols].fillna(0).sum(axis=1)
            )

    if '新增标记总数' in df.columns and '退出标记总数' in df.columns:
        df['标记净增减'] = (
            df['新增标记总数'].fillna(0) - df['退出标记总数'].fillna(0)
        )

    derived_cols = [
        '近30天变更占比', '近90天变更占比', '近180天变更占比', '近365天变更占比',
        '变更类型集中度', '高风险变更总数', '高风险变更占比',
        '近30天高风险变更数', '近90天高风险变更数', '标记净增减',
    ]
    n_derived = sum(1 for c in derived_cols if c in df.columns)
    print(f"[INFO] 工商变更衍生特征数: {n_derived}")

    return df
