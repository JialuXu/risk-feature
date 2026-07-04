# -*- coding: utf-8 -*-
"""risk-result-query: 读取已导出的风险特征分析结果 + top-N 查询糖。

解耦重构（DECOUPLING-DESIGN §4.2，阶段 1）：核心读逻辑 ``load_results`` + ``Results``
已升入 ``risk_core.results_loader`` 作为三处共享的唯一读取器；本模块从那里再导出，
并保留 ``top_features`` 等查询糖（只依赖 ``Results`` 的属性，不重复读盘逻辑）。

核心 API:
    load_results(project_name, subdir=None) -> Results      # 再导出自 risk_core
    top_features(results, kind, group=None, dim=None, n=15, sign=None) -> DataFrame
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from risk_core.results_loader import (  # noqa: F401  再导出：读逻辑已升 risk_core
    Results,
    load_results,
    _normalize_legacy_cols,
)


def top_features(results: Results,
                 kind: str,
                 group: Optional[str] = None,
                 dim: Optional[str] = None,
                 n: int = 15,
                 sign: Optional[str] = None) -> pd.DataFrame:
    """统一的 top-N 查询。

    Args:
        kind:   'iv' | 'iv_group' | 'corr' | 'lr'
        group:  分群名称（如 '小型企业'），不传则不过滤
        dim:    分群维度（如 '企业规模'），不传则不过滤
        n:      取前多少条
        sign:   仅对 kind='lr' 生效：'positive' / 'negative' / None（按 |系数| 取）

    Returns:
        已按相应指标降序、head(n) 后的 DataFrame。
    """
    if kind == 'iv':
        if dim or group:
            import warnings
            warnings.warn(
                f"kind='iv' 走全量 IV 表，不接受 dim/group 参数（dim={dim!r}, group={group!r} 已被忽略）。"
                f"如需分群 IV top-N，请改用 kind='iv_group'。",
                UserWarning,
                stacklevel=2,
            )
        df = results.iv_full
        if df is None or df.empty:
            return pd.DataFrame()
        return df.sort_values('IV值', ascending=False).head(n)

    if kind == 'iv_group':
        df = results.iv_group_all
        if df is None or df.empty:
            return pd.DataFrame()
        if dim:
            df = df[df['分群维度'] == dim]
        if group:
            df = df[df['分群名称'] == group]
        return df.sort_values('IV值', ascending=False).head(n)

    if kind == 'corr':
        df = results.corr_long
        if df is None or df.empty:
            return pd.DataFrame()
        if dim:
            df = df[df['分群维度'] == dim]
        if group:
            df = df[df['分群名称'] == group]
        return df.sort_values('|相关系数|', ascending=False).head(n)

    if kind == 'lr':
        df = results.lr_coef_long
        if df is None or df.empty:
            return pd.DataFrame()
        if dim:
            df = df[df['分群维度'] == dim]
        if group:
            df = df[df['分群名称'] == group]
        if sign == 'positive':
            return df.sort_values('系数', ascending=False).head(n)
        if sign == 'negative':
            return df.sort_values('系数', ascending=True).head(n)
        return df.sort_values('|系数|', ascending=False).head(n)

    raise ValueError(f"未知 kind: {kind!r}；支持 iv / iv_group / corr / lr")
