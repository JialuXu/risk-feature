"""筛选规则: 排除过拟合 + 无法计算; 信号分级."""

from __future__ import annotations

from typing import Any

import pandas as pd


def filter_iv(
    iv_df: pd.DataFrame,
    exclude_credibility: list[str] | None = None,
    iv_max: float = 2.0,
    only_segment: str = "全量",
) -> pd.DataFrame:
    """应用排除规则. 不做 IV 下限过滤(IV 不做硬过滤,见方法论 §3)."""
    if iv_df.empty:
        return iv_df
    exclude_credibility = exclude_credibility or ["无法计算", "不可信-过拟合嫌疑"]
    df = iv_df.copy()
    if "分群" in df.columns:
        df = df[df["分群"] == only_segment]
    if "IV可信度" in df.columns:
        df = df[~df["IV可信度"].isin(exclude_credibility)]
    if "IV值" in df.columns:
        df = df[df["IV值"] < iv_max]
    return df.copy()


def signal_strength(
    iv: float,
    credibility: str,
    thresholds: dict[str, float] | None = None,
) -> str:
    """与 工作链路-指标设计方法论.md §3.2 一致."""
    if credibility != "可信":
        return "观察期"
    t = thresholds or {"strong": 0.10, "medium": 0.05, "weak": 0.02}
    if iv >= t["strong"]:
        return "强"
    if iv >= t["medium"]:
        return "中"
    if iv >= t["weak"]:
        return "弱"
    return "观察期"


def risk_direction_from_lr(lr_df: pd.DataFrame) -> dict[str, str]:
    """从 LR 系数表推断每个特征的风险方向.

    输入列: 特征 / 系数 / 分群名称 (跨分群投票).
    返回: {特征名: '正向' | '负向' | '待验证'}
    """
    if lr_df.empty or "特征" not in lr_df.columns or "系数" not in lr_df.columns:
        return {}
    out: dict[str, str] = {}
    for feat, sub in lr_df.groupby("特征"):
        coefs = sub["系数"].dropna()
        if coefs.empty:
            out[feat] = "待验证"
            continue
        pos_ratio = (coefs > 0).mean()
        if pos_ratio >= 0.7:
            out[feat] = "正向"
        elif pos_ratio <= 0.3:
            out[feat] = "负向"
        else:
            out[feat] = "待验证"
    return out


def add_coverage_rate(iv_df: pd.DataFrame) -> pd.DataFrame:
    """补 coverage_rate = 1 - 缺失样本/总样本."""
    if iv_df.empty:
        return iv_df
    df = iv_df.copy()
    if "缺失样本数" in df.columns and "分群总样本数" in df.columns:
        df["coverage_rate"] = (1 - df["缺失样本数"] / df["分群总样本数"]).round(4)
    return df


__all__ = ["filter_iv", "signal_strength", "risk_direction_from_lr", "add_coverage_rate"]
