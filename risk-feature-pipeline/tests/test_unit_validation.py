# -*- coding: utf-8 -*-
"""单元测试：CLI 输入校验（缺文件 / 缺字段时正确退出 + 提示）。"""
from __future__ import annotations

import pytest

from risk_pipeline import cli


def _run(argv, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(argv)
    out, err = capsys.readouterr()
    return exc.value.code, out, err


def test_prepare_missing_wide(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    code, _, err = _run([
        'prepare',
        '--wide', 'no_such.csv',
        '--id-col', '客户编号',
        '--target-col', 'is_bad',
        '--project', 'p1',
    ], capsys)
    assert code == 1
    assert '宽表文件不存在' in err


def test_analyze_missing_prepared(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    code, _, err = _run([
        'analyze', '--project', 'p1',
    ], capsys)
    assert code == 1
    assert 'prepared.csv 不存在' in err
    assert 'python -m risk_pipeline prepare' in err


def test_export_missing_intermediate(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    code, _, err = _run([
        'export', '--project', 'p1',
    ], capsys)
    assert code == 1
    assert '_intermediate/ 不存在' in err
    assert 'python -m risk_pipeline analyze' in err


def test_analyze_invalid_step(project_workdir, capsys):
    # 先跑 prepare 让 features.json 存在
    cli.main([
        'prepare',
        '--wide', project_workdir['wide'],
        '--bad-customer', project_workdir['bad'],
        '--id-col', '客户编号',
        '--target-col', 'is_bad',
        '--project', 'p1',
        '--confirmed-new-dataset',
    ])
    code, _, err = _run([
        'analyze', '--project', 'p1',
        '--steps', 'unknown_step',
    ], capsys)
    assert code == 1
    assert '无效 steps' in err


def test_analyze_rejects_export_in_steps(project_workdir, capsys):
    cli.main([
        'prepare',
        '--wide', project_workdir['wide'],
        '--bad-customer', project_workdir['bad'],
        '--id-col', '客户编号',
        '--target-col', 'is_bad',
        '--project', 'p1',
        '--confirmed-new-dataset',
    ])
    code, _, err = _run([
        'analyze', '--project', 'p1',
        '--steps', 'iv,export',
    ], capsys)
    assert code == 1
    assert 'export' in err
    assert '禁止' in err


def test_rules_only_rejects_new_category_dim(project_workdir, capsys):
    """rules-only 跑时若 --category-dims 引入 manifest 没有的维度，应报错。

    覆盖之前的静默失效路径：rules-only 分支直接采纳 CLI 传入的 category_dims，
    但下游 cmd_export 读旧 manifest，导致新维度悄悄失效。修复后应直接拦截。
    """
    project = 'p_rules_dim'
    # 1) prepare
    cli.main([
        'prepare',
        '--wide', project_workdir['wide'],
        '--bad-customer', project_workdir['bad'],
        '--id-col', '客户编号',
        '--target-col', 'is_bad',
        '--project', project,
        '--confirmed-new-dataset',
    ])
    # 2) 前置 analyze 只跑了 企业规模 一个维度
    rc = cli.main([
        'analyze', '--project', project,
        '--steps', 'univariate,iv,lr',
        '--category-dims', '企业规模',
        '--quiet',
    ])
    assert rc == 0
    # 3) rules-only 时传入未在 manifest 中的维度 → 拦截
    code, _, err = _run([
        'analyze', '--project', project,
        '--steps', 'rules',
        '--category-dims', '行业',  # 没出现在前置 manifest
    ], capsys)
    assert code == 1
    assert '不在前置维度中' in err
    assert '行业' in err


def test_trigger_requires_level1(project_workdir, capsys):
    """没跑 export 就直接 trigger，应被 Level 守护拦下。"""
    cli.main([
        'prepare',
        '--wide', project_workdir['wide'],
        '--bad-customer', project_workdir['bad'],
        '--id-col', '客户编号',
        '--target-col', 'is_bad',
        '--project', 'p1',
        '--confirmed-new-dataset',
    ])
    code, _, err = _run([
        'trigger', '--project', 'p1',
        '--use-default-features',
        '--confirmed',
    ], capsys)
    assert code == 1
    assert 'Level 1' in err
