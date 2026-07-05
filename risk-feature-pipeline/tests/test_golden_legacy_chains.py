# -*- coding: utf-8 -*-
"""数值 golden 基线：credit + gsfc 黑盒链路下游数值输出锁。

背景：credit/gsfc 两条链路此前**无任何测试钉住其下游数值**（IV/LR/单变量）——
现有 smoke 只断文件存在与列 schema。要把「行为保持」从假设变成可验证事实，
尤其是在把 run_credit_pipeline / run_gsfc_pipeline 从 risk_pipeline/pipeline.py
逐字抽取到独立 skill（risk_legacy_chains）之前，本文件用**固定种子合成数据**
真跑两条链路，钉死若干稳定数值单元格：

  - 全量 IV 值（纯 pandas/numpy 算术，确定性最强）；
  - 交叉验证 AUC（StratifiedKFold 无 shuffle，确定性）；
  - credit LR 系数；
  - gsfc univariate_long 相关系数/P值（gsfc 唯一走 risk_segment_univariate 的一步，
    也是「segment vs engine」发散点——本锁保证抽取不动它）。

抽取是**逐字搬迁**，数值应逐位不变；任何漂移都会让本测试变红。
数据合成与 test_smoke_run_credit / test_smoke_run_gsfc 逐字一致，故 fixture 隔离约定相同：
只设 RISK_PROJECT_ROOT（RISK_OUTPUT_ROOT 在 import 期冻结、运行中改无效）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from risk_pipeline.config import COL_CUSTOMER_ID, COL_REPORT_DATE
from risk_pipeline.pipeline import run_credit_pipeline, run_gsfc_pipeline
from risk_data_prep.scripts.config import CREDIT_CONFIG

# IV 是纯算术、逐位可复现；LR 经 sklearn（lbfgs/BLAS）留一点浮点余量。
_IV_TOL = 1e-5
_LR_TOL = 1e-4

_RAW_FEATURES = CREDIT_CONFIG['raw_features']


# ---------------------------------------------------------------------------
# 合成数据（与 test_smoke_run_credit / test_smoke_run_gsfc 逐字一致，固定种子）
# ---------------------------------------------------------------------------
def _build_credit_dataset(root):
    raw = root / 'data' / 'raw'
    raw.mkdir(parents=True)
    rng = np.random.RandomState(20240701)
    n = 600
    ids = [f'K{i:05d}' for i in range(n)]
    pd.DataFrame({
        COL_CUSTOMER_ID: ids,
        '企业规模': ['小型企业' if i % 2 == 0 else '中型企业' for i in range(n)],
    }).to_csv(raw / '客户信息.csv', index=False, encoding='utf-8-sig')
    credit = pd.DataFrame({COL_CUSTOMER_ID: ids})
    credit[COL_REPORT_DATE] = '2024-01-15'
    latent = rng.normal(size=n)
    for j, feat in enumerate(_RAW_FEATURES):
        credit[feat] = (rng.poisson(lam=3 + j, size=n)
                        + (latent * (1 if j % 2 == 0 else 0)).round().astype(int).clip(min=0))
    credit.to_csv(raw / '征信数据.csv', index=False, encoding='utf-8-sig')
    bad_score = latent + rng.normal(scale=0.5, size=n)
    bad_mask = bad_score > np.percentile(bad_score, 80)
    pd.DataFrame({COL_CUSTOMER_ID: [ids[i] for i in range(n) if bad_mask[i]]}).to_csv(
        raw / '坏客户标记.csv', index=False, encoding='utf-8-sig',
    )


def _build_gsfc_dataset(root):
    raw = root / 'data' / 'raw'
    raw.mkdir(parents=True)
    rng = np.random.RandomState(20240601)
    n = 400
    ids = [f'G{i:05d}' for i in range(n)]

    def _money(values):
        return ['-' if i % 29 == 0 else f'{int(v):,}' for i, v in enumerate(values)]

    pd.DataFrame({
        '客户编号': ids,
        '所属行业': ['制造业', '批发零售', '建筑业', '服务业'] * (n // 4),
        '客户性质': ['民营' if i % 2 == 0 else '国有' for i in range(n)],
        '内部评级': rng.choice(['A', 'BBB', 'BB', 'A+'], size=n),
        '授信总金额': _money(rng.randint(5, 500, n) * 100000),
        '表内授信余额': _money(rng.randint(1, 300, n) * 100000),
    }).to_csv(raw / '客户信息.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame({
        '客户编号': ids,
        '变更总次数': rng.randint(0, 20, n),
        '变更类型数': rng.randint(0, 6, n),
        '最近30天_变更次数': rng.randint(0, 4, n),
        '最近90天_变更次数': rng.randint(0, 6, n),
        '新增标记总数': rng.randint(0, 5, n),
        '退出标记总数': rng.randint(0, 5, n),
    }).to_csv(raw / '工商变更_特征.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame({'客户编号': [ids[i] for i in range(n) if rng.rand() < 0.16]}).to_csv(
        raw / '坏客户标记.csv', index=False, encoding='utf-8-sig',
    )


def _iv_full_cell(iv_full, feature):
    row = iv_full[(iv_full['分群'] == '全量') & (iv_full['特征'] == feature)]
    assert len(row) == 1, f'全量 IV 未唯一命中 {feature}：{len(row)} 行'
    return float(row['IV值'].iloc[0])


@pytest.fixture
def credit_workdir(tmp_path, monkeypatch):
    _build_credit_dataset(tmp_path)
    monkeypatch.setenv('RISK_PROJECT_ROOT', str(tmp_path))
    monkeypatch.delenv('RISK_OUTPUT_ROOT', raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def gsfc_workdir(tmp_path, monkeypatch):
    _build_gsfc_dataset(tmp_path)
    monkeypatch.setenv('RISK_PROJECT_ROOT', str(tmp_path))
    monkeypatch.delenv('RISK_OUTPUT_ROOT', raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_credit_numeric_golden(credit_workdir):
    """credit 链路下游 IV / AUC / LR 系数逐位钉死（抽取前后必须不变）。"""
    r = run_credit_pipeline(steps=['data_prep', 'univariate', 'iv', 'lr', 'export'], verbose=False)

    iv = r['iv_full']
    assert _iv_full_cell(iv, '担保人征信查询次数') == pytest.approx(0.296793, abs=_IV_TOL)
    assert _iv_full_cell(iv, '消费金融公司数') == pytest.approx(0.370911, abs=_IV_TOL)
    assert _iv_full_cell(iv, '当前逾期余额') == pytest.approx(0.339124, abs=_IV_TOL)
    assert _iv_full_cell(iv, '银行授信机构数') == pytest.approx(0.275198, abs=_IV_TOL)

    auc = r['lr_auc_results']['企业规模']
    assert float(auc.loc['中型企业', 'AUC']) == pytest.approx(0.706800, abs=_LR_TOL)
    assert float(auc.loc['小型企业', 'AUC']) == pytest.approx(0.687267, abs=_LR_TOL)

    coef = r['lr_coef_results']['企业规模']
    assert float(coef.loc['中型企业', '担保人征信查询次数']) == pytest.approx(0.570470, abs=_LR_TOL)


def test_gsfc_numeric_golden(gsfc_workdir):
    """gsfc 链路下游 IV / AUC / 单变量（segment 路径）逐位钉死。"""
    r = run_gsfc_pipeline(verbose=False)

    iv = r['iv_full']
    assert _iv_full_cell(iv, '变更总次数') == pytest.approx(0.139389, abs=_IV_TOL)
    assert _iv_full_cell(iv, '本行授信使用率') == pytest.approx(0.221354, abs=_IV_TOL)
    assert _iv_full_cell(iv, '标记净增减') == pytest.approx(0.209928, abs=_IV_TOL)

    auc = r['lr_auc_results']['客户性质']
    assert float(auc.loc['国有', 'AUC']) == pytest.approx(0.561765, abs=_LR_TOL)
    assert float(auc.loc['民营', 'AUC']) == pytest.approx(0.435937, abs=_LR_TOL)

    # gsfc 单变量走 risk_segment_univariate（唯一非 engine 提供方）——钉死其相关系数/P值
    ul = r['univariate_long']
    row = ul[(ul['维度'] == '客户性质') & (ul['分群'] == '国有') & (ul['特征'] == '变更总次数')]
    assert len(row) == 1, 'univariate_long 未唯一命中 客户性质/国有/变更总次数'
    assert float(row['相关系数'].iloc[0]) == pytest.approx(0.008284, abs=_LR_TOL)
    assert float(row['P值'].iloc[0]) == pytest.approx(0.899776, abs=_LR_TOL)
