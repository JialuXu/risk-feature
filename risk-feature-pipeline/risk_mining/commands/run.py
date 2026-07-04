# -*- coding: utf-8 -*-
"""run 子命令：便捷组合。generic 走 prepare→analyze→export；credit/gsfc 转发现有黑盒链路。"""
from __future__ import annotations

import argparse as _argparse
import os
import sys
import time

from risk_pipeline.pipeline_state import load_state

from ._common import _err, _is_quiet, _is_verbose, _output_root, _state_dir
from .analyze import cmd_analyze
from .export import cmd_export
from .prepare import cmd_prepare


def cmd_run(args) -> int:
    # --category-dims 仅 generic 链路生效；credit/gsfc 用预置维度，传了告警忽略
    if getattr(args, 'category_dims', None) and args.pipeline != 'generic':
        print(
            f'⚠️ [run] --category-dims 仅对 --pipeline generic 生效；'
            f'当前 pipeline={args.pipeline} 使用预置分群维度，本参数将被忽略。',
            file=sys.stderr,
        )

    if args.pipeline == 'credit':
        from risk_pipeline.pipeline import run_credit_pipeline
        steps = [s.strip() for s in args.steps.split(',')] if args.steps else None
        started = time.time()
        run_credit_pipeline(steps=steps, verbose=_is_verbose(args) and not _is_quiet(args))
        # credit 用 'credit' 作为 project，state 写入 data/results/征信/credit/
        project = args.project or 'credit'
        state_dir = _state_dir(args) or os.path.join(
            _output_root(), 'data', 'results', '征信', project,
        )
        state = load_state(project, state_dir=state_dir)
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
        from risk_pipeline.pipeline import run_gsfc_pipeline
        steps = [s.strip() for s in args.steps.split(',')] if args.steps else None
        started = time.time()
        run_gsfc_pipeline(steps=steps, verbose=_is_verbose(args) and not _is_quiet(args))
        project = args.project or 'gsfc'
        state_dir = _state_dir(args) or os.path.join(
            _output_root(), 'data', 'results', '工商财务', project,
        )
        state = load_state(project, state_dir=state_dir)
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

    rc = cmd_prepare(_argparse.Namespace(
        wide=args.wide, bad_customer=args.bad_customer,
        id_col=args.id_col, target_col=args.target_col,
        bad_id_col=getattr(args, 'bad_id_col', None),
        merge_table=getattr(args, 'merge_table', None),
        merge_id_col=getattr(args, 'merge_id_col', None),
        merge_cols=getattr(args, 'merge_cols', None),
        filter_file=getattr(args, 'filter_file', None),
        exclude_features_file=getattr(args, 'exclude_features_file', None),
        project=args.project,
        confirmed_new_dataset=getattr(args, 'confirmed_new_dataset', False),
        # C15 拆分确认 flag：原 cmd_run 漏传导致 run 路径仅支持一键确认
        confirmed_id_col=getattr(args, 'confirmed_id_col', None),
        confirmed_target_col=getattr(args, 'confirmed_target_col', None),
        confirmed_target_positive=getattr(args, 'confirmed_target_positive', None),
        skip_preflight=getattr(args, 'skip_preflight', False),
        quiet=_is_quiet(args), verbose=_is_verbose(args),
        state_dir=_state_dir(args),
    ))
    if rc:
        return rc

    rc = cmd_analyze(_argparse.Namespace(
        project=args.project, prepared=None, features_file=None,
        # 默认含 rules，让 visualize 立即能出决策树/规则散点/共现网络
        steps=args.steps or 'univariate,iv,lr,rules',
        category_dims=getattr(args, 'category_dims', None),
        qual_dims=None, target_col=None,
        quiet=_is_quiet(args), verbose=_is_verbose(args),
        state_dir=_state_dir(args),
    ))
    if rc:
        return rc

    rc = cmd_export(_argparse.Namespace(
        project=args.project, intermediate_dir=None, output_subdir=None,
        quiet=_is_quiet(args), verbose=_is_verbose(args),
        state_dir=_state_dir(args),
    ))
    if rc:
        return rc

    if not _is_quiet(args):
        print(f'[run] OK | pipeline=generic | project={args.project} | level=Level 1')
    return 0
