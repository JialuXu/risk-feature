# -*- coding: utf-8 -*-
"""解耦重构 Stage 2 不变量锁：统一 CLI 入口转发到组合根 risk_mining，9 子命令可分发。

锁住「入口保号」与「命令拆包」两个约束，防止后续阶段无声破坏：
  - `python -m risk_pipeline` / `from risk_pipeline import cli` 仍解析且 main 转发 risk_mining.cli
  - cli.main 靠 getattr(commands, f'cmd_{子命令}') 分发，故 9 个 cmd_* 必须都在 risk_mining.commands
"""
import contextlib
import io

import pytest

import risk_mining.cli
import risk_mining.commands
from risk_pipeline import cli as rp_cli

_SUBCOMMANDS = [
    'prepare', 'analyze', 'export', 'query', 'visualize',
    'trigger', 'explore_thresholds', 'report', 'run',
]


def test_cli_main_forwards_to_risk_mining():
    """risk_pipeline.cli.main 必须就是组合根 risk_mining.cli.main（同一对象）。"""
    assert rp_cli.main is risk_mining.cli.main


def test_cli_commands_shim_forwards_all_cmds():
    """旧路径 risk_pipeline.cli_commands.cmd_X 逐个转发到 risk_mining.commands.cmd_X。"""
    import risk_pipeline.cli_commands as shim
    for name in _SUBCOMMANDS:
        assert getattr(shim, f'cmd_{name}') is getattr(risk_mining.commands, f'cmd_{name}')


def test_all_subcommands_dispatchable_via_commands():
    """cli.main 的分发依赖 getattr(commands, f'cmd_{子命令}')，9 个必须全在且可调用。"""
    for name in _SUBCOMMANDS:
        assert callable(getattr(risk_mining.commands, f'cmd_{name}')), f'cmd_{name} 不可分发'


def test_help_renders_for_top_and_every_subcommand():
    """顶层 + 9 子命令 --help 均应正常渲染（argparse help → SystemExit(0)）。"""
    parser = risk_mining.cli._build_parser()
    for argv in [['--help']] + [[sc, '--help'] for sc in _SUBCOMMANDS]:
        with pytest.raises(SystemExit) as ei, contextlib.redirect_stdout(io.StringIO()):
            parser.parse_args(argv)
        assert ei.value.code == 0, f'{argv} help 退出码 != 0'
