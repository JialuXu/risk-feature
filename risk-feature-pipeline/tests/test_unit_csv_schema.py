# -*- coding: utf-8 -*-
"""A4 / A5 单测：CSV 列名统一 + 文件改名兼容副本。"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from risk_mining import cli


def test_unified_column_names_and_filename_aliases(project_workdir):
    """跑一遍 generic 全流程，验证：
    1. _IV分析结果_全量.csv（A5 新名）存在，列里有 `特征` 而非 `特征名称`
    2. _IV分析结果_分群.csv（A5 新名）存在，列里有 `分群名称` 而非 `分群值`
    3. _IV分析结果.csv / _IV值分析.csv 兼容副本仍存在（一个版本后移除）
    4. results_loader 能把旧列名自动 normalize
    """
    rc = cli.main([
        'run', '--pipeline', 'generic',
        '--wide', project_workdir['wide'],
        '--bad-customer', project_workdir['bad'],
        '--id-col', '客户编号',
        '--target-col', 'is_bad',
        '--project', 'schema_check',
        '--confirmed-new-dataset',
    ])
    assert rc == 0

    root = Path(project_workdir['root'])
    res_dir = root / 'data' / 'results' / 'schema_check'

    new_full = res_dir / 'schema_check_IV分析结果_全量.csv'
    new_group = res_dir / 'schema_check_IV分析结果_分群.csv'
    legacy_full = res_dir / 'schema_check_IV分析结果.csv'
    legacy_group = res_dir / 'schema_check_IV值分析.csv'

    assert new_full.exists(), 'A5 新名 _IV分析结果_全量.csv 缺失'
    assert new_group.exists(), 'A5 新名 _IV分析结果_分群.csv 缺失'
    assert legacy_full.exists(), 'A5 兼容副本 _IV分析结果.csv 缺失（一个版本后移除）'
    assert legacy_group.exists(), 'A5 兼容副本 _IV值分析.csv 缺失（一个版本后移除）'

    # 全量表：列必须是「特征」（不是「特征名称」）
    iv_full = pd.read_csv(new_full, encoding='utf-8-sig')
    assert '特征' in iv_full.columns, f"_IV分析结果_全量.csv 缺 '特征' 列：{iv_full.columns.tolist()}"
    assert '特征名称' not in iv_full.columns, '_IV分析结果_全量.csv 仍含旧列 特征名称'

    # 分群表：分群标识列必须是「分群名称」（不是「分群值」）
    iv_group = pd.read_csv(new_group, encoding='utf-8-sig')
    assert '分群名称' in iv_group.columns, f"_IV分析结果_分群.csv 缺 '分群名称' 列：{iv_group.columns.tolist()}"
    assert '分群值' not in iv_group.columns

    # 兼容副本与新文件内容一致
    legacy_iv_full = pd.read_csv(legacy_full, encoding='utf-8-sig')
    assert '特征' in legacy_iv_full.columns

    # results_loader 读取兼容性：删掉新文件，应该还能从旧名读出来
    new_full.unlink()
    new_group.unlink()
    from risk_result_query.scripts.results_loader import load_results
    r = load_results('schema_check', project_root=str(root))
    assert r.iv_full is not None and not r.iv_full.empty
    assert '特征' in r.iv_full.columns
    assert r.iv_group_all is not None and not r.iv_group_all.empty
    assert '分群名称' in r.iv_group_all.columns


def test_legacy_column_normalize_on_read(tmp_path):
    """results_loader 读取含旧列名的 CSV 时，自动 rename 为新列名。"""
    from risk_result_query.scripts.results_loader import _normalize_legacy_cols
    legacy = pd.DataFrame({'特征名称': ['A', 'B'], 'IV值': [0.1, 0.2], '分群值': ['s1', 's2']})
    normalized = _normalize_legacy_cols(legacy)
    assert '特征' in normalized.columns
    assert '分群名称' in normalized.columns
    assert '特征名称' not in normalized.columns
    assert '分群值' not in normalized.columns
