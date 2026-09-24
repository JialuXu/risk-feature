# -*- coding: utf-8 -*-
"""run 子命令：便捷组合。generic 走 prepare→analyze→export；credit/gsfc 转发现有黑盒链路。"""
from __future__ import annotations

import argparse as _argparse
import sys
import time

from risk_mining.pipeline_state import load_state

from ..argspec import dests_for
from ._common import _err, _is_quiet, _is_verbose, _state_dir
from .analyze import cmd_analyze
from .export import cmd_export
from .prepare import cmd_prepare


def _forward_ns(cmd: str, args, **overrides) -> _argparse.Namespace:
    """从 argspec 派生目标子命令的转发 Namespace。

    该命令在 argspec 声明的每个 dest 一律从 run 的 args 透传（run 的 flag 集就是
    prepare∪analyze 并集，故 prepare/analyze 的 dest 必在）；run 未声明的 dest
    （如 export 的 intermediate_dir/output_subdir）取 None。
    给 prepare/analyze 新增 flag 只改 argspec 一处，run 路径自动透传，
    不会因漏转发某个字段而在运行期静默得到 None。
    """
    values = {dest: getattr(args, dest, None) for dest in dests_for(cmd)}
    values.update(
        quiet=_is_quiet(args), verbose=_is_verbose(args), state_dir=_state_dir(args),
    )
    values.update(overrides)
    return _argparse.Namespace(**values)


def cmd_run(args) -> int:
    # --category-dims 仅 generic 链路生效；credit/gsfc 用预置维度，传了告警忽略
    if getattr(args, 'category_dims', None) and args.pipeline != 'generic':
        print(
            f'⚠️ [run] --category-dims 仅对 --pipeline generic 生效；'
            f'当前 pipeline={args.pipeline} 使用预置分群维度，本参数将被忽略。',
            file=sys.stderr,
        )

    if args.pipeline == 'credit':
        from risk_legacy_chains.scripts import run_credit_pipeline
        steps = [s.strip() for s in args.steps.split(',')] if args.steps else None
        started = time.time()
        run_credit_pipeline(steps=steps, verbose=_is_verbose(args) and not _is_quiet(args))
        # credit 用 'credit' 作为 project。state 目录不带「征信/」前缀：
        # 与 analyze/export/trigger 统一走 _resolve_state_dir → data/results/<project>/，
        # 否则 run credit 推进的 Level 1 对下游 require_level（trigger/report/explore）不可见。
        # 注意：结果 CSV 目录仍带「征信/」前缀（config.RESULTS_DIR_CREDIT）。
        project = args.project or 'credit'
        state = load_state(project, state_dir=_state_dir(args))
        # 只有 export 真的跑了才推进到 Level 1；steps=None 表示全跑（含 export）
        has_export = steps is None or 'export' in steps
        state.append_history({
            'cmd': 'run',
            'pipeline': 'credit',
            'args_summary': {'steps': steps},
            'duration_sec': round(time.time() - started, 2),
            'note': 'credit/gsfc 不可中段独立调用；state 黑盒一项',
        }, new_level='Level 1' if has_export else None)
        state.save()
        if not _is_quiet(args):
            print(f'[run] OK | pipeline=credit | level={state.current_level}')
        return 0

    if args.pipeline == 'gsfc':
        from risk_legacy_chains.scripts import run_gsfc_pipeline
        steps = [s.strip() for s in args.steps.split(',')] if args.steps else None
        started = time.time()
        run_gsfc_pipeline(steps=steps, verbose=_is_verbose(args) and not _is_quiet(args))
        # 同 credit：state 目录不带前缀，结果 CSV 仍带「工商财务/」前缀
        project = args.project or 'gsfc'
        state = load_state(project, state_dir=_state_dir(args))
        has_export = steps is None or 'export' in steps
        state.append_history({
            'cmd': 'run',
            'pipeline': 'gsfc',
            'args_summary': {'steps': steps},
            'duration_sec': round(time.time() - started, 2),
            'note': 'credit/gsfc 不可中段独立调用；state 黑盒一项',
        }, new_level='Level 1' if has_export else None)
        state.save()
        if not _is_quiet(args):
            print(f'[run] OK | pipeline=gsfc | level={state.current_level}')
        return 0

    # generic: prepare → analyze → export
    if not args.wide:
        _err('[run] --pipeline generic 必须提供 --wide')
    if not args.id_col or not args.target_col:
        _err('[run] --pipeline generic 必须提供 --id-col 和 --target-col')
    if not args.project:
        _err('[run] --pipeline generic 必须提供 --project')

    rc = cmd_prepare(_forward_ns('prepare', args))
    if rc:
        return rc

    # --steps 缺省时兜底含 rules，让 visualize 立即能出 rules（规则散点）/ combos（指标组合）图
    # （run 专属默认；argspec 里 run 的 --steps 覆盖为 default=None 正是为给这里让路）
    rc = cmd_analyze(_forward_ns(
        'analyze', args, steps=args.steps or 'univariate,iv,lr,rules',
    ))
    if rc:
        return rc

    rc = cmd_export(_forward_ns('export', args))
    if rc:
        return rc

    if not _is_quiet(args):
        print(f'[run] OK | pipeline=generic | project={args.project} | level=Level 1')
    return 0
