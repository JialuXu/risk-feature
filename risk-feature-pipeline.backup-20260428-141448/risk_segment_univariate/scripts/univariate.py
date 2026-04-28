# -*- coding: utf-8 -*-
"""点二列相关与好坏客户 T 检验等底层统计，阈值与 SAMPLE_THRESHOLDS 对齐。"""
import numpy as np
import pandas as pd
from scipy.stats import pointbiserialr, ttest_ind

from .config import SAMPLE_THRESHOLDS, COL_TARGET

_T = SAMPLE_THRESHOLDS


def calc_correlation_pvalue(df, feature, target):
    """
    点二列相关系数及 P 值（连续特征 vs 二分类目标）。

    有效样本数低于 MIN_SAMPLES 或方差退化时返回 nan。
    """
    try:
        df_temp = df[[feature, target]].dropna()
        min_n = _T['MIN_SAMPLES']
        if len(df_temp) < min_n:
            return np.nan, np.nan
        if df_temp[feature].nunique() <= 1 or df_temp[target].nunique() <= 1:
            return np.nan, np.nan

        corr, pvalue = pointbiserialr(df_temp[target], df_temp[feature])
        return corr, pvalue
    except Exception:
        return np.nan, np.nan


def ttest_good_bad(df, feature, target):
    """
    Welch T 检验：好客户(target=0)与坏客户(target=1)在特征上的均值差异。

    各类样本数须同时满足 MIN_GOOD_CORR、MIN_BAD_CORR，否则返回 nan。
    """
    try:
        df_temp = df[[feature, target]].dropna()
        good_vals = df_temp[df_temp[target] == 0][feature]
        bad_vals = df_temp[df_temp[target] == 1][feature]

        min_good = _T['MIN_GOOD_CORR']
        min_bad = _T['MIN_BAD_CORR']
        if len(good_vals) < min_good or len(bad_vals) < min_bad:
            return np.nan, np.nan, np.nan, np.nan

        good_mean = good_vals.mean()
        bad_mean = bad_vals.mean()
        t_stat, p_value = ttest_ind(bad_vals, good_vals, equal_var=False)

        return good_mean, bad_mean, t_stat, p_value
    except Exception:
        return np.nan, np.nan, np.nan, np.nan


def univariate_analysis(df, feature_cols, group_name='全量', target=COL_TARGET):
    """
    单张表内多特征的单变量结果（长表），用于报表或二次汇总。
    """
    results = []

    for feat in feature_cols:
        corr, pvalue = calc_correlation_pvalue(df, feat, target)
        good_mean, bad_mean, t_stat, t_pvalue = ttest_good_bad(df, feat, target)

        results.append({
            '分群': group_name,
            '特征': feat,
            '样本数': df[feat].notna().sum(),
            '相关系数': corr,
            '相关P值': pvalue,
            '好客户均值': good_mean,
            '坏客户均值': bad_mean,
            '均值差异': (
                bad_mean - good_mean
                if pd.notna(bad_mean) and pd.notna(good_mean) else np.nan
            ),
            'T统计量': t_stat,
            'T检验P值': t_pvalue,
        })

    return pd.DataFrame(results)
