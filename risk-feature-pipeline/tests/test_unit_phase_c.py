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
