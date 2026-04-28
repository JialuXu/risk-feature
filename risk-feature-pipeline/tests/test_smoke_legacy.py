# -*- coding: utf-8 -*-
"""legacy smoke：验证老入口 `python -m shared` 仍工作 + 打 deprecation 警告。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


_ROOT = Path(__file__).resolve().parent.parent


def _run_module(args, cwd):
    """以子进程跑 `python -m <module> args`，返回 (returncode, stdout, stderr)。"""
    cmd = [sys.executable, '-m'] + args
    env = {'PYTHONPATH': str(_ROOT), 'PATH': '/usr/bin:/bin:/usr/local/bin'}
    import os as _os
    env['HOME'] = _os.environ.get('HOME', '')
    proc = subprocess.run(
        cmd, cwd=str(cwd), env=env,
        capture_output=True, text=True, timeout=30,
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_shared_help_prints_deprecation(tmp_path):
    rc, out, err = _run_module(['shared', '--help'], cwd=tmp_path)
    # --help 老入口是直接被 argparse 捕获 → exit 0；deprecation 在 import shared 时打
    assert '[DEPRECATION]' in err
    # argparse 的 help 文案
    assert '--pipeline' in out


def test_shared_module_import_still_works(tmp_path):
    """import shared.config 在 Python 内仍可工作（兼容 shim）。"""
    code = (
        'import warnings\n'
        'warnings.simplefilter("error", DeprecationWarning)\n'  # 视警告为错误
        'try:\n'
        '    from shared.config import COL_TARGET\n'
        '    print(f"COL_TARGET={COL_TARGET}")\n'
        '    raise RuntimeError("did not warn")\n'
        'except DeprecationWarning as w:\n'
        '    print(f"DEPRECATION_OK: {w}")\n'
    )
    proc = subprocess.run(
        [sys.executable, '-c', code],
        env={'PYTHONPATH': str(_ROOT)},
        capture_output=True, text=True, timeout=10,
    )
    assert 'DEPRECATION_OK' in proc.stdout
