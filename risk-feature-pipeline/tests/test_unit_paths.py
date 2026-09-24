# -*- coding: utf-8 -*-
"""单元测试：risk_core.paths 的优先级与友好报错。"""
from __future__ import annotations

import os
import stat

import pytest

from risk_core import paths
from risk_core.paths import (
    ENV_OUTPUT_ROOT,
    ENV_PROJECT_ROOT,
    ensure_writable_dir,
    get_output_root,
    get_project_root,
    output_dir,
    results_dir,
    unified_results_dir,
)


@pytest.fixture(autouse=True)
def clear_env(monkeypatch):
    """每个用例都先把环境变量清空，避免外部 export 污染。"""
    monkeypatch.delenv(ENV_PROJECT_ROOT, raising=False)
    monkeypatch.delenv(ENV_OUTPUT_ROOT, raising=False)
    paths._warned_no_data_dir.clear()


def test_env_project_root_wins(tmp_path, monkeypatch):
    """RISK_PROJECT_ROOT 优先级最高，不验证 data/ 是否存在。"""
    monkeypatch.setenv(ENV_PROJECT_ROOT, str(tmp_path))
    monkeypatch.chdir('/')
    assert get_project_root() == os.path.normpath(str(tmp_path))


def test_env_project_root_expands(tmp_path, monkeypatch):
    """支持 ${VAR} 与 ~/ 展开。"""
    monkeypatch.setenv('FOO_BASE', str(tmp_path))
    monkeypatch.setenv(ENV_PROJECT_ROOT, '${FOO_BASE}')
    assert get_project_root() == os.path.normpath(str(tmp_path))


def test_walk_up_finds_data_dir(tmp_path, monkeypatch):
    """无 env 时从 CWD 向上找 data/。"""
    (tmp_path / 'data').mkdir()
    sub = tmp_path / 'a' / 'b'
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)
    assert get_project_root() == str(tmp_path.resolve())


def test_walk_up_uses_start_argument(tmp_path, monkeypatch):
    """显式传 start 时从 start 向上找。"""
    (tmp_path / 'data').mkdir()
    other = tmp_path.parent
    monkeypatch.chdir(other)  # CWD 找不到 data/
    sub = tmp_path / 'a'
    sub.mkdir()
    assert get_project_root(start=sub) == str(tmp_path.resolve())


def test_no_data_falls_back_to_cwd(tmp_path, monkeypatch, capsys):
    """找不到 data/ 时回落到 CWD，且打印 WARN 提示设置 env。"""
    monkeypatch.chdir(tmp_path)
    result = get_project_root()
    assert result == str(tmp_path.resolve())
    captured = capsys.readouterr()
    assert '[WARN]' in captured.out
    assert ENV_PROJECT_ROOT in captured.out


def test_no_data_warn_only_once(tmp_path, monkeypatch, capsys):
    """连续两次回落 CWD 只打印一次 WARN。"""
    monkeypatch.chdir(tmp_path)
    get_project_root()
    capsys.readouterr()  # 丢弃第一次
    get_project_root()
    captured = capsys.readouterr()
    assert '[WARN]' not in captured.out


def test_output_root_falls_back_to_project_root(tmp_path, monkeypatch):
    """未设 RISK_OUTPUT_ROOT 时复用 get_project_root()。"""
    monkeypatch.setenv(ENV_PROJECT_ROOT, str(tmp_path))
    assert get_output_root() == os.path.normpath(str(tmp_path))


def test_output_root_env_wins(tmp_path, monkeypatch):
    """RISK_OUTPUT_ROOT 与 RISK_PROJECT_ROOT 独立生效。"""
    proj = tmp_path / 'proj'
    out = tmp_path / 'out'
    proj.mkdir()
    out.mkdir()
    monkeypatch.setenv(ENV_PROJECT_ROOT, str(proj))
    monkeypatch.setenv(ENV_OUTPUT_ROOT, str(out))
    assert get_project_root() == os.path.normpath(str(proj))
    assert get_output_root() == os.path.normpath(str(out))


def test_results_dir_compose(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_OUTPUT_ROOT, str(tmp_path))
    assert results_dir() == os.path.join(str(tmp_path), 'data', 'results')
    assert results_dir('myproj') == os.path.join(str(tmp_path), 'data', 'results', 'myproj')


def test_output_dir_compose(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_OUTPUT_ROOT, str(tmp_path))
    assert output_dir() == os.path.join(str(tmp_path), 'output')
    assert output_dir('myproj') == os.path.join(str(tmp_path), 'output', 'myproj')


def test_ensure_writable_dir_creates(tmp_path):
    target = tmp_path / 'a' / 'b' / 'c'
    ensure_writable_dir(target)
    assert target.is_dir()


def test_ensure_writable_dir_idempotent(tmp_path):
    target = tmp_path / 'x'
    ensure_writable_dir(target)
    ensure_writable_dir(target)  # 不该报错
    assert target.is_dir()


@pytest.mark.skipif(os.geteuid() == 0, reason='root 无视权限位')
def test_ensure_writable_dir_permission_error_message(tmp_path):
    """不可写目录下应抛 RuntimeError，文案要包含 RISK_OUTPUT_ROOT。"""
    readonly = tmp_path / 'readonly'
    readonly.mkdir()
    readonly.chmod(stat.S_IRUSR | stat.S_IXUSR)  # 只读 + 可遍历
    try:
        with pytest.raises(RuntimeError) as exc_info:
            ensure_writable_dir(readonly / 'sub')
        msg = str(exc_info.value)
        assert ENV_OUTPUT_ROOT in msg
        assert '无写权限' in msg
    finally:
        readonly.chmod(stat.S_IRWXU)


def test_yaml_expandvars(tmp_path, monkeypatch):
    """config_loader 应展开 YAML 字符串里的 ${VAR}。"""
    from risk_core.config_loader import load_yaml

    monkeypatch.setenv('TEST_BASE', '/expanded/base')
    yaml_path = tmp_path / 'cfg.yaml'
    yaml_path.write_text(
        'paths:\n'
        '  raw: "${TEST_BASE}/raw.csv"\n'
        '  list:\n'
        '    - "${TEST_BASE}/a"\n'
        '    - "literal"\n',
        encoding='utf-8',
    )
    cfg = load_yaml(yaml_path)
    assert cfg['paths']['raw'] == '/expanded/base/raw.csv'
    assert cfg['paths']['list'] == ['/expanded/base/a', 'literal']


def test_config_constants_use_output_root(tmp_path, monkeypatch):
    """RISK_OUTPUT_ROOT 设置后再 import config，常量应是绝对路径。"""
    monkeypatch.setenv(ENV_OUTPUT_ROOT, str(tmp_path))
    # 强制重载 config 模块以拾取新 env
    import importlib
    import risk_core.config as cfg_mod
    importlib.reload(cfg_mod)
    try:
        assert os.path.isabs(cfg_mod.OUTPUT_DIR_CREDIT)
        assert cfg_mod.OUTPUT_DIR_CREDIT.startswith(str(tmp_path))
        assert os.path.isabs(cfg_mod.RESULTS_DIR_CREDIT)
    finally:
        monkeypatch.delenv(ENV_OUTPUT_ROOT, raising=False)
        importlib.reload(cfg_mod)


def test_config_constants_relative_without_env(monkeypatch):
    """未设 env 时常量仍是相对路径，保持向后兼容。"""
    monkeypatch.delenv(ENV_OUTPUT_ROOT, raising=False)
    import importlib
    import risk_core.config as cfg_mod
    importlib.reload(cfg_mod)
    assert not os.path.isabs(cfg_mod.OUTPUT_DIR_CREDIT)
    assert cfg_mod.OUTPUT_DIR_CREDIT == 'output/征信'


# B10: unified_results_dir 辅助
def test_unified_results_dir_default_level1(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_OUTPUT_ROOT, str(tmp_path))
    p = unified_results_dir('foo')
    assert p == os.path.join(str(tmp_path), 'data', 'results', 'foo', 'level1')


def test_unified_results_dir_level2(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_OUTPUT_ROOT, str(tmp_path))
    p = unified_results_dir('foo', 'level2')
    assert p == os.path.join(str(tmp_path), 'data', 'results', 'foo', 'level2')


def test_unified_results_dir_invalid_level_raises(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV_OUTPUT_ROOT, str(tmp_path))
    with pytest.raises(ValueError, match='level1'):
        unified_results_dir('foo', 'level99')
