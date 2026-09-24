# -*- coding: utf-8 -*-
"""端到端 smoke：trigger 子命令（要求 Level 1 前置 + 自定义 features）。"""
from __future__ import annotations

import json

from risk_mining import cli


def test_trigger_with_custom_features(project_workdir, tmp_path):
    # 先跑 full 抵达 Level 1
    rc = cli.main([
        'run', '--pipeline', 'generic',
        '--wide', project_workdir['wide'],
        '--bad-customer', project_workdir['bad'],
        '--id-col', '客户编号',
        '--target-col', 'is_bad',
        '--project', 'smoke_t',
        '--quiet', '--confirmed-new-dataset',
    ])
    assert rc == 0

    # 自定义 features
    features = [
        {'report_name': 'feat_3', 'source_col': 'feat_3',
         'risk_direction': 'negative', 'iv': 1.02,
         'category': '测试', 'scope': 'full'},
        {'report_name': 'feat_5', 'source_col': 'feat_5',
         'risk_direction': 'positive', 'iv': 0.91,
         'category': '测试', 'scope': 'full'},
    ]
    feat_file = tmp_path / 'features_custom.json'
    with open(feat_file, 'w', encoding='utf-8') as f:
        json.dump(features, f, ensure_ascii=False)

    rc = cli.main([
        'trigger', '--project', 'smoke_t',
        '--features-file', str(feat_file),
        '--quiet', '--confirmed',
    ])
    assert rc == 0

    root = project_workdir['root']
    expected = [
        root / 'output' / 'smoke_t' / 'smoke_t_风险触碰明细_宽表.csv',
        root / 'output' / 'smoke_t' / 'smoke_t_风险触碰明细_长表.csv',
        root / 'output' / 'smoke_t' / 'smoke_t_触碰阈值说明.csv',
    ]
    for p in expected:
        assert p.exists(), f'缺失: {p}'

    # state 推进到 Level 2
    state_path = root / 'data' / 'results' / 'smoke_t' / '.pipeline_state.json'
    with open(state_path, 'r', encoding='utf-8') as f:
        state = json.load(f)
    assert state['current_level'] == 'Level 2'
    assert state['history'][-1]['cmd'] == 'trigger'
