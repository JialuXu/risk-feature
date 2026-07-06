# -*- coding: utf-8 -*-
"""单元测试：CLI 启动时打印的 `[路径]` 状态行（沙盒定位排障用）。"""
from __future__ import annotations

import os

import pytest

from risk_pipeline import cli, paths
from risk_pipeline.paths import ENV_OUTPUT_ROOT, ENV_PROJECT_ROOT


@pytest.fixture(autouse=True)
def isolated_root(monkeypatch, tmp_path):
    """清空 env、把 CWD 切到含 data/ 的临时目录，让根解析确定为 tmp_path。"""
    monkeypatch.delenv(ENV_PROJECT_ROOT, raising=False)
    monkeypatch.delenv(ENV_OUTPUT_ROOT, raising=False)
    paths._warned_no_data_dir.clear()
    (tmp_path / 'data').mkdir()
    monkeypatch.chdir(tmp_path)


def _run(argv):
    """跑 CLI；query 在项目不存在时 _err → SystemExit，属预期。"""
    try:
        cli.main(argv)
    except SystemExit:
        pass


def test_roots_stamp_printed(capsys, tmp_path):
    _run(['query', '--project', '__不存在的项目__', '--kind', 'iv'])
    out = capsys.readouterr().out
    assert '[路径]' in out
    assert f'项目根={tmp_path}' in out
    assert f'输出根={tmp_path}' in out


def test_roots_stamp_suppressed_by_quiet(capsys):
    _run(['query', '--project', '__不存在的项目__', '--kind', 'iv', '--quiet'])
    assert '[路径]' not in capsys.readouterr().out


def test_roots_stamp_respects_output_root_env(capsys, monkeypatch, tmp_path):
    out_root = tmp_path / 'out_ws'
    out_root.mkdir()
    monkeypatch.setenv(ENV_OUTPUT_ROOT, str(out_root))
    _run(['query', '--project', '__不存在的项目__', '--kind', 'iv'])
    out = capsys.readouterr().out
    assert f'输出根={os.path.normpath(str(out_root))}' in out
    assert f'项目根={tmp_path}' in out
