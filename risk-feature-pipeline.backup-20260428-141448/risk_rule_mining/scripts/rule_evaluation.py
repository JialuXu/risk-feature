# -*- coding: utf-8 -*-
"""
规则评估：单规则统计量计算 + 批量评估 + 业务建议标注

核心函数：
    evaluate_rule(df, conditions, target) -> dict
    evaluate_rules(df, rules_df, target) -> pd.DataFrame  # 原表追加评估列
"""
from typing import List, Dict, Tuple
import numpy as np
import pandas as pd

from .config import (
    RULE_MINING_CONFIG,
    SUGGESTION_LIFT_STRICT,
    SUGGESTION_LIFT_WARN,
)
from .rule_extraction import _conditions_to_mask


def _wilson_ci(p: float, n: int, z: float = 1.96) -> Tuple[float, float]:
    """Wilson 得分区间：小样本下比正态近似更可靠。"""
    if n == 0:
        return (np.nan, np.nan)
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = (z / denom) * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, center - margin), min(1.0, center + margin))


def _suggest_usage(lift: float, stability: str) -> str:
    """根据 Lift 与稳定性给出业务用途建议。"""
    if stability == '不稳定':
        return '参考'
    if lift >= SUGGESTION_LIFT_STRICT:
        return '审批红线'
    if lift >= SUGGESTION_LIFT_WARN:
        return '预警规则'
    return '参考'


def evaluate_rule(
    df: pd.DataFrame,
    conditions: List[Tuple[str, str, float]],
    target: str = 'is_bad',
) -> Dict:
    """评估单条规则在指定数据集上的统计表现。

    返回字段：coverage_n, coverage_pct, bad_n, bad_rate, overall_bad_rate,
             lift, bad_rate_ci_low, bad_rate_ci_high
    """
    df_clean = df.dropna(subset=[target])
    n_total = len(df_clean)
    if n_total == 0:
        return {}

    mask = _conditions_to_mask(df_clean, conditions)
    cover_n = int(mask.sum())
    if cover_n == 0:
        return {
            'coverage_n': 0, 'coverage_pct': 0.0,
            'bad_n': 0, 'bad_rate': np.nan,
            'overall_bad_rate': df_clean[target].mean(),
            'lift': np.nan,
            'bad_rate_ci_low': np.nan, 'bad_rate_ci_high': np.nan,
        }

    bad_n = int(df_clean.loc[mask, target].sum())
    bad_rate = bad_n / cover_n
    overall_bad_rate = df_clean[target].mean()
    lift = bad_rate / overall_bad_rate if overall_bad_rate > 0 else np.nan
    ci_low, ci_high = _wilson_ci(bad_rate, cover_n)

    return {
        'coverage_n': cover_n,
        'coverage_pct': cover_n / n_total,
        'bad_n': bad_n,
        'bad_rate': bad_rate,
        'overall_bad_rate': overall_bad_rate,
        'lift': lift,
        'bad_rate_ci_low': ci_low,
        'bad_rate_ci_high': ci_high,
    }


def evaluate_rules(
    df: pd.DataFrame,
    rules_df: pd.DataFrame,
    target: str = 'is_bad',
) -> pd.DataFrame:
    """批量评估 + 三道闸门过滤 + Lift 排序 + Top-K 截断。"""
    if rules_df.empty:
        return rules_df

    cfg = RULE_MINING_CONFIG
    eval_records = []
    for _, row in rules_df.iterrows():
        stats = evaluate_rule(df, row['conditions'], target=target)
        eval_records.append(stats)

    eval_df = pd.DataFrame(eval_records)
    out = pd.concat([rules_df.reset_index(drop=True), eval_df], axis=1)

    # 三道闸门
    before = len(out)
    out = out[
        (out['coverage_pct'] >= cfg['min_coverage'])
        & (out['lift'] >= cfg['min_lift'])
        & (out['bad_n'] >= cfg['min_bad_in_leaf'])
    ].copy()

    # Lift 降序 → 覆盖率降序
    out = out.sort_values(['lift', 'coverage_pct'], ascending=[False, False])
    out = out.head(cfg['top_k_per_segment']).reset_index(drop=True)
    out['rule_id'] = range(1, len(out) + 1)

    print(f"[规则评估] 挖掘 {before} 条 → 通过闸门 {len(out)} 条 "
          f"(min_coverage={cfg['min_coverage']}, min_lift={cfg['min_lift']})")
    return out


def attach_suggestion(rules_df: pd.DataFrame) -> pd.DataFrame:
    """为规则表追加 `建议用途` 列，需先有 `stability` 列。"""
    if rules_df.empty:
        return rules_df
    stab = rules_df.get('stability', pd.Series(['稳定'] * len(rules_df)))
    rules_df = rules_df.copy()
    rules_df['suggestion'] = [
        _suggest_usage(l, s) for l, s in zip(rules_df['lift'], stab)
    ]
    return rules_df
