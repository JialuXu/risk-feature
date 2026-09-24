# -*- coding: utf-8 -*-
"""回归测试：设计检视第二批统计口径（缺失值统一 / 规则留出评估 / 触碰阈值防护）。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


# ===== 缺失值：统计检验成对删除，建模中位数填补 =====

def test_univariate_corr_and_diff_agree_on_direction_with_missing():
    """缺失集中在坏客户时，fillna(0) 会让相关系数与均值差方向相反；成对删除后一致。"""
    from risk_pipeline.analysis.engine import _univariate_single_group

    rng = np.random.default_rng(0)
    n = 1000
    y = (rng.random(n) < 0.2).astype(int)
    x = rng.normal(loc=10 + y * 0.3, scale=1.0)
    # 坏客户里 40% 缺失：旧口径填 0 会把坏客户均值拉到好客户之下，相关系数变负
    x[(y == 1) & (rng.random(n) < 0.4)] = np.nan
    df = pd.DataFrame({'f': x, 'is_bad': y})
    assert df['f'].fillna(0).corr(df['is_bad']) < 0   # 旧口径的错误方向

    corr, diff, _ = _univariate_single_group(df, ['f'], target='is_bad')
    assert np.sign(corr['f']) == np.sign(diff['f']) == 1


def test_impute_for_model_policies():
    from risk_core.missing import (
        MISSING_POLICY_LEGACY_ZERO, fit_fill_values, impute_for_model, impute_median,
    )

    X = pd.DataFrame({'a': [1.0, np.nan, 3.0, 5.0], 'b': [np.nan] * 4})
    med = impute_for_model(X)
    assert med['a'].tolist() == [1.0, 3.0, 3.0, 5.0]
    assert med['b'].isna().all()          # 全缺失列不凭空造值
    assert impute_for_model(X, MISSING_POLICY_LEGACY_ZERO)['a'].tolist() == [1.0, 0.0, 3.0, 5.0]
    # 评估阶段沿用训练填补值
    assert impute_median(pd.DataFrame({'a': [np.nan]}), fit_fill_values(X))['a'].iloc[0] == 3.0
    with pytest.raises(ValueError):
        impute_for_model(X, '未知口径')


def test_woe_table_iv_sums_to_calc_iv():
    from risk_export_report.scripts.report_insights import calc_woe_table
    from risk_pipeline.analysis.iv_core import calc_iv

    rng = np.random.default_rng(3)
    n = 3000
    x = rng.normal(size=n)
    y = (rng.random(n) < 1 / (1 + np.exp(-(x - 2)))).astype(int)
    x[rng.random(n) < 0.2] = np.nan
    df = pd.DataFrame({'f': x, 'is_bad': y})

    table = calc_woe_table(df, 'f', 'is_bad')
    assert table['bin'].iloc[-1] == '缺失'
    assert table['iv'].sum() == pytest.approx(calc_iv(df, 'f', 'is_bad')[0], abs=1e-9)


# ===== 规则：留出评估 + 训练/评估同一填补值 =====

def _rule_df(n, seed=5):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({f'f{i}': rng.normal(size=n) for i in range(6)})
    p = 1 / (1 + np.exp(-(1.2 * df['f0'] - 0.8 * df['f1'] - 2.5)))
    df['is_bad'] = (rng.random(n) < p).astype(int)
    return df


def test_rules_evaluated_out_of_sample_when_enough_bad():
    from risk_rule_mining.scripts.rule_mining_pipeline import mine_rules_full

    rules = mine_rules_full(_rule_df(4000), [f'f{i}' for i in range(6)], verbose=False)
    assert not rules.empty
    assert set(rules['eval_scope']) == {'样本外(留出30%)'}
    assert {'train_lift', 'stab_valid_n', 'stab_n', 'stability'} <= set(rules.columns)
    assert (rules['stab_n'] == 200).all()


def test_rules_fall_back_to_in_sample_when_bad_scarce():
    from risk_rule_mining.scripts.rule_mining_pipeline import _holdout_split

    df = _rule_df(4000)
    small = pd.concat([df[df['is_bad'] == 1].head(25), df[df['is_bad'] == 0].head(500)])
    train, test, scope = _holdout_split(small, 'is_bad')
    assert scope == '样本内(坏客户不足未留出)'
    assert len(train) == len(test) == len(small)


def test_rule_mask_uses_training_fill_values():
    from risk_rule_mining.scripts.rule_extraction import _conditions_to_mask

    df = pd.DataFrame({'x': [np.nan, 1.0, 9.0]})
    conds = [('x', '>', 5.0)]
    assert _conditions_to_mask(df, conds).tolist() == [False, False, True]
    # 训练中位数为 7 → 缺失客户按 7 判定，命中
    assert _conditions_to_mask(df, conds, {'x': 7.0}).tolist() == [True, False, True]


# ===== 触碰阈值：按适用范围计算 + 方向校验 + 缺列跳过 =====

def _feat(name, direction='positive', scope='full'):
    return {'report_name': name, 'source_col': name, 'risk_direction': direction,
            'iv': 0.2, 'category': 'X', 'scope': scope}


def _trigger_df():
    rng = np.random.default_rng(1)
    n = 400
    size = np.where(np.arange(n) < 200, '大', '小')
    y = (rng.random(n) < 0.2).astype(int)
    # 大型企业：坏客户值高；小型企业整体数值更高但与好坏无关
    v = np.where(size == '大', 1 + y * 2 + rng.normal(scale=0.1, size=n), 50 + rng.normal(size=n))
    return pd.DataFrame({'客户编号': [f'C{i}' for i in range(n)], '企业规模': size,
                         'is_bad': y, 'v': v, 'neg': 1 + y * 2 + rng.normal(scale=0.1, size=n)})


def test_threshold_computed_within_scope():
    from risk_trigger_extraction.scripts.trigger_extraction import compute_thresholds

    df = _trigger_df()
    thr = compute_thresholds(df, [_feat('v', scope={'dim': '企业规模', 'value': '大'})])['v']
    in_scope_bad_mean = df.loc[(df['企业规模'] == '大') & (df['is_bad'] == 1), 'v'].mean()
    assert thr['value'] == pytest.approx(in_scope_bad_mean)
    assert '范围=企业规模=大' in thr['source']
    assert thr['direction_check'] == '一致'


def test_threshold_direction_conflict_flagged(capsys, tmp_path):
    from risk_trigger_extraction.scripts.trigger_extraction import extract_triggers

    _, _, table = extract_triggers(
        df=_trigger_df(), features=[_feat('neg', direction='negative')],
        project_name='dir', output_dir=str(tmp_path), verbose=False,
    )
    _, err = capsys.readouterr()
    assert table.loc[0, '方向校验'].startswith('⚠')
    assert 'risk_direction 相反' in err


def test_missing_scope_dim_skips_feature(capsys, tmp_path):
    from risk_trigger_extraction.scripts.trigger_extraction import extract_triggers

    df_wide, _, table = extract_triggers(
        df=_trigger_df(), features=[_feat('v', scope={'dim': '不存在的列', 'value': 'A'})],
        project_name='skip', output_dir=str(tmp_path), verbose=False,
    )
    _, err = capsys.readouterr()
    assert df_wide['v_触碰'].isna().all()
    assert (df_wide['触碰特征总数'] == 0).all()
    assert table.loc[0, '触碰条件'] == '(已跳过)'
    assert '适用范围列不存在' in err
