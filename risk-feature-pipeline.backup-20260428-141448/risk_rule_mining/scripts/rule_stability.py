# -*- coding: utf-8 -*-
"""
规则稳定性评估：K-fold 交叉验证每条规则在 holdout 上的坏账率 mean/std

策略（而非"规则跨折匹配"）：
    给定从全样本挖掘出的规则集，在 K 折 holdout 上分别评估每条规则，
    记录坏账率的 mean/std 与"有效折数"（命中≥min_bad_in_leaf 的折数），
    据此判定稳定性等级。

该做法比"每折重新挖树再匹配规则"更可靠：
    - 阈值浮动下规则匹配极难对齐；
    - CV 目的是度量规则的泛化表现，而非重复发现。
"""
from typing import List
import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold

from .config import (
    RULE_MINING_CONFIG,
    STABILITY_CV_STABLE,
    STABILITY_CV_MODERATE,
)
from .rule_evaluation import evaluate_rule


def _stability_grade(mean: float, std: float, valid_folds: int) -> str:
    """根据 CV 均值/标准差/有效折数判定稳定性等级。"""
    min_folds = RULE_MINING_CONFIG['stability_min_folds']
    if valid_folds < min_folds or np.isnan(mean) or mean == 0:
        return '不稳定'
    cv = std / mean  # 变异系数
    if cv <= STABILITY_CV_STABLE:
        return '稳定'
    if cv <= STABILITY_CV_MODERATE:
        return '较稳定'
    return '不稳定'


def assess_rule_stability(
    df: pd.DataFrame,
    rules_df: pd.DataFrame,
    target: str = 'is_bad',
    n_splits: int = None,
    random_state: int = 42,
    verbose: bool = True,
) -> pd.DataFrame:
    """为规则表追加 CV 稳定性列。

    追加字段：cv_bad_rate_mean, cv_bad_rate_std, cv_valid_folds, stability
    """
    if rules_df.empty:
        return rules_df
    if n_splits is None:
        n_splits = RULE_MINING_CONFIG['cv_splits']

    df_clean = df.dropna(subset=[target]).reset_index(drop=True)
    y = df_clean[target].astype(int)

    # 分层 K 折（保证每折坏客户比例一致）
    if y.sum() < n_splits:
        if verbose:
            print(f"[稳定性] 坏客户数 {y.sum()} < n_splits={n_splits}，跳过 CV")
        rules_df = rules_df.copy()
        rules_df['cv_bad_rate_mean'] = np.nan
        rules_df['cv_bad_rate_std'] = np.nan
        rules_df['cv_valid_folds'] = 0
        rules_df['stability'] = '不稳定'
        return rules_df

    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=random_state)
    min_bad = RULE_MINING_CONFIG['min_bad_in_leaf']

    results = []
    for _, row in rules_df.iterrows():
        fold_bad_rates: List[float] = []
        valid_folds = 0
        for _, test_idx in skf.split(df_clean, y):
            holdout = df_clean.iloc[test_idx]
            stats = evaluate_rule(holdout, row['conditions'], target=target)
            if stats and stats.get('bad_n', 0) >= min_bad:
                fold_bad_rates.append(stats['bad_rate'])
                valid_folds += 1

        if fold_bad_rates:
            mean_br = float(np.mean(fold_bad_rates))
            std_br = float(np.std(fold_bad_rates, ddof=0))
        else:
            mean_br, std_br = np.nan, np.nan

        grade = _stability_grade(mean_br, std_br, valid_folds)
        results.append({
            'cv_bad_rate_mean': mean_br,
            'cv_bad_rate_std': std_br,
            'cv_valid_folds': valid_folds,
            'stability': grade,
        })

    stab_df = pd.DataFrame(results)
    return pd.concat([rules_df.reset_index(drop=True), stab_df], axis=1)
