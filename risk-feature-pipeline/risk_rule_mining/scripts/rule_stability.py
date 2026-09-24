# -*- coding: utf-8 -*-
"""
规则稳定性评估：在评估集（留出测试集）上 bootstrap 重抽样，度量每条规则坏账率的波动。

口径：
    规则在训练集上挖掘，稳定性只在**未参与挖掘**的测试集上评估（样本外）。
    对测试集做 bootstrap_n 次有放回重抽样，每次记录规则命中样本的坏账率；
    命中坏客户数 ≥ min_bad_in_leaf 的重抽样计为"有效"。
    稳定性等级由 有效占比 与 坏账率变异系数（std/mean）共同判定。

    坏客户不足以留出测试集时，评估集回退为全量（样本内），
    由调用方在「评估口径」列标注，结论偏乐观。
"""
import numpy as np
import pandas as pd

from .config import (
    RULE_MINING_CONFIG,
    STABILITY_CV_STABLE,
    STABILITY_CV_MODERATE,
)
from .rule_extraction import _conditions_to_mask


def _stability_grade(mean: float, std: float, valid_ratio: float) -> str:
    """根据重抽样坏账率均值/标准差/有效占比判定稳定性等级。"""
    if valid_ratio < RULE_MINING_CONFIG['stability_min_valid_ratio'] or np.isnan(mean) or mean == 0:
        return '不稳定'
    cv = std / mean  # 变异系数
    if cv <= STABILITY_CV_STABLE:
        return '稳定'
    if cv <= STABILITY_CV_MODERATE:
        return '较稳定'
    return '不稳定'


def assess_rule_stability(
    df_eval: pd.DataFrame,
    rules_df: pd.DataFrame,
    target: str = 'is_bad',
    n_boot: int = None,
    random_state: int = 42,
    verbose: bool = True,
) -> pd.DataFrame:
    """为规则表追加稳定性列（在 df_eval 上 bootstrap）。

    追加字段：stab_bad_rate_mean, stab_bad_rate_std, stab_valid_n, stab_n, stability
    """
    if rules_df.empty:
        return rules_df
    if n_boot is None:
        n_boot = RULE_MINING_CONFIG['bootstrap_n']

    df_clean = df_eval.dropna(subset=[target]).reset_index(drop=True)
    y = df_clean[target].astype(int).to_numpy()
    n = len(y)
    min_bad = RULE_MINING_CONFIG['min_bad_in_leaf']

    masks = [
        _conditions_to_mask(df_clean, row['conditions'], row.get('fill_values')).to_numpy()
        for _, row in rules_df.iterrows()
    ]

    rng = np.random.default_rng(random_state)
    bad_rates = [[] for _ in masks]
    for _ in range(n_boot if n > 0 else 0):
        idx = rng.integers(0, n, n)
        y_b = y[idx]
        for k, mask in enumerate(masks):
            hit = mask[idx]
            cover = int(hit.sum())
            bad = int(y_b[hit].sum())
            if cover > 0 and bad >= min_bad:
                bad_rates[k].append(bad / cover)

    results = []
    for rates in bad_rates:
        if rates:
            mean_br = float(np.mean(rates))
            std_br = float(np.std(rates, ddof=0))
        else:
            mean_br, std_br = np.nan, np.nan
        valid_ratio = len(rates) / n_boot if n_boot else 0.0
        results.append({
            'stab_bad_rate_mean': mean_br,
            'stab_bad_rate_std': std_br,
            'stab_valid_n': len(rates),
            'stab_n': n_boot,
            'stability': _stability_grade(mean_br, std_br, valid_ratio),
        })

    stab_df = pd.DataFrame(results)
    return pd.concat([rules_df.reset_index(drop=True), stab_df], axis=1)
