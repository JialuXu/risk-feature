# -*- coding: utf-8 -*-
"""单元测试：prepare_df 打标守门（坏客户清单匹配校验 + 宽表自带目标列取值校验）。

覆盖两类静默错误风险：
1. 坏客户清单与宽表主键 0 匹配 → 全体被标好客户，下游空跑但流程全绿；
2. 宽表自带目标列编码非 0/1（如 '是/否'、1/2）→ 语义全错但流程全绿。
"""
from __future__ import annotations

import pandas as pd
import pytest

from risk_data_prep.scripts.prepare_df import prepare_df


def _write_csv(tmp_path, name: str, df: pd.DataFrame) -> str:
    p = tmp_path / name
    df.to_csv(p, index=False, encoding='utf-8-sig')
    return str(p)


def _make_wide(tmp_path, n: int = 6) -> str:
    """n 个客户的最小宽表（不含目标列）。"""
    return _write_csv(tmp_path, 'wide.csv', pd.DataFrame({
        '客户编号': [f'C{i:03d}' for i in range(n)],
        'feat_1': [float(i) for i in range(n)],
        'feat_2': [float(n - i) for i in range(n)],
    }))


# ---------------------------------------------------------------------------
# A. 坏客户清单分支（bad_customer_path 非 None）
# ---------------------------------------------------------------------------

def test_bad_list_zero_match_raises(tmp_path):
    """清单主键与宽表 0 匹配 → 抛 ValueError，且给出两边主键样例。"""
    wide = _make_wide(tmp_path)
    bad = _write_csv(tmp_path, 'bad.csv', pd.DataFrame({
        '客户编号': ['X001', 'X002'],   # 与宽表 C0xx 完全不匹配
    }))
    with pytest.raises(ValueError, match='0 匹配'):
        prepare_df(wide_path=wide, bad_customer_path=bad,
                   id_col='客户编号', target_col='is_bad')


def test_bad_list_zero_match_message_has_samples(tmp_path):
    """0 匹配报错信息应包含两边主键样例值（便于发现格式差异）。"""
    wide = _make_wide(tmp_path)
    bad = _write_csv(tmp_path, 'bad.csv', pd.DataFrame({
        '客户编号': ['X001'],
    }))
    with pytest.raises(ValueError) as exc:
        prepare_df(wide_path=wide, bad_customer_path=bad,
                   id_col='客户编号', target_col='is_bad')
    msg = str(exc.value)
    assert 'C000' in msg          # 宽表主键样例
    assert 'X001' in msg          # 清单主键样例
    assert 'bad-id-col' in msg    # 提示检查 --bad-id-col


def test_bad_list_empty_raises(tmp_path):
    """清单只有表头（去重后 0 条）→ 抛 ValueError 说明清单为空。"""
    wide = _make_wide(tmp_path)
    bad = _write_csv(tmp_path, 'bad.csv', pd.DataFrame({'客户编号': []}))
    with pytest.raises(ValueError, match='清单为空'):
        prepare_df(wide_path=wide, bad_customer_path=bad,
                   id_col='客户编号', target_col='is_bad')


def test_bad_list_all_bad_raises(tmp_path):
    """全部客户都被标为坏客户 → 抛 ValueError 提示清单或主键可能用错。"""
    n = 6
    wide = _make_wide(tmp_path, n=n)
    bad = _write_csv(tmp_path, 'bad.csv', pd.DataFrame({
        '客户编号': [f'C{i:03d}' for i in range(n)],
    }))
    with pytest.raises(ValueError, match='坏客户'):
        prepare_df(wide_path=wide, bad_customer_path=bad,
                   id_col='客户编号', target_col='is_bad')


def test_bad_list_low_match_rate_warns_not_blocks(tmp_path, capsys):
    """清单匹配率 < 50% → 仅 stderr 警告，不阻断，返回结果正常。"""
    wide = _make_wide(tmp_path, n=6)
    # 清单 4 条，只有 1 条能匹配上（25% < 50%）
    bad = _write_csv(tmp_path, 'bad.csv', pd.DataFrame({
        '客户编号': ['C001', 'X001', 'X002', 'X003'],
    }))
    df, feature_cols = prepare_df(wide_path=wide, bad_customer_path=bad,
                                  id_col='客户编号', target_col='is_bad')
    err = capsys.readouterr().err
    assert '[警告]' in err
    assert '匹配率' in err
    assert '1/4' in err
    assert df['is_bad'].sum() == 1
    assert set(feature_cols) == {'feat_1', 'feat_2'}


def test_bad_list_normal_path_no_warning(tmp_path, capsys):
    """正常匹配（≥50%）→ 无警告，打标正确。"""
    wide = _make_wide(tmp_path, n=6)
    bad = _write_csv(tmp_path, 'bad.csv', pd.DataFrame({
        '客户编号': ['C001', 'C003'],
    }))
    df, feature_cols = prepare_df(wide_path=wide, bad_customer_path=bad,
                                  id_col='客户编号', target_col='is_bad')
    err = capsys.readouterr().err
    assert '[警告]' not in err
    assert df['is_bad'].tolist() == [0, 1, 0, 1, 0, 0]
    assert set(feature_cols) == {'feat_1', 'feat_2'}


# ---------------------------------------------------------------------------
# B. 宽表自带目标列分支（bad_customer_path=None）
# ---------------------------------------------------------------------------

def test_target_col_with_nan_raises(tmp_path):
    wide = _write_csv(tmp_path, 'wide.csv', pd.DataFrame({
        '客户编号': ['A', 'B', 'C'],
        'feat_1': [1.0, 2.0, 3.0],
        'is_bad': [0, None, 1],
    }))
    with pytest.raises(ValueError, match='缺失值'):
        prepare_df(wide_path=wide, bad_customer_path=None,
                   id_col='客户编号', target_col='is_bad')


def test_target_col_yes_no_encoding_raises(tmp_path):
    """'是/否' 编码 → 抛 ValueError 并列出实际取值。"""
    wide = _write_csv(tmp_path, 'wide.csv', pd.DataFrame({
        '客户编号': ['A', 'B', 'C'],
        'feat_1': [1.0, 2.0, 3.0],
        'is_bad': ['是', '否', '否'],
    }))
    with pytest.raises(ValueError, match='0/1') as exc:
        prepare_df(wide_path=wide, bad_customer_path=None,
                   id_col='客户编号', target_col='is_bad')
    assert '是' in str(exc.value)   # 报错应列出实际 unique 值


def test_target_col_1_2_encoding_raises(tmp_path):
    """1/2 编码 → 抛 ValueError（数值但不在 {0,1}）。"""
    wide = _write_csv(tmp_path, 'wide.csv', pd.DataFrame({
        '客户编号': ['A', 'B', 'C'],
        'feat_1': [1.0, 2.0, 3.0],
        'is_bad': [1, 2, 1],
    }))
    with pytest.raises(ValueError, match='0/1'):
        prepare_df(wide_path=wide, bad_customer_path=None,
                   id_col='客户编号', target_col='is_bad')


@pytest.mark.parametrize('constant', [0, 1])
def test_target_col_single_value_raises(tmp_path, constant):
    """目标列全 0 或全 1 → 无法做有监督分析，抛 ValueError。"""
    wide = _write_csv(tmp_path, 'wide.csv', pd.DataFrame({
        '客户编号': ['A', 'B', 'C'],
        'feat_1': [1.0, 2.0, 3.0],
        'is_bad': [constant] * 3,
    }))
    with pytest.raises(ValueError, match='单一取值'):
        prepare_df(wide_path=wide, bad_customer_path=None,
                   id_col='客户编号', target_col='is_bad')


def test_target_col_string_01_accepted(tmp_path):
    """'0'/'1' 字符串编码 → 通过校验并统一为 int。"""
    wide = _write_csv(tmp_path, 'wide.csv', pd.DataFrame({
        '客户编号': ['A', 'B', 'C'],
        'feat_1': [1.0, 2.0, 3.0],
        'is_bad': ['0', '1', '0'],
    }))
    df, _ = prepare_df(wide_path=wide, bad_customer_path=None,
                       id_col='客户编号', target_col='is_bad')
    assert df['is_bad'].tolist() == [0, 1, 0]
    assert df['is_bad'].dtype.kind == 'i'


def test_target_col_float_01_accepted(tmp_path):
    """0.0/1.0 浮点编码 → 通过校验并统一为 int。"""
    wide = _write_csv(tmp_path, 'wide.csv', pd.DataFrame({
        '客户编号': ['A', 'B', 'C'],
        'feat_1': [1.0, 2.0, 3.0],
        'is_bad': [0.0, 1.0, 1.0],
    }))
    df, feature_cols = prepare_df(wide_path=wide, bad_customer_path=None,
                                  id_col='客户编号', target_col='is_bad')
    assert df['is_bad'].tolist() == [0, 1, 1]
    assert df['is_bad'].dtype.kind == 'i'
    assert set(feature_cols) == {'feat_1'}
