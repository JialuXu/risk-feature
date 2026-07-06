# -*- coding: utf-8 -*-
"""解耦重构 Stage 4 不变量锁：argspec 单一注册表 + run 并集派生 + 转发完整性。

锁住三条设计验证要求（DECOUPLING-DESIGN §9 阶段4「验证」列）：
  1. **prepare 每 flag 在 run 路径真到达 cmd_prepare**（analyze 同理到 cmd_analyze）——
     测试**迭代 argspec 本身**生成命令行与期望值，未来给 prepare/analyze 新增 flag
     无需改本测试即自动纳入覆盖；若 run 并集派生或 _forward_ns 转发漏掉任何 dest，
     此处立即红。
  2. **无 argparse dest 冲突**——_build_parser() 构建期 argparse 对重复 option-string
     直接抛 ArgumentError；外加 spec 级重复检查。
  3. **run 的 --steps 必须保持 default=None**——analyze 的默认 'univariate,iv,lr' 若
     泄漏进 run，会吞掉 generic 兜底 'univariate,iv,lr,rules'（静默丢 rules），并让
     credit/gsfc 的 steps=None（全跑）语义失效。这是设计文档点名的坑，单独锁死。

（--help 字节对比属一次性阶段验收，人工完成：顶层 + 8 个非 run 子命令与阶段 4 之前
逐字节一致；run 仅多出并集带来的 --prepared/--features-file/--qual-dims/--project-name。）
"""
from __future__ import annotations

import pytest

import risk_mining.cli
from risk_mining import argspec
from risk_mining.commands import run as run_mod


def _plain_entries(cmd):
    return list(argspec._iter_plain(argspec.flags_for(cmd)))


def _optstrings(cmd):
    return [o for e in _plain_entries(cmd) for o in e['opts']]


# ---------------------------------------------------------------------------
# 不变量2：注册表自洽 + 构建无冲突
# ---------------------------------------------------------------------------

def test_parser_builds_and_no_dest_conflicts():
    """_build_parser() 全量构建成功（argparse 对重复 option-string 抛错即红）；
    且每个子命令（含派生的 run）的 option-string 在命令内无重复。"""
    parser = risk_mining.cli._build_parser()
    assert parser is not None
    for cmd in argspec.SUBCOMMAND_ORDER:
        opts = _optstrings(cmd)
        assert len(opts) == len(set(opts)), f'{cmd} 存在重复 option-string：{opts}'


def test_run_flags_superset_of_prepare_union_analyze():
    """run 的 flag 集必须 ⊇ prepare∪analyze（并集派生的定义性质）。"""
    run_opts = set(_optstrings('run'))
    for src in ('prepare', 'analyze'):
        missing = set(_optstrings(src)) - run_opts
        assert not missing, f'run 缺 {src} 的 flag：{missing}（并集派生断裂？）'


def test_run_required_all_downgraded():
    """run 并集里 required 一律降 False（generic 必填项由 cmd_run 自行校验）。"""
    for entry in _plain_entries('run'):
        if entry['opts'] == ('--pipeline',):
            continue  # run 专属路由开关，允许 required
        assert not entry['kwargs'].get('required', False), (
            f"run 的 {entry['opts']} 不应 required=True（credit/gsfc 不需要它们）"
        )


def test_run_steps_default_stays_none():
    """不变量3：run 的 --steps default 必须为 None（防 analyze 默认值泄漏吞掉
    generic 的 ...,rules 兜底与 credit/gsfc 的全步骤语义）。"""
    steps = [e for e in _plain_entries('run') if e['opts'][0] == '--steps']
    assert len(steps) == 1
    assert steps[0]['kwargs'].get('default') is None, (
        "run 的 --steps default 泄漏为非 None——analyze 默认值进了 run？"
    )
    # analyze 自己的默认值保持不变（对外 --help 语义冻结）
    a_steps = [e for e in argspec.SPECS['analyze'] if e['opts'][0] == '--steps']
    assert a_steps[0]['kwargs']['default'] == 'univariate,iv,lr'


# ---------------------------------------------------------------------------
# 不变量1：run 路径转发完整性（迭代 argspec 生成，未来 flag 自动纳入）
# ---------------------------------------------------------------------------

def _sentinel_argv_for(cmd, offset=0):
    """按 argspec 给 cmd 的每个 flag 生成哨兵值命令行与期望 dest→值 映射。"""
    argv, expected = [], {}
    for i, entry in enumerate(argspec._iter_plain(argspec.SPECS[cmd])):
        dest = argspec._dest_of(entry)
        opt, kw = entry['opts'][0], entry['kwargs']
        if kw.get('action') == 'store_true':
            argv.append(opt)
            expected[dest] = True
        elif 'choices' in kw:
            val = kw['choices'][0]
            argv += [opt, str(val)]
            expected[dest] = val
        else:
            typ = kw.get('type', str)
            val = typ(offset + i + 1) if typ in (int, float) else f'哨兵{cmd}{i}'
            argv += [opt, str(val)]
            expected[dest] = val
    return argv, expected


def _run_with_fakes(monkeypatch, extra_argv):
    """跑 cmd_run(generic)（prepare/analyze/export 全部替身），返回各替身收到的 Namespace。"""
    captured = {}

    def fake(name):
        def _f(ns):
            captured[name] = ns
            return 0
        return _f

    monkeypatch.setattr(run_mod, 'cmd_prepare', fake('prepare'))
    monkeypatch.setattr(run_mod, 'cmd_analyze', fake('analyze'))
    monkeypatch.setattr(run_mod, 'cmd_export', fake('export'))

    parser = risk_mining.cli._build_parser()
    args = parser.parse_args(['run', '--pipeline', 'generic'] + extra_argv)
    rc = run_mod.cmd_run(args)
    assert rc == 0 and set(captured) == {'prepare', 'analyze', 'export'}
    return captured


def test_every_prepare_flag_reaches_cmd_prepare_via_run(monkeypatch):
    """§9 阶段4 验证列原文：prepare 每 flag 在 run 路径真到达 cmd_prepare。"""
    argv, expected = _sentinel_argv_for('prepare')
    captured = _run_with_fakes(monkeypatch, argv)

    ns = captured['prepare']
    for dest, val in expected.items():
        assert getattr(ns, dest) == val, (
            f'prepare 的 dest={dest} 未在 run 路径到达 cmd_prepare：'
            f'期望 {val!r}，实际 {getattr(ns, dest, "<缺失>")!r}'
        )
    # 全局三件套照旧随行
    for g in ('quiet', 'verbose', 'state_dir'):
        assert hasattr(ns, g), f'转发 Namespace 缺全局 dest：{g}'


def test_every_analyze_flag_reaches_cmd_analyze_via_run(monkeypatch):
    """analyze 每 flag（含新透传的 --prepared/--features-file/--qual-dims）经 run 到达
    cmd_analyze；--steps 显式传值时逐字转发。"""
    argv, expected = _sentinel_argv_for('analyze', offset=100)
    # analyze 的 dest 与 prepare 有交集（project/target_col）——并集下同一 flag 只声明
    # 一次，故命令行里也只能出现一次：从 prepare 侧补 run 校验必需项，去重跳过交集。
    prep_argv, prep_expected = _sentinel_argv_for('prepare')
    seen = set(argv[::2])
    for opt, val in zip(prep_argv[::2], prep_argv[1::2]):
        if opt not in seen and opt in ('--wide', '--id-col'):
            argv += [opt, val]
    captured = _run_with_fakes(monkeypatch, argv)

    ns = captured['analyze']
    for dest, val in expected.items():
        assert getattr(ns, dest) == val, (
            f'analyze 的 dest={dest} 未在 run 路径到达 cmd_analyze：'
            f'期望 {val!r}，实际 {getattr(ns, dest, "<缺失>")!r}'
        )


def test_run_steps_fallback_includes_rules(monkeypatch):
    """--steps 缺省时 generic 路径兜底 'univariate,iv,lr,rules'（run 专属默认，
    保证 visualize 出树图/规则散点的中间产物就位）。"""
    argv = ['--project', 'p', '--wide', 'w.csv', '--id-col', 'id', '--target-col', 'y']
    captured = _run_with_fakes(monkeypatch, argv)
    assert captured['analyze'].steps == 'univariate,iv,lr,rules'
    # export 未在 run 声明的 dest 补 None（与旧手抄行为一致）
    assert captured['export'].project == 'p'
    assert captured['export'].intermediate_dir is None
    assert captured['export'].output_subdir is None
