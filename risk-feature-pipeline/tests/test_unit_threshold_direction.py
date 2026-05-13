# -*- coding: utf-8 -*-
"""风险方向推断三态单测：lr → corr → bin_jump 优先级与回落。"""
from __future__ import annotations

import numpy as np
import pandas as pd

from risk_threshold_explore.scripts.threshold_explore import _infer_risk_direction


def _make_bin_table(rates):
    """构造形如 optbinning binning_table 的 data_rows（汉化后用中文列名）。"""
    return pd.DataFrame({
        '分箱': [f'bin_{i}' for i in range(len(rates))],
        '坏率': rates,
    })


def test_direction_from_lr_positive():
    lr = pd.DataFrame({
        '分群维度': ['企业规模'], '分群名称': ['小型企业'], '特征': ['feat_1'], '系数': [0.8],
    })
    data_rows = _make_bin_table([0.1, 0.3, 0.5])
    direction, src = _infer_risk_direction(
        '企业规模', '小型企业', 'feat_1', lr, None, data_rows, splits=np.array([0.5, 1.0]),
    )
    assert direction == 'positive'
    assert src == 'lr'


def test_direction_from_lr_negative_wins_over_corr():
    """LR 命中时 corr 不应介入，即使 corr 给出相反方向。"""
    lr = pd.DataFrame({
        '分群维度': ['企业规模'], '分群名称': ['小型企业'], '特征': ['feat_1'], '系数': [-1.2],
    })
    corr = pd.DataFrame({
        '分群维度': ['企业规模'], '分群名称': ['小型企业'], '特征': ['feat_1'], '相关系数': [0.7],
    })
    data_rows = _make_bin_table([0.5, 0.3, 0.1])
    direction, src = _infer_risk_direction(
        '企业规模', '小型企业', 'feat_1', lr, corr, data_rows, splits=np.array([0.5]),
    )
    assert direction == 'negative'
    assert src == 'lr'


def test_direction_falls_back_to_corr():
    """LR 缺这条记录时回落到 corr。"""
    lr = pd.DataFrame(columns=['分群维度', '分群名称', '特征', '系数'])
    corr = pd.DataFrame({
        '分群维度': ['企业规模'], '分群名称': ['小型企业'], '特征': ['feat_1'], '相关系数': [-0.4],
    })
    data_rows = _make_bin_table([0.5, 0.3, 0.1])
    direction, src = _infer_risk_direction(
        '企业规模', '小型企业', 'feat_1', lr, corr, data_rows, splits=np.array([0.5]),
    )
    assert direction == 'negative'
    assert src == 'corr'


def test_direction_falls_back_to_bin_jump():
    """LR/corr 都缺时回落到分箱跳变方向；event rate 升高 → positive。"""
    lr = None
    corr = None
    data_rows = _make_bin_table([0.05, 0.05, 0.40])  # 最大跳变在末段，向上
    direction, src = _infer_risk_direction(
        '企业规模', '小型企业', 'feat_1', lr, corr, data_rows, splits=np.array([0.5, 1.0]),
    )
    assert direction == 'positive'
    assert src == 'bin_jump'


def test_direction_bin_jump_downward():
    """event rate 跳降 → negative。"""
    data_rows = _make_bin_table([0.40, 0.05, 0.05])
    direction, src = _infer_risk_direction(
        '企业规模', '小型企业', 'feat_1', None, None, data_rows, splits=np.array([0.5, 1.0]),
    )
    assert direction == 'negative'
    assert src == 'bin_jump'


def test_direction_unknown_when_single_bin():
    """单 bin 时 bin_jump 也无法判定，返回 (None, None)。"""
    data_rows = _make_bin_table([0.10])
    direction, src = _infer_risk_direction(
        '企业规模', '小型企业', 'feat_1', None, None, data_rows, splits=np.array([]),
    )
    assert direction is None
    assert src is None


def test_zero_coef_does_not_trigger_lr():
    """LR 系数为 0（数值意义上无方向）应跳过 LR，转回落到下一档。"""
    lr = pd.DataFrame({
        '分群维度': ['企业规模'], '分群名称': ['小型企业'], '特征': ['feat_1'], '系数': [0.0],
    })
    corr = pd.DataFrame({
        '分群维度': ['企业规模'], '分群名称': ['小型企业'], '特征': ['feat_1'], '相关系数': [0.6],
    })
    data_rows = _make_bin_table([0.1, 0.4])
    direction, src = _infer_risk_direction(
        '企业规模', '小型企业', 'feat_1', lr, corr, data_rows, splits=np.array([0.5]),
    )
    assert direction == 'positive'
    assert src == 'corr'
