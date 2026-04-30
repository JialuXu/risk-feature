# -*- coding: utf-8 -*-
"""Phase C 单测：阈值精度自适应 / audit.json / 拆分版确认 flag。"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from risk_pipeline import cli
from risk_rule_mining.scripts.rule_extraction import _format_threshold


# ---------- C11: 阈值精度自适应 ----------

def test_format_threshold_amount_large():
    assert _format_threshold(2.112e7, '授信总金额') == '21,120,000'


def test_format_threshold_amount_small():
    assert _format_threshold(123.4, '资金余额') == '123'


def test_format_threshold_ratio_priority_over_amount():
    """资产负债率含 '资产' 但本质是比率（应走 2 位小数分支，不应 round 到整数）。"""
    assert _format_threshold(0.7501, '资产负债率') == '0.75'


def test_format_threshold_ratio():
    assert _format_threshold(0.1197, '非银机构占比') == '0.12'


def test_format_threshold_default():
    assert _format_threshold(0.1197, '某衍生指标') == '0.1197'


def test_format_threshold_no_name():
    assert _format_threshold(0.5, '') == '0.5'


# ---------- C12: audit.json ----------

def test_audit_json_after_export(project_workdir):
    """跑完 generic 全流程后，应当生成 _audit.json 并含正确结构。"""
    rc = cli.main([
        'run', '--pipeline', 'generic',
        '--wide', project_workdir['wide'],
        '--bad-customer', project_workdir['bad'],
        '--id-col', '客户编号', '--target-col', 'is_bad',
        '--project', 'audit_check',
        '--confirmed-new-dataset',
    ])
    assert rc == 0

    audit_path = Path(project_workdir['root']) / 'data' / 'results' / 'audit_check' / 'audit_check_audit.json'
    assert audit_path.exists(), 'audit.json 未生成'

    with open(audit_path, 'r', encoding='utf-8') as f:
        audit = json.load(f)

    # 必要键
    assert audit['project_name'] == 'audit_check'
    assert audit['level'] == 'Level 1'
    assert 'iv_overfit_features' in audit
    assert 'unstable_rules' in audit
    assert 'created_at' in audit
    assert audit['n_exported'] >= 5  # 至少 5 个文件已落盘
    # 类型
    assert isinstance(audit['iv_overfit_features'], list)
    assert isinstance(audit['unstable_rules'], list)


# ---------- C15: 拆分版确认 flag ----------

def test_split_confirmation_pass(project_workdir):
    """拆分版三项一致 → 通过阻断节点 1。"""
    rc = cli.main([
        'prepare',
        '--wide', project_workdir['wide'],
        '--bad-customer', project_workdir['bad'],
        '--id-col', '客户编号', '--target-col', 'is_bad',
        '--project', 'c15_split_pass',
        '--confirmed-id-col', '客户编号',
        '--confirmed-target-col', 'is_bad',
        '--confirmed-target-positive', '1',
    ])
    assert rc == 0

    # features.json 中应记录 confirmation.mode='split'
    feats_path = Path(project_workdir['root']) / 'data' / 'processed' / 'c15_split_pass' / 'features.json'
    assert feats_path.exists()
    with open(feats_path, 'r', encoding='utf-8') as f:
        info = json.load(f)
    assert info['confirmation']['mode'] == 'split'
    assert info['confirmation']['id_col'] == '客户编号'
    assert info['confirmation']['target_positive'] == '1'


def test_split_confirmation_partial_fails(project_workdir):
    """只填一项 → 报错（必须三项齐发）。"""
    with pytest.raises(SystemExit):
        cli.main([
            'prepare',
            '--wide', project_workdir['wide'],
            '--bad-customer', project_workdir['bad'],
            '--id-col', '客户编号', '--target-col', 'is_bad',
            '--project', 'c15_partial',
            '--confirmed-id-col', '客户编号',
            # 故意不传 --confirmed-target-col / --confirmed-target-positive
        ])


def test_split_confirmation_mismatch_fails(project_workdir):
    """拆分确认值与主参数不一致 → 报错。"""
    with pytest.raises(SystemExit):
        cli.main([
            'prepare',
            '--wide', project_workdir['wide'],
            '--bad-customer', project_workdir['bad'],
            '--id-col', '客户编号', '--target-col', 'is_bad',
            '--project', 'c15_mismatch',
            '--confirmed-id-col', '客户号',     # 不一致！
            '--confirmed-target-col', 'is_bad',
            '--confirmed-target-positive', '1',
        ])


def test_legacy_confirmation_still_works(project_workdir):
    """旧 --confirmed-new-dataset 单独使用仍生效。"""
    rc = cli.main([
        'prepare',
        '--wide', project_workdir['wide'],
        '--bad-customer', project_workdir['bad'],
        '--id-col', '客户编号', '--target-col', 'is_bad',
        '--project', 'c15_legacy',
        '--confirmed-new-dataset',
    ])
    assert rc == 0
    feats_path = Path(project_workdir['root']) / 'data' / 'processed' / 'c15_legacy' / 'features.json'
    with open(feats_path, 'r', encoding='utf-8') as f:
        info = json.load(f)
    assert info['confirmation']['mode'] == 'legacy'


# ---------- 微调 1：query kind='iv' 误传 dim/group 警告 ----------

def test_top_features_iv_with_dim_warns():
    """top_features(kind='iv', dim=...) 应当 warn 而非静默忽略。"""
    import warnings
    from risk_result_query.scripts.results_loader import top_features, Results
    fake_iv = pd.DataFrame({'特征': ['A', 'B', 'C'], 'IV值': [0.5, 0.3, 0.1]})
    r = Results(project_name='x', results_dir='.', iv_full=fake_iv)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        out = top_features(r, kind='iv', dim='企业规模', n=2)
    assert len(out) == 2
    assert any('iv_group' in str(w.message) for w in caught), '应提示改用 iv_group'


def test_top_features_iv_no_warning_without_dim_group():
    """top_features(kind='iv') 不传 dim/group 时不应 warn。"""
    import warnings
    from risk_result_query.scripts.results_loader import top_features, Results
    fake_iv = pd.DataFrame({'特征': ['A', 'B'], 'IV值': [0.5, 0.3]})
    r = Results(project_name='x', results_dir='.', iv_full=fake_iv)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        top_features(r, kind='iv', n=2)
    assert not any('iv_group' in str(w.message) for w in caught)


# ---------- 微调 2：keep_metadata_cols 应能保留非默认列（如「内部评级」） ----------

def test_keep_metadata_cols_includes_non_default_columns(tmp_path):
    """keep_metadata_cols 指定的非白名单列（如「内部评级」）也要被带进宽表。"""
    from risk_trigger_extraction.scripts.trigger_extraction import extract_triggers

    df = pd.DataFrame({
        '客户编号': ['A', 'B', 'C'],
        'is_bad':   [0, 1, 0],
        '企业规模': ['大', '小', '大'],
        '所属行业': ['金融', '制造', '金融'],
        '内部评级': ['AA', 'B', 'A'],
        'feat_x':   [0.1, 0.9, 0.5],
    })
    features = [{
        'report_name': 'feat_x', 'source_col': 'feat_x',
        'risk_direction': 'positive', 'iv': 0.4,
        'category': 'test', 'scope': 'full',
    }]
    df_wide, _, _ = extract_triggers(
        df=df, features=features,
        project_name='unit_keep_metadata',
        output_dir=str(tmp_path), verbose=False,
        keep_metadata_cols=['企业规模', '所属行业', '内部评级'],
    )
    # 三项都应在 wide 表里
    assert '企业规模' in df_wide.columns
    assert '所属行业' in df_wide.columns
    assert '内部评级' in df_wide.columns, '内部评级 不在默认白名单，但用户显式 keep 应保留'


def test_keep_metadata_cols_missing_in_widetable_warns(tmp_path, capsys):
    """keep_metadata_cols 指定的列在宽表中不存在时应给出 warn 不静默。"""
    from risk_trigger_extraction.scripts.trigger_extraction import extract_triggers

    df = pd.DataFrame({
        '客户编号': ['A', 'B'],
        'is_bad':   [0, 1],
        '企业规模': ['大', '小'],
        'feat_x':   [0.1, 0.9],
    })
    features = [{
        'report_name': 'feat_x', 'source_col': 'feat_x',
        'risk_direction': 'positive', 'iv': 0.4,
        'category': 'test', 'scope': 'full',
    }]
    extract_triggers(
        df=df, features=features,
        project_name='unit_keep_missing',
        output_dir=str(tmp_path), verbose=True,
        keep_metadata_cols=['企业规模', '不存在的列'],
    )
    out, _ = capsys.readouterr()
    assert '不存在的列' in out and 'WARN' in out
