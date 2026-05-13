# -*- coding: utf-8 -*-
"""端到端 smoke：explore_thresholds 子命令（要求 Level 1 前置）。"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from risk_pipeline import cli


def _make_pairs_csv(path: Path) -> None:
    pd.DataFrame({
        '分群维度': ['企业规模', '企业规模'],
        '分群名称': ['小型企业', '小型企业'],
        '特征': ['feat_1', 'feat_3'],
    }).to_csv(path, index=False, encoding='utf-8-sig')


def test_explore_thresholds_writes_outputs_and_audit(project_workdir, tmp_path):
    # 1. 先跑 generic 抵达 Level 1
    rc = cli.main([
        'run', '--pipeline', 'generic',
        '--wide', project_workdir['wide'],
        '--bad-customer', project_workdir['bad'],
        '--id-col', '客户编号',
        '--target-col', 'is_bad',
        '--project', 'smoke_thr',
        '--quiet', '--confirmed-new-dataset',
    ])
    assert rc == 0

    # 2. 准备 pair list 文件
    pairs_path = tmp_path / 'pairs_smoke.csv'
    _make_pairs_csv(pairs_path)

    # 3. 跑 explore_thresholds
    rc = cli.main([
        'explore_thresholds',
        '--project', 'smoke_thr',
        '--pairs-file', str(pairs_path),
        '--quiet',
    ])
    assert rc == 0

    # 4. 验产物
    root = project_workdir['root']
    summary_path = root / 'data' / 'results' / 'smoke_thr' / 'smoke_thr_候选阈值表.csv'
    detail_path = root / 'data' / 'results' / 'smoke_thr' / 'smoke_thr_候选阈值_分箱明细.csv'
    audit_path = root / 'data' / 'results' / 'smoke_thr' / 'smoke_thr_audit.json'

    assert summary_path.exists(), f'缺失候选阈值表: {summary_path}'
    assert detail_path.exists(), f'缺失分箱明细: {detail_path}'
    assert audit_path.exists(), f'缺失 audit.json: {audit_path}'

    # 5. audit 节点
    with open(audit_path, 'r', encoding='utf-8') as f:
        audit = json.load(f)
    assert 'threshold_candidates' in audit, 'audit.json 缺 threshold_candidates 节点'
    tc = audit['threshold_candidates']
    assert tc['n_pairs_input'] == 2
    # evaluated + skipped 应等于 input
    assert tc['n_pairs_evaluated'] + tc['n_pairs_skipped'] == 2
    # gates 字段必存
    assert 'gates' in tc and 'min_risk_ratio' in tc['gates']

    # export 子命令落的 IV/规则节点不应被覆盖
    assert 'level' in audit, 'audit.json 丢失了原 level 字段（合并应保留）'

    # 6. 候选表 CSV 字段完整性（BUG-4 / NOTE-1 / NOTE-2）
    summary_df = pd.read_csv(summary_path, encoding='utf-8-sig')
    if not summary_df.empty:
        # BUG-4：规则有效=True 时 不通过原因 必为 '-' 哨兵（不是 NaN）
        valid_mask = summary_df['规则有效'] == True  # noqa: E712
        if valid_mask.any():
            assert summary_df.loc[valid_mask, '不通过原因'].eq('-').all(), \
                "规则有效=True 时 '不通过原因' 应是 '-' 哨兵（修 BUG-4）"
        # NOTE-1：候选表必含 IV来源 列
        assert 'IV来源' in summary_df.columns, "候选表缺 IV来源 列（修 NOTE-1）"
        # NOTE-2：候选表必含 切点来源 列
        assert '切点来源' in summary_df.columns, "候选表缺 切点来源 列（修 NOTE-2）"

    # 7. 分箱明细列名汉化（NOTE-3）
    detail_df = pd.read_csv(detail_path, encoding='utf-8-sig')
    if not detail_df.empty:
        expected_cn_cols = {'分箱', '样本数', '坏率', '坏客户数'}
        missing = expected_cn_cols - set(detail_df.columns)
        assert not missing, f"分箱明细缺中文列 {missing}（修 NOTE-3）"
        assert 'Bin' not in detail_df.columns, "分箱明细仍保留英文 'Bin' 列（修 NOTE-3）"

    # 6. state 未推进（保持 Level 1）
    state_path = root / 'data' / 'results' / 'smoke_thr' / '.pipeline_state.json'
    with open(state_path, 'r', encoding='utf-8') as f:
        state = json.load(f)
    assert state['current_level'] == 'Level 1'
    assert state['history'][-1]['cmd'] == 'explore_thresholds'


def test_explore_thresholds_requires_level_1(project_workdir, tmp_path):
    """前置：未到 Level 1（仅 prepare）时应被 require_level 拦下。"""
    rc = cli.main([
        'prepare',
        '--wide', project_workdir['wide'],
        '--bad-customer', project_workdir['bad'],
        '--id-col', '客户编号',
        '--target-col', 'is_bad',
        '--project', 'smoke_thr_block',
        '--quiet', '--confirmed-new-dataset',
    ])
    assert rc == 0

    pairs_path = tmp_path / 'pairs.csv'
    _make_pairs_csv(pairs_path)

    # 子命令应 SystemExit 非 0
    import pytest
    with pytest.raises(SystemExit) as excinfo:
        cli.main([
            'explore_thresholds',
            '--project', 'smoke_thr_block',
            '--pairs-file', str(pairs_path),
            '--quiet',
        ])
    assert excinfo.value.code != 0


def test_explore_thresholds_bad_pairs_file_format(project_workdir, tmp_path):
    """pair-list 文件缺列时给出明确报错。"""
    # 先到 Level 1
    rc = cli.main([
        'run', '--pipeline', 'generic',
        '--wide', project_workdir['wide'],
        '--bad-customer', project_workdir['bad'],
        '--id-col', '客户编号', '--target-col', 'is_bad',
        '--project', 'smoke_thr_bad',
        '--quiet', '--confirmed-new-dataset',
    ])
    assert rc == 0

    bad_pairs = tmp_path / 'bad_pairs.csv'
    # 缺「特征」列
    pd.DataFrame({'分群维度': ['企业规模'], '分群名称': ['小型企业']}).to_csv(
        bad_pairs, index=False, encoding='utf-8-sig',
    )

    import pytest
    with pytest.raises(SystemExit):
        cli.main([
            'explore_thresholds',
            '--project', 'smoke_thr_bad',
            '--pairs-file', str(bad_pairs),
            '--quiet',
        ])
