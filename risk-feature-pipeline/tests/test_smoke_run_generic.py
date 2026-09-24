# -*- coding: utf-8 -*-
"""端到端 smoke：run --pipeline generic 全流程，断言 Level 1 文件落盘 + state 正确。"""
from __future__ import annotations

import json

from risk_mining import cli


def test_run_generic_full_cycle(project_workdir):
    rc = cli.main([
        'run', '--pipeline', 'generic',
        '--wide', project_workdir['wide'],
        '--bad-customer', project_workdir['bad'],
        '--id-col', '客户编号',
        '--target-col', 'is_bad',
        '--project', 'smoke_full',
        '--confirmed-new-dataset',
    ])
    assert rc == 0

    root = project_workdir['root']

    # Level 1 关键文件落盘
    expected = [
        root / 'data' / 'results' / 'smoke_full' / 'smoke_full_IV分析结果.csv',
        root / 'data' / 'results' / 'smoke_full' / 'smoke_full_综合特征分析结果.csv',
        root / 'output' / 'smoke_full' / 'smoke_full_LLM报告数据.json',
    ]
    for p in expected:
        assert p.exists(), f'缺失: {p}'

    # state.json 推进到 Level 1
    state_path = root / 'data' / 'results' / 'smoke_full' / '.pipeline_state.json'
    assert state_path.exists()
    with open(state_path, 'r', encoding='utf-8') as f:
        state = json.load(f)
    assert state['current_level'] == 'Level 1'

    cmds = [h['cmd'] for h in state['history']]
    assert cmds == ['prepare', 'analyze', 'export']


def test_run_generic_single_dim(project_workdir):
    """单维快路径：只跑 企业规模 一个维度。"""
    rc = cli.main([
        'run', '--pipeline', 'generic',
        '--wide', project_workdir['wide'],
        '--bad-customer', project_workdir['bad'],
        '--id-col', '客户编号',
        '--target-col', 'is_bad',
        '--project', 'smoke_single',
        '--confirmed-new-dataset',
    ])
    assert rc == 0

    # 之后 analyze 单维（覆盖之前的 _intermediate）
    rc = cli.main([
        'analyze', '--project', 'smoke_single',
        '--steps', 'iv',
        '--category-dims', '企业规模',
        '--qual-dims', '',
    ])
    assert rc == 0

    # state 现在应该是过渡态（analyze 不改 Level 1 → Level 1，因为不会回退）
    # 实际：analyze 只 promote 到过渡态；当前 Level 是 Level 1，更高，不回退
    root = project_workdir['root']
    state_path = root / 'data' / 'results' / 'smoke_single' / '.pipeline_state.json'
    with open(state_path, 'r', encoding='utf-8') as f:
        state = json.load(f)
    assert state['current_level'] == 'Level 1'  # 不回退
    cmds = [h['cmd'] for h in state['history']]
    assert cmds[-1] == 'analyze'
