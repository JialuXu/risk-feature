# -*- coding: utf-8 -*-
"""A2 / A1 单测：trigger scope 通用化 + 默认特征匹配率守门。"""
from __future__ import annotations

import pandas as pd
import pytest

from risk_trigger_extraction.scripts.trigger_extraction import (
    _resolve_scope_mask,
    _format_scope_label,
    _get_feature_iv,
    _check_feature_match_rate,
    extract_triggers,
)


# ---------- _resolve_scope_mask ----------

def _df():
    return pd.DataFrame({
        '是否腰部企业': [1, 0, 1, 0],
        '企业规模': ['大', '小', '大', '中'],
    })


def test_scope_full():
    mask = _resolve_scope_mask(_df(), 'full')
    assert mask.tolist() == [True, True, True, True]


def test_scope_none_treated_as_full():
    mask = _resolve_scope_mask(_df(), None)
    assert mask.tolist() == [True, True, True, True]


def test_scope_waist_compat():
    mask = _resolve_scope_mask(_df(), 'waist')
    assert mask.tolist() == [True, False, True, False]


def test_scope_dict_value():
    mask = _resolve_scope_mask(_df(), {'dim': '企业规模', 'value': '大'})
    assert mask.tolist() == [True, False, True, False]


def test_scope_dict_values_multi():
    mask = _resolve_scope_mask(_df(), {'dim': '企业规模', 'values': ['大', '中']})
    assert mask.tolist() == [True, False, True, True]


def test_scope_dict_missing_dim_falls_back_to_full():
    """dim 不在宽表列时退化为全量（不阻断），与 waist 旧行为一致。"""
    mask = _resolve_scope_mask(_df(), {'dim': '不存在的列', 'value': 'X'})
    assert mask.tolist() == [True, True, True, True]


# ---------- _format_scope_label ----------

def test_label_full():
    assert _format_scope_label('full') == '全量'
    assert _format_scope_label(None) == '全量'


def test_label_waist():
    assert _format_scope_label('waist') == '腰部企业'


def test_label_dict_value():
    assert _format_scope_label({'dim': '企业规模', 'value': '大型企业'}) == '企业规模=大型企业'


def test_label_dict_values():
    label = _format_scope_label({'dim': '企业规模', 'values': ['大', '中']})
    assert '企业规模' in label and '大' in label and '中' in label


# ---------- _get_feature_iv ----------

def test_iv_waist_uses_iv_waist_field():
    assert _get_feature_iv({'scope': 'waist', 'iv': 0.1, 'iv_waist': 0.5}) == 0.5


def test_iv_waist_falls_back_to_iv():
    assert _get_feature_iv({'scope': 'waist', 'iv': 0.1}) == 0.1


def test_iv_full_uses_iv():
    assert _get_feature_iv({'scope': 'full', 'iv': 0.2}) == 0.2


def test_iv_dict_scope_uses_iv():
    """通用 dict scope 不读 iv_waist，统一用 iv。"""
    feat = {'scope': {'dim': '企业规模', 'value': '大'}, 'iv': 0.3, 'iv_waist': 0.99}
    assert _get_feature_iv(feat) == 0.3


# ---------- _check_feature_match_rate / extract_triggers 默认特征守门 ----------

def test_match_rate_default_low_raises():
    """默认特征 + 匹配率 < 50% → 抛 RuntimeError。"""
    df = pd.DataFrame({'客户编号': ['A', 'B'], 'is_bad': [0, 1], '与默认无关的列': [1, 2]})
    fake_features = [
        {'source_col': '不存在A', 'report_name': 'A', 'risk_direction': 'positive', 'iv': 0.1, 'category': 'X', 'scope': 'full'},
        {'source_col': '不存在B', 'report_name': 'B', 'risk_direction': 'positive', 'iv': 0.2, 'category': 'X', 'scope': 'full'},
    ]
    with pytest.raises(RuntimeError, match='不匹配'):
        _check_feature_match_rate(fake_features, df, is_using_default=True, verbose=False)


def test_match_rate_user_supplied_low_does_not_raise():
    """用户显式传入 features 时，低匹配率不阻断（仅 warn）。"""
    df = pd.DataFrame({'客户编号': ['A'], 'is_bad': [0]})
    fake_features = [
        {'source_col': '不存在A', 'report_name': 'A', 'risk_direction': 'positive', 'iv': 0.1, 'category': 'X', 'scope': 'full'},
    ]
    # is_using_default=False → 不抛
    _check_feature_match_rate(fake_features, df, is_using_default=False, verbose=False)


def test_match_rate_high_passes():
    """匹配率 ≥ 50% → 不抛。"""
    df = pd.DataFrame({'客户编号': ['A'], 'is_bad': [0], '存在A': [1.0]})
    fake_features = [
        {'source_col': '存在A', 'report_name': 'A', 'risk_direction': 'positive', 'iv': 0.1, 'category': 'X', 'scope': 'full'},
    ]
    _check_feature_match_rate(fake_features, df, is_using_default=True, verbose=False)


def test_extract_triggers_default_features_on_unrelated_widetable_raises(tmp_path):
    """端到端：用默认 RISK_FEATURES 跑一份完全不匹配的宽表 → 必抛 RuntimeError。"""
    df = pd.DataFrame({
        '客户编号': ['A', 'B', 'C'],
        'is_bad': [0, 1, 0],
        '完全无关的列1': [1, 2, 3],
        '完全无关的列2': [4, 5, 6],
    })
    with pytest.raises(RuntimeError, match='不匹配'):
        extract_triggers(
            df=df,
            features=None,            # 走默认 RISK_FEATURES_GSFC
            project_name='unit_test_default_mismatch',
            output_dir=str(tmp_path),
            verbose=False,
        )
