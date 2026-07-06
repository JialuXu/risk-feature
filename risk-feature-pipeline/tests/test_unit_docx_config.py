# -*- coding: utf-8 -*-
"""单元测试：risk_docx_report.scripts.config 的沙盒适配。

- DOCX_VALIDATE_SCRIPT 支持 RISK_DOCX_VALIDATE_SCRIPT 环境变量覆盖；
- DEFAULT_OUTPUT_DIR 懒求值时向 sys.path 注入 PROJECT_ROOT（risk-feature-pipeline/），
  bare-module 导入（sys.path 只含 scripts/ 目录）也能 import risk_pipeline。
"""
from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = _PIPELINE_ROOT / 'risk_docx_report' / 'scripts'


@pytest.fixture()
def reload_docx_config(monkeypatch):
    """返回 reload 函数；teardown 时先摘 env 再 reload，恢复默认模块状态。"""
    def _reload():
        import risk_docx_report.scripts.config as cfg
        return importlib.reload(cfg)

    yield _reload
    # 本 fixture 的 teardown 先于 monkeypatch 复原执行，须手动清 env 后再 reload
    monkeypatch.delenv('RISK_DOCX_VALIDATE_SCRIPT', raising=False)
    _reload()


def test_validate_script_env_override(monkeypatch, tmp_path, reload_docx_config):
    """RISK_DOCX_VALIDATE_SCRIPT 设定时优先生效。"""
    fake = tmp_path / 'validate.py'
    fake.write_text('# stub', encoding='utf-8')
    monkeypatch.setenv('RISK_DOCX_VALIDATE_SCRIPT', str(fake))
    cfg = reload_docx_config()
    assert cfg.DOCX_VALIDATE_SCRIPT == fake


def test_validate_script_default_fallback(monkeypatch, reload_docx_config):
    """未设 env 时回退本机开发布局（兄弟目录 skills/skills/docx）。"""
    monkeypatch.delenv('RISK_DOCX_VALIDATE_SCRIPT', raising=False)
    cfg = reload_docx_config()
    expected = (cfg.WORKSPACE_ROOT / 'skills' / 'skills' / 'docx'
                / 'scripts' / 'office' / 'validate.py')
    assert cfg.DOCX_VALIDATE_SCRIPT == expected


def test_default_output_dir_bare_module_import(tmp_path):
    """bare-module 导入（模拟直接执行脚本）时，DEFAULT_OUTPUT_DIR 能自行把
    PROJECT_ROOT 注入 sys.path 并 import risk_pipeline。

    修复前 __getattr__ 注入的是 WORKSPACE_ROOT（risk_pipeline 不在其下），
    此场景 ImportError。
    """
    (tmp_path / 'data').mkdir()
    code = (
        'import sys;'
        f'sys.path.insert(0, {str(_SCRIPTS_DIR)!r});'
        'import config;'
        'print(config.DEFAULT_OUTPUT_DIR)'
    )
    env = {k: v for k, v in os.environ.items()
           if k not in ('RISK_PROJECT_ROOT', 'RISK_OUTPUT_ROOT',
                        'RISK_DOCX_VALIDATE_SCRIPT', 'PYTHONPATH')}
    r = subprocess.run(
        [sys.executable, '-c', code],
        cwd=str(tmp_path), env=env, capture_output=True, text=True,
    )
    assert r.returncode == 0, f'stderr: {r.stderr}'
    last_line = r.stdout.strip().splitlines()[-1]
    assert last_line == str(tmp_path / 'output' / 'docx-report')
