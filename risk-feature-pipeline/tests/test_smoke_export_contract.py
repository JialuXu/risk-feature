# -*- coding: utf-8 -*-
"""导出契约 smoke：risk_export_report 是 Level 1 唯一出口，下游
query/visualize/trigger/report 全部依赖它落盘的文件名与列名契约。

本测试护住契约本身（AGENTS.md 第二节 Level 1 清单），与既有测试的分工：
- test_smoke_run_generic.py 已断言 _IV分析结果.csv / _综合特征分析结果.csv /
  _LLM报告数据.json 存在 + state 推进 → 此处不重复"存在性单点"断言，
  但 Level 1 清单要求"全部落盘且非空"，故此处按清单整体兜底（存在 + 非空）。
- test_unit_csv_schema.py 已断言 IV 全量/分群表的 `特征`/`分群名称` 新列名
  与旧名兼容副本 → 此处跳过 IV 列名断言，只补 corr / LR 的列名契约。
- test_unit_phase_c.py 已断言 audit.json 完整结构 → 此处仅留契约最小断言
  （json 可解析 + iv_overfit_features 键），保证契约测试自包含。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from risk_pipeline import cli


PROJECT = 'export_contract'

# AGENTS.md 第二节 Level 1 清单：data/results/<project>/ 下的产物
RESULTS_FILES = [
    f'{PROJECT}_IV分析结果_全量.csv',      # ⭐ A5 新名
    f'{PROJECT}_IV分析结果_分群.csv',      # ⭐ A5 新名
    f'{PROJECT}_特征风险相关性.csv',
    f'{PROJECT}_逻辑回归系数.csv',
    f'{PROJECT}_IV可信度透视表.csv',
    f'{PROJECT}_IV可信度诊断.csv',
    f'{PROJECT}_IV值透视表.csv',
    f'{PROJECT}_综合特征分析结果.csv',
    f'{PROJECT}_audit.json',               # ⭐ C12 机器可读自检
    # 旧名兼容副本（下版本移除；移除时同步删掉这两行）
    f'{PROJECT}_IV分析结果.csv',
    f'{PROJECT}_IV值分析.csv',
]

# AGENTS.md 第二节 Level 1 清单：output/<project>/ 下的产物
OUTPUT_FILES = [
    f'{PROJECT}_LLM报告数据.json',
    f'{PROJECT}_LLM_分群画像.csv',
]


def _build_contract_dataframe():
    """构造比 conftest.synthetic_dataframe 更大的合成数据（1500 行 / 20% 坏客户率）。

    契约测试要求 Level 1 全清单落盘，其中 _特征风险相关性.csv / _逻辑回归系数.csv
    要求每个分群坏客户数 ≥ MIN_BAD_CORR(15) / MIN_BAD_LR(20)、好客户数 ≥ MIN_GOOD_LR(50)。
    conftest 的 200 行 / 10% 坏客户率会让所有分群被合法跳过 → corr/LR 文件不落盘，
    无法断言完整清单，故此处单独构造（生成逻辑与 conftest 同构，仅放大规模）。
    """
    np.random.seed(42)
    n = 1500
    df = pd.DataFrame({
        '客户编号': [f'C{i:05d}' for i in range(n)],
        '企业规模': np.random.choice(
            ['小型企业', '中型企业', '大型企业', '微型企业'],
            size=n, p=[0.4, 0.3, 0.1, 0.2],
        ),
    })
    for i in range(1, 9):
        df[f'feat_{i}'] = np.random.normal(loc=10 + i, scale=2, size=n)
    score = (
        0.5 * df['feat_1'] - 0.3 * df['feat_3'] + 0.4 * df['feat_5']
        + np.random.normal(scale=2, size=n)
    )
    threshold = np.percentile(score, 80)
    df['is_bad'] = (score > threshold).astype(int)
    return df


@pytest.fixture(scope='module')
def exported_dirs(tmp_path_factory):
    """跑一遍 generic 全流程（prepare→analyze→export），返回结果/输出目录。

    module 级：四个契约断言共享同一次落盘（契约对象是同一批文件，无需重跑）。
    """
    tmp_path = tmp_path_factory.mktemp('export_contract')
    raw = tmp_path / 'data' / 'raw'
    raw.mkdir(parents=True)
    df = _build_contract_dataframe()
    df.to_csv(raw / 'wide.csv', index=False, encoding='utf-8-sig')
    df[df['is_bad'] == 1][['客户编号']].to_csv(
        raw / 'bad_customers.csv', index=False, encoding='utf-8-sig')

    # CLI 自 CWD 向上找含 data/ 的目录定位项目根，故 run 期间 chdir 进临时根
    with pytest.MonkeyPatch.context() as mp:
        mp.chdir(tmp_path)
        rc = cli.main([
            'run', '--pipeline', 'generic',
            '--wide', 'data/raw/wide.csv',
            '--bad-customer', 'data/raw/bad_customers.csv',
            '--id-col', '客户编号',
            '--target-col', 'is_bad',
            '--project', PROJECT,
            '--confirmed-new-dataset',
        ])
    assert rc == 0, 'generic 全流程未跑通，导出契约无从断言'
    return {
        'results': tmp_path / 'data' / 'results' / PROJECT,
        'output': tmp_path / 'output' / PROJECT,
    }


def test_level1_full_file_manifest(exported_dirs):
    """a. Level 1 全部文件落盘：按 AGENTS.md 清单逐一断言存在且非空。"""
    missing, empty = [], []
    for name in RESULTS_FILES:
        p = exported_dirs['results'] / name
        if not p.exists():
            missing.append(str(p))
        elif p.stat().st_size == 0:
            empty.append(str(p))
    for name in OUTPUT_FILES:
        p = exported_dirs['output'] / name
        if not p.exists():
            missing.append(str(p))
        elif p.stat().st_size == 0:
            empty.append(str(p))
    assert not missing, f'Level 1 清单缺失文件：{missing}'
    assert not empty, f'Level 1 清单存在空文件：{empty}'


def test_corr_and_lr_column_contract(exported_dirs):
    """b. 新列名契约（corr / LR 宽表）：分群标识列为 `分群维度`/`分群名称`，
    不得出现旧名 `分群值`/`特征名称`。

    注：corr/LR 导出是宽表（特征本身是列，不存在单独的 `特征` 列），
    `特征`/`分群名称` 长表契约（IV 表）已由 test_unit_csv_schema.py 覆盖。
    """
    res_dir = exported_dirs['results']
    for fname in (f'{PROJECT}_特征风险相关性.csv', f'{PROJECT}_逻辑回归系数.csv'):
        df = pd.read_csv(res_dir / fname, encoding='utf-8-sig')
        cols = df.columns.tolist()
        assert '分群维度' in cols, f'{fname} 缺 `分群维度` 列：{cols[:10]}'
        assert '分群名称' in cols, f'{fname} 缺 `分群名称` 列：{cols[:10]}'
        assert '分群值' not in cols, f'{fname} 仍含旧列名 `分群值`'
        assert '特征名称' not in cols, f'{fname} 仍含旧列名 `特征名称`'
        # 宽表至少要有一个特征列（query/visualize 据此取数）
        meta = {'分群维度', '分群名称', '样本数', '坏客户数', '坏客户率', 'AUC', 'AUC类型'}
        feat_cols = [c for c in cols if c not in meta]
        assert feat_cols, f'{fname} 没有任何特征列，下游无数可取'

    # IV 分群表的 `分群维度` 列（test_unit_csv_schema 只断言了 特征/分群名称）
    iv_group = pd.read_csv(res_dir / f'{PROJECT}_IV分析结果_分群.csv', encoding='utf-8-sig')
    assert '分群维度' in iv_group.columns, '_IV分析结果_分群.csv 缺 `分群维度` 列'


def test_audit_json_contract(exported_dirs):
    """c. audit.json 可被 json.load 且含 iv_overfit_features 键。

    （完整结构断言见 test_unit_phase_c.py；此处只护下游依赖的最小契约。）
    """
    audit_path = exported_dirs['results'] / f'{PROJECT}_audit.json'
    with open(audit_path, 'r', encoding='utf-8') as f:
        audit = json.load(f)
    assert 'iv_overfit_features' in audit, 'audit.json 缺 iv_overfit_features 键'
    assert isinstance(audit['iv_overfit_features'], list)


def test_csv_encoding_utf8_sig(exported_dirs):
    """d. CSV 编码契约：utf-8-sig（读首文件前 3 字节验 BOM）。

    下游 load_results / pandas 读取均按 utf-8-sig，丢 BOM 会导致
    Excel 直开乱码；逐一验清单内全部 CSV 的 BOM。
    """
    bom = b'\xef\xbb\xbf'
    csv_files = (
        [exported_dirs['results'] / n for n in RESULTS_FILES if n.endswith('.csv')]
        + [exported_dirs['output'] / n for n in OUTPUT_FILES if n.endswith('.csv')]
    )
    no_bom = []
    for p in csv_files:
        with open(p, 'rb') as f:
            if f.read(3) != bom:
                no_bom.append(p.name)
    assert not no_bom, f'以下 CSV 缺 utf-8-sig BOM：{no_bom}'
