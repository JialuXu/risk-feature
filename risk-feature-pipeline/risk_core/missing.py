# -*- coding: utf-8 -*-
"""缺失值统一口径（单一真源）。

按分析类型分口径，各模块不得再自行 fillna(0) / dropna：

  统计检验（相关系数 / 均值差 / T 检验）  → 成对删除：只用「特征与目标都非缺失」的样本
  建模与切分（逻辑回归 / 规则挖掘 / 阈值探索）→ 中位数填补；训练与评估使用同一组填补值
  IV / WOE                               → 缺失单独成箱（见 analysis.iv_core.calc_iv），不走本模块

credit / gsfc 老链路（risk_legacy_chains，含 segment_univariate）按既定决策保持黑盒原口径。
"""
from __future__ import annotations

from typing import Dict, Optional

import pandas as pd

MISSING_POLICY_TEST = '成对删除'
MISSING_POLICY_MODEL = '中位数填补'
# 仅供 credit/gsfc 黑盒老链路保持历史数值（golden test 钉死），新代码不得使用
MISSING_POLICY_LEGACY_ZERO = '填0(老链路)'


def pairwise_valid(df: pd.DataFrame, feature: str, target: str) -> pd.DataFrame:
    """统计检验口径：返回特征与目标均非缺失的两列子表。"""
    return df[[feature, target]].dropna()


def fit_fill_values(X: pd.DataFrame) -> Dict[str, float]:
    """建模口径：在训练数据上拟合每列的填补值（中位数）。全缺失列不产生填补值。"""
    med = X.median(numeric_only=True)
    return {k: float(v) for k, v in med.items() if pd.notna(v)}


def impute_median(
    X: pd.DataFrame, fill_values: Optional[Dict[str, float]] = None,
) -> pd.DataFrame:
    """建模口径：按 fill_values（缺省时就地拟合）做中位数填补。

    评估 / 打分阶段务必传入训练阶段的 fill_values，保证训练与评估口径一致。
    """
    if fill_values is None:
        fill_values = fit_fill_values(X)
    return X.fillna(value=fill_values)


def impute_for_model(X: pd.DataFrame, policy: str = MISSING_POLICY_MODEL) -> pd.DataFrame:
    """建模口径分发：默认中位数填补；老链路显式传 MISSING_POLICY_LEGACY_ZERO 保持填 0。"""
    if policy == MISSING_POLICY_LEGACY_ZERO:
        return X.fillna(0)
    if policy != MISSING_POLICY_MODEL:
        raise ValueError(f'未知缺失值口径：{policy!r}')
    return impute_median(X)
