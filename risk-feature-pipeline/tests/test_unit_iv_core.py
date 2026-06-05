# -*- coding: utf-8 -*-
"""IV 内核数值单测：钉死 calc_iv / 自适应分箱 / 可信度分级 / WOE 截断。

这些是去重重构（三份 iv_analysis.py → risk_pipeline.analysis.iv_core）的回归网：
任何改动若改变了 IV 计算或可信度判定，这里会立刻红。
"""
import math

import numpy as np
import pandas as pd
import pytest

from risk_pipeline.analysis.iv_core import (
    calc_iv,
    _assess_iv_reliability,
    _adaptive_bins,
)


def _det_table():
    """完全确定性小表（无 RNG）。"""
    n = 300
    feat = [float(i % 10) for i in range(n)]
    y = [1 if (feat[i] >= 6 and (i % 3 == 0)) else 0 for i in range(n)]
    return pd.DataFrame({'feat': feat, 'is_bad': y})


def test_calc_iv_deterministic_value():
    """确定性表的 IV 钉死值（重构前后必须一致）。"""
    df = _det_table()
    iv, meta = calc_iv(df, 'feat', 'is_bad', bins=10)
    assert iv == pytest.approx(2.187984431482454, abs=1e-9)
    assert meta['n_samples'] == 300
    assert meta['n_bad'] == 40
    assert meta['iv_missing'] == 0.0


def test_calc_iv_below_min_samples_returns_nan():
    """有效样本 < MIN_SAMPLES(50) 时返回 NaN。"""
    df = _det_table().head(40)
    iv, meta = calc_iv(df, 'feat', 'is_bad')
    assert math.isnan(iv)


def test_calc_iv_missing_contributes():
    """缺失值单独成箱并贡献 IV（缺失分离逻辑）。"""
    df = _det_table()
    df.loc[df.index[:60], 'feat'] = np.nan
    iv, meta = calc_iv(df, 'feat', 'is_bad', bins=10)
    assert meta['n_missing'] == 60
    assert not math.isnan(iv)


def test_calc_iv_finite_under_extreme_separation():
    """完全可分时 WOE 被截断到 [-5,5]，IV 仍有限（不爆 inf）。"""
    n = 200
    feat = [0.0] * 100 + [1.0] * 100
    y = [0] * 100 + [1] * 100  # 完美分离
    df = pd.DataFrame({'feat': feat, 'is_bad': y})
    iv, _ = calc_iv(df, 'feat', 'is_bad')
    assert np.isfinite(iv)


@pytest.mark.parametrize('n_samples,n_bad,expected', [
    (400, 80, 10),   # 充足 → 默认 10 箱
    (100, 9, 3),     # 坏客户极少 → 降到下限 3
    (250, 25, 8),    # 中间档：min(25//3=8, 250//20=12, 10)=8
])
def test_adaptive_bins(n_samples, n_bad, expected):
    assert _adaptive_bins(n_samples, n_bad, default_bins=10) == expected


@pytest.mark.parametrize('iv,n,bad,expected', [
    (float('nan'), 500, 50, '无法计算'),
    (2.5, 500, 50, '不可信-过拟合嫌疑'),   # > suspect(2.0)
    (0.6, 500, 10, '不可信-样本不足'),     # bad<20 且 iv>0.5
    (0.3, 500, 10, '参考'),                # bad<20 但 iv<=0.5
    (0.3, 150, 50, '参考'),                # n<200
    (1.5, 500, 50, '参考'),                # iv>1.0（但 <=2.0）
    (0.3, 500, 50, '可信'),                # 充足且 iv 适中
])
def test_assess_iv_reliability_boundaries(iv, n, bad, expected):
    assert _assess_iv_reliability(iv, n, bad, n_bins_actual=5) == expected


def test_shim_paths_equal_canonical():
    """三个 Skill 的 iv_analysis shim 必须与 canonical 输出完全一致。"""
    from risk_iv_diagnosis.scripts.iv_analysis import calc_iv as a
    from risk_export_report.scripts.iv_analysis import calc_iv as b
    from risk_logistic_regression.scripts.iv_analysis import calc_iv as c
    df = _det_table()
    base, _ = calc_iv(df, 'feat', 'is_bad', bins=10)
    for fn in (a, b, c):
        iv, _ = fn(df, 'feat', 'is_bad', bins=10)
        assert iv == base


def test_shim_reexports_underscore_symbols():
    """shim 必须显式再导出下划线符号（import * 不会带入）。"""
    import risk_export_report.scripts.iv_analysis as m
    for name in ('_adaptive_bins', '_assess_iv_reliability', '_run_segment_iv',
                 'calc_iv', 'run_iv_analysis'):
        assert hasattr(m, name), f'shim 缺少再导出: {name}'
