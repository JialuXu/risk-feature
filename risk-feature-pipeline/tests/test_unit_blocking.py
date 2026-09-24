# -*- coding: utf-8 -*-
"""单元测试：三个阻断节点的 CLI 物理强制。"""
from __future__ import annotations

import json

import pytest

from risk_mining import cli


def _run(argv, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(argv)
    out, err = capsys.readouterr()
    return exc.value.code, out, err


# ===== 阻断节点 1：首次新数据集 =====

def test_block_new_dataset_without_confirm(project_workdir, capsys):
    code, _, err = _run([
        'prepare',
        '--wide', project_workdir['wide'],
        '--bad-customer', project_workdir['bad'],
        '--id-col', '客户编号',
        '--target-col', 'is_bad',
        '--project', 'b1',
    ], capsys)
    assert code == 1
    assert '阻断节点 1' in err
    assert 'confirmed-new-dataset' in err


def test_block_new_dataset_passes_with_confirm(project_workdir):
    rc = cli.main([
        'prepare',
        '--wide', project_workdir['wide'],
        '--bad-customer', project_workdir['bad'],
        '--id-col', '客户编号',
        '--target-col', 'is_bad',
        '--project', 'b1',
        '--confirmed-new-dataset',
    ])
    assert rc == 0


def test_known_dataset_no_confirm_needed(project_workdir):
    """同一数据集第二次跑 prepare，不再需要 --confirmed-new-dataset。"""
    cli.main([
        'prepare',
        '--wide', project_workdir['wide'],
        '--bad-customer', project_workdir['bad'],
        '--id-col', '客户编号',
        '--target-col', 'is_bad',
        '--project', 'b1',
        '--confirmed-new-dataset',
    ])
    # 第二次不带 confirm
    rc = cli.main([
        'prepare',
        '--wide', project_workdir['wide'],
        '--bad-customer', project_workdir['bad'],
        '--id-col', '客户编号',
        '--target-col', 'is_bad',
        '--project', 'b1',
    ])
    assert rc == 0


# ===== 阻断节点 2：trigger features 配置确认 =====

def _setup_level1(project_workdir, project='b2'):
    cli.main([
        'run', '--pipeline', 'generic',
        '--wide', project_workdir['wide'],
        '--bad-customer', project_workdir['bad'],
        '--id-col', '客户编号',
        '--target-col', 'is_bad',
        '--project', project,
        '--quiet', '--confirmed-new-dataset',
    ])


def test_block_trigger_without_confirm(project_workdir, capsys):
    _setup_level1(project_workdir, 'b2')
    code, _, err = _run([
        'trigger', '--project', 'b2',
        '--use-default-features',
    ], capsys)
    assert code == 1
    assert '阻断节点 2' in err


def test_block_trigger_features_file_also_blocked(project_workdir, capsys, tmp_path):
    _setup_level1(project_workdir, 'b2b')
    feat_file = tmp_path / 'feats.json'
    feat_file.write_text('[]', encoding='utf-8')
    code, _, err = _run([
        'trigger', '--project', 'b2b',
        '--features-file', str(feat_file),
    ], capsys)
    assert code == 1
    assert '阻断节点 2' in err
    assert '项目专属' in err


# ===== 阻断节点 3：external 报告确认 =====

def test_block_report_external_without_confirm(project_workdir, capsys, tmp_path):
    _setup_level1(project_workdir, 'b3')
    md = tmp_path / 'report.md'
    md.write_text('# 测试\n', encoding='utf-8')
    code, _, err = _run([
        'report', '--project', 'b3',
        '--report-markdown', str(md),
        '--purpose', 'external',
    ], capsys)
    assert code == 1
    assert '阻断节点 3' in err
    assert 'confirmed-final-version' in err


def test_block_report_internal_no_confirm_needed(project_workdir, capsys, tmp_path):
    """internal 用途不需要 --confirmed-final-version 阻断。

    注意：本测试只验证阻断 flag 不被强制；实际 build_docx_report 调用 Node 渲染器，
    Node 缺失时会抛 SystemExit，但那不是阻断节点 3 的功劳——我们只断言 stderr 里
    没有出现"阻断节点 3"，无论后续是否成功执行到 Node。
    """
    _setup_level1(project_workdir, 'b3i')
    md = tmp_path / 'report.md'
    md.write_text('# 测试\n', encoding='utf-8')
    # internal 不传 --confirmed-final-version；不应被阻断节点 3 拦下
    try:
        cli.main([
            'report', '--project', 'b3i',
            '--report-markdown', str(md),
            '--purpose', 'internal',
        ])
    except SystemExit:
        pass  # Node 缺失等其他失败均忽略
    out, err = capsys.readouterr()
    assert '阻断节点 3' not in err
