# -*- coding: utf-8 -*-
"""单元测试：prepare_df 特征卫生闸（语义残缺资质哑变量名 + 二值特征完全相同/互补去重）。

事故背景：上游 one-hot 用「取值」拼列名产生 `是_非` 这类语义残缺列，且与正名列
完全互补 → 两列 IV 完全相同、LR 完全共线、方向标注自相矛盾，最终混进触碰提取
的待确认清单。闸的判定只依赖命名约定（config 前缀）与取值关系，不含任何具体
业务列名黑名单（防过拟合）。
"""
from __future__ import annotations

import pandas as pd
import pytest

from risk_data_prep.scripts.feature_sanity import (
    find_degenerate_qual_names,
    find_redundant_binary_features,
)
from risk_data_prep.scripts.prepare_df import prepare_df


def _write_csv(tmp_path, name: str, df: pd.DataFrame) -> str:
    p = tmp_path / name
    df.to_csv(p, index=False, encoding='utf-8-sig')
    return str(p)


# ---------------------------------------------------------------------------
# A. 列名闸 find_degenerate_qual_names（纯函数）
# ---------------------------------------------------------------------------

def test_degenerate_names_caught_and_legit_names_kept():
    """前缀后仅剩纯是/否词（或空/nan）→ 剔；正名资质列与非前缀列不受影响。"""
    cols = ['是_非', '是_否', '是_是', '是_无', '是_', '是_nan',
            '是_科技型企业', '是_高新技术企业', '资产负债率']
    bad = find_degenerate_qual_names(cols, qual_prefix='是_')
    assert set(bad) == {'是_非', '是_否', '是_是', '是_无', '是_', '是_nan'}
    # 每条剔除都带原因（显式记原因规范）
    assert all('语义' in why for why in bad.values())


def test_degenerate_names_follow_custom_prefix():
    """前缀来自配置约定，换行方前缀（如 标签_）自动跟随，不硬编码 是_。"""
    cols = ['标签_非', '标签_高新技术企业', '是_非']
    bad = find_degenerate_qual_names(cols, qual_prefix='标签_')
    assert set(bad) == {'标签_非'}          # 是_非 不匹配该行前缀，不误伤


def test_degenerate_names_default_prefix_from_config():
    """不传前缀时读 column_mapping.yaml 默认值（是_）。"""
    bad = find_degenerate_qual_names(['是_非', '是_科技型企业'])
    assert set(bad) == {'是_非'}


# ---------------------------------------------------------------------------
# B. 取值闸 find_redundant_binary_features（纯函数）
# ---------------------------------------------------------------------------

def test_complementary_binary_pair_deduped_keep_first():
    """完全互补的二值对（含 int/float dtype 混用）只保留列序靠前者。"""
    df = pd.DataFrame({
        '科技型企业_是': [1, 0, 1, 0, 1, 0],
        '科技型企业_否': [0.0, 1.0, 0.0, 1.0, 0.0, 1.0],   # = 1 - 前者，float
    })
    bad = find_redundant_binary_features(df, list(df.columns))
    assert set(bad) == {'科技型企业_否'}
    assert '互补' in bad['科技型企业_否']


def test_identical_binary_deduped():
    """完全相同的二值对只保留一个。"""
    df = pd.DataFrame({'a': [1, 0, 1], 'a_copy': [1, 0, 1]})
    bad = find_redundant_binary_features(df, ['a', 'a_copy'])
    assert set(bad) == {'a_copy'}
    assert '相同' in bad['a_copy']


def test_near_complementary_binary_kept():
    """差一行的二值对不是完全互补 → 两列都保留（阈值不放松）。"""
    df = pd.DataFrame({'a': [1, 0, 1, 0], 'b': [0, 1, 0, 0]})
    assert find_redundant_binary_features(df, ['a', 'b']) == {}


def test_continuous_perfect_corr_deliberately_kept():
    """连续特征即使完全线性相关也不剔（刻意只动二值，避免小样本/换算列误伤）。"""
    df = pd.DataFrame({'x': [1.0, 2.0, 3.0], 'y': [2.0, 4.0, 6.0]})
    assert find_redundant_binary_features(df, ['x', 'y']) == {}


# ---------------------------------------------------------------------------
# C. prepare_df 端到端（事故场景复现：是_非 与 是_科技型企业 互补共存）
# ---------------------------------------------------------------------------

@pytest.fixture()
def incident_paths(tmp_path):
    n = 6
    tech = [1, 0, 1, 0, 1, 0]
    wide = _write_csv(tmp_path, 'wide.csv', pd.DataFrame({
        '客户编号': [f'C{i:03d}' for i in range(n)],
        '是_非': [1 - v for v in tech],       # 语义残缺 + 与正名列完全互补
        '是_科技型企业': tech,
        '资产负债率': [0.3, 0.5, 0.7, 0.4, 0.6, 0.8],
    }))
    bad = _write_csv(tmp_path, 'bad.csv', pd.DataFrame({'客户编号': ['C000', 'C001']}))
    return wide, bad


def test_prepare_df_drops_degenerate_and_keeps_legit(incident_paths, capfd):
    wide, bad = incident_paths
    df, feature_cols = prepare_df(wide_path=wide, bad_customer_path=bad,
                                  id_col='客户编号', target_col='is_bad')
    # 名字闸在前 → 互补对里存活的是正名列，而非按列序碰运气（是_非 列序更靠前）
    assert '是_非' not in feature_cols
    assert '是_科技型企业' in feature_cols
    assert '资产负债率' in feature_cols
    # 只清理入池清单，不动 df
    assert '是_非' in df.columns
    # 剔除显式记原因到 stderr
    err = capfd.readouterr().err
    assert '特征卫生闸' in err and '是_非' in err


def test_prepare_df_dedups_well_named_complement_pair(tmp_path, capfd):
    """两列都是正名（名字闸不触发）时，取值闸兜底去重，保留列序靠前者。"""
    n = 6
    v = [1, 0, 1, 0, 1, 0]
    wide = _write_csv(tmp_path, 'wide.csv', pd.DataFrame({
        '客户编号': [f'C{i:03d}' for i in range(n)],
        '是_科技型企业': v,
        '是_非科技型企业': [1 - x for x in v],   # 正名但完全互补
    }))
    bad = _write_csv(tmp_path, 'bad.csv', pd.DataFrame({'客户编号': ['C000', 'C001']}))
    df, feature_cols = prepare_df(wide_path=wide, bad_customer_path=bad,
                                  id_col='客户编号', target_col='is_bad')
    assert feature_cols == ['是_科技型企业']
    assert '互补' in capfd.readouterr().err
