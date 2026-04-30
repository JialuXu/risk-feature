# -*- coding: utf-8 -*-
"""A3 单测：prepare_df 数值范围过滤（min/max/range/drop_na）。"""
from __future__ import annotations

import pandas as pd
import pytest

from risk_data_prep.scripts.prepare_df import prepare_df


def _write_wide(tmp_path, df: pd.DataFrame) -> str:
    p = tmp_path / 'wide.csv'
    df.to_csv(p, index=False, encoding='utf-8-sig')
    return str(p)


def test_filter_exclude_categorical(tmp_path):
    wide = _write_wide(tmp_path, pd.DataFrame({
        '客户编号': ['A', 'B', 'C'],
        '企业规模': ['大', '0', '小'],
        'is_bad': [0, 1, 0],
        '其它': [1.0, 2.0, 3.0],
    }))
    df, _ = prepare_df(
        wide_path=wide, bad_customer_path=None,
        id_col='客户编号', target_col='is_bad',
        filter={'企业规模': {'exclude': ['0']}},
    )
    assert df['客户编号'].tolist() == ['A', 'C']


def test_filter_range(tmp_path):
    """range 应同时应用 lo + hi。"""
    wide = _write_wide(tmp_path, pd.DataFrame({
        '客户编号': ['A', 'B', 'C', 'D'],
        '占比': [0.1, 0.5, 1.5, -0.2],
        'is_bad': [0, 1, 0, 1],
    }))
    df, _ = prepare_df(
        wide_path=wide, bad_customer_path=None,
        id_col='客户编号', target_col='is_bad',
        filter={'占比': {'range': [0.0, 1.0]}},
    )
    assert df['客户编号'].tolist() == ['A', 'B']


def test_filter_min_only(tmp_path):
    wide = _write_wide(tmp_path, pd.DataFrame({
        '客户编号': ['A', 'B', 'C'],
        '指标': [10, 50, 100],
        'is_bad': [0, 0, 1],
    }))
    df, _ = prepare_df(
        wide_path=wide, bad_customer_path=None,
        id_col='客户编号', target_col='is_bad',
        filter={'指标': {'min': 30}},
    )
    assert df['客户编号'].tolist() == ['B', 'C']


def test_filter_max_only(tmp_path):
    wide = _write_wide(tmp_path, pd.DataFrame({
        '客户编号': ['A', 'B', 'C'],
        '指标': [10, 50, 100],
        'is_bad': [0, 0, 1],
    }))
    df, _ = prepare_df(
        wide_path=wide, bad_customer_path=None,
        id_col='客户编号', target_col='is_bad',
        filter={'指标': {'max': 60}},
    )
    assert df['客户编号'].tolist() == ['A', 'B']


def test_filter_combined_exclude_and_range(tmp_path):
    wide = _write_wide(tmp_path, pd.DataFrame({
        '客户编号': ['A', 'B', 'C', 'D', 'E'],
        '企业规模': ['大', '0', '小', '大', '0'],
        '占比': [0.5, 0.5, 1.5, 0.7, 0.3],
        'is_bad': [0, 1, 0, 1, 0],
    }))
    df, _ = prepare_df(
        wide_path=wide, bad_customer_path=None,
        id_col='客户编号', target_col='is_bad',
        filter={
            '企业规模': {'exclude': ['0']},   # 剔 B / E
            '占比': {'range': [0.0, 1.0]},    # 剔 C
        },
    )
    assert df['客户编号'].tolist() == ['A', 'D']


def test_filter_drop_na(tmp_path):
    wide = _write_wide(tmp_path, pd.DataFrame({
        '客户编号': ['A', 'B', 'C'],
        '指标': [1.0, None, 3.0],
        'is_bad': [0, 1, 0],
    }))
    df, _ = prepare_df(
        wide_path=wide, bad_customer_path=None,
        id_col='客户编号', target_col='is_bad',
        filter={'指标': {'drop_na': True}},
    )
    assert df['客户编号'].tolist() == ['A', 'C']


def test_filter_range_invalid_format_raises(tmp_path):
    wide = _write_wide(tmp_path, pd.DataFrame({
        '客户编号': ['A'],
        '占比': [0.5],
        'is_bad': [0],
    }))
    with pytest.raises(ValueError, match='range'):
        prepare_df(
            wide_path=wide, bad_customer_path=None,
            id_col='客户编号', target_col='is_bad',
            filter={'占比': {'range': [0.0]}},   # 只有一个值，应报错
        )


def test_filter_unknown_col_silently_skipped(tmp_path):
    """filter 列不在宽表中 → 静默跳过，与原行为一致。"""
    wide = _write_wide(tmp_path, pd.DataFrame({
        '客户编号': ['A'],
        'is_bad': [0],
    }))
    df, _ = prepare_df(
        wide_path=wide, bad_customer_path=None,
        id_col='客户编号', target_col='is_bad',
        filter={'不存在的列': {'range': [0, 1]}},
    )
    assert df['客户编号'].tolist() == ['A']
