# -*- coding: utf-8 -*-
"""适配性回归：引擎/IV 内核不得绑定任何具体数据集的列名。

用一份与征信/工商/测试数据完全不同形态的宽表（英文主键/目标/分群/特征名）驱动
分析内核，断言 IV / 单变量 / LR / 可信度 全部按传入的 target/dim 工作，且不依赖
`客户编号` / `is_bad` / `企业规模` 等任何硬编码字段。这是去重与后续重构的护栏：
确保 skill 的「配置驱动 + 显式列名」适配能力不被破坏。
"""
import numpy as np
import pandas as pd


def _alien_schema_df(n=600, seed=7):
    """构造一份"异星" schema 的宽表：列名、主键、目标、分群全不同于任何现有数据集。"""
    rng = np.random.default_rng(seed)
    region = rng.choice(['ALPHA', 'BETA', 'GAMMA'], size=n, p=[0.5, 0.3, 0.2])
    x = {f'metric_{i}': rng.normal(50 + i * 5, 12, size=n) for i in range(1, 7)}
    df = pd.DataFrame({'ACCOUNT_KEY': np.arange(100000, 100000 + n), **x})
    df['REGION_CODE'] = region
    # 目标与 metric_1、地区相关，制造可分性
    logit = (df['metric_1'] - 50) / 25 + (region == 'GAMMA') * 0.8 - 1.6
    p = 1 / (1 + np.exp(-logit))
    df['DELINQUENT'] = (rng.random(n) < p).astype(int)
    return df


FEATS = [f'metric_{i}' for i in range(1, 7)]
DIM = 'REGION_CODE'
TGT = 'DELINQUENT'


def test_iv_core_fullsample_is_schema_agnostic():
    """iv_core.run_iv_analysis 在异构 schema 下应算出全量 IV（不因缺少征信维度而失败）。"""
    from risk_pipeline.analysis.iv_core import run_iv_analysis
    iv = run_iv_analysis(_alien_schema_df(), FEATS, target=TGT)
    assert iv is not None and not iv.empty
    assert set(iv['特征']).issubset(set(FEATS))
    assert (iv['分群'] == '全量').any()
    # 可信度列已赋值（按样本/坏客户数判定），不是硬编码
    assert iv['IV可信度'].notna().all()


def test_engine_bygroup_is_schema_agnostic():
    """univariate / iv / lr by_group 应完全按传入的 dim/target 工作。"""
    from risk_iv_diagnosis.scripts.iv_group_diagnosis import (
        univariate_by_group, iv_by_group, lr_by_group, reliability_diagnosis,
    )
    df = _alien_schema_df()

    corr_df, diff_df, pval_df, meta_df, sk_u = univariate_by_group(
        df, DIM, FEATS, target=TGT)
    iv_df, sk_iv = iv_by_group(df, DIM, FEATS, target=TGT)
    coef_df, auc_df, sk_lr = lr_by_group(df, DIM, FEATS, target=TGT)

    # IV 分群结果应覆盖到样本充足的地区，且带可信度
    assert iv_df is not None and not iv_df.empty
    assert 'IV可信度' in iv_df.columns
    # LR 应产出系数 + 带类型标注的 AUC
    assert not auc_df.empty
    assert auc_df['AUC类型'].isin(
        ['5折交叉验证', '训练集(样本不足)', '训练集(CV失败)']).all()
    # 可信度诊断在异构 schema 下也能跑（依赖的是结果列而非字段名）
    summary_df, dist_df, warns = reliability_diagnosis(iv_df)
    assert isinstance(summary_df, pd.DataFrame)


def test_engine_does_not_require_default_target_name():
    """显式 target 时，绝不回退到默认 COL_TARGET（is_bad）这种硬编码名。"""
    from risk_iv_diagnosis.scripts.iv_group_diagnosis import iv_by_group
    df = _alien_schema_df()
    assert 'is_bad' not in df.columns and '客户编号' not in df.columns
    iv_df, _ = iv_by_group(df, DIM, FEATS, target=TGT)
    assert iv_df is not None and not iv_df.empty
