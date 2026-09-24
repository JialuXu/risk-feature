# -*- coding: utf-8 -*-
"""pytest fixtures：合成数据 + 临时项目根。"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# 把 risk-feature-pipeline/ 加入 sys.path（让 `import risk_core` / `risk_mining` / 各子 skill 工作）
_PIPELINE_ROOT = str(Path(__file__).resolve().parent.parent)
if _PIPELINE_ROOT not in sys.path:
    sys.path.insert(0, _PIPELINE_ROOT)


@pytest.fixture(scope='session')
def synthetic_dataframe():
    """200 行 / 10 数值特征 / 2 类别维度 / 2 资质标签 / 10% 坏客户率。"""
    np.random.seed(42)
    n = 200
    df = pd.DataFrame({
        '客户编号': [f'C{i:04d}' for i in range(n)],
        '企业规模': np.random.choice(
            ['小型企业', '中型企业', '大型企业', '微型企业'],
            size=n, p=[0.4, 0.3, 0.1, 0.2],
        ),
        '行业': np.random.choice(['制造业', '批发零售', '建筑业', '服务业'], size=n),
        '是_VIP': np.random.choice([0, 1], size=n, p=[0.8, 0.2]),
        '是_重点客户': np.random.choice([0, 1], size=n, p=[0.7, 0.3]),
    })
    for i in range(1, 9):
        df[f'feat_{i}'] = np.random.normal(loc=10 + i, scale=2, size=n)
    score = (
        0.5 * df['feat_1'] - 0.3 * df['feat_3'] + 0.4 * df['feat_5']
        + np.random.normal(scale=2, size=n)
    )
    threshold = np.percentile(score, 90)
    df['is_bad'] = (score > threshold).astype(int)
    return df


@pytest.fixture
def project_workdir(tmp_path, synthetic_dataframe, monkeypatch):
    """为每个测试创建独立的项目根：data/raw/wide.csv + bad_customers.csv，并 chdir 进去。"""
    raw = tmp_path / 'data' / 'raw'
    raw.mkdir(parents=True)
    wide_path = raw / 'wide.csv'
    bad_path = raw / 'bad_customers.csv'
    synthetic_dataframe.to_csv(wide_path, index=False, encoding='utf-8-sig')
    bad_df = synthetic_dataframe[synthetic_dataframe['is_bad'] == 1][['客户编号']]
    bad_df.to_csv(bad_path, index=False, encoding='utf-8-sig')
    monkeypatch.chdir(tmp_path)
    return {
        'root': tmp_path,
        'wide': str(wide_path.relative_to(tmp_path)),
        'bad': str(bad_path.relative_to(tmp_path)),
    }
