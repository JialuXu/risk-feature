# -*- coding: utf-8 -*-
"""visualize 子命令：读结果 CSV → PNG 图表（Level 1 后；不推进 level）。"""
from __future__ import annotations

import os
import time
from typing import Optional

from risk_pipeline.pipeline_state import format_status_stamp, load_state

from ._common import _err, _output_root, _print_stamp, _state_dir


def cmd_visualize(args) -> int:
    from risk_visualization.scripts.visualize import generate_charts, ALL_KINDS

    started = time.time()
    project = args.project

    kinds: Optional[list] = None
    if args.kinds:
        kinds = [k.strip() for k in args.kinds.split(',') if k.strip()]
        invalid = [k for k in kinds if k not in ALL_KINDS]
        if invalid:
            _err(f'[visualize] 无效 kinds: {invalid}；可选: {list(ALL_KINDS)}')

    try:
        result_paths = generate_charts(
            project_name=project,
            kinds=kinds,
            top_n=args.top,
            out_dir=args.out_dir,
            dim=args.dim,
            dpi=args.dpi,
            project_root=_output_root(),  # visualize 读产物 CSV + 写 charts/
        )
    except FileNotFoundError as e:
        _err(f'[visualize] {e}')
    except ValueError as e:
        _err(f'[visualize] {e}')

    # 推断输出目录用于 status stamp
    if args.out_dir:
        out_dir_display = args.out_dir
    else:
        out_dir_display = os.path.join('output', project, 'charts')

    summary = ', '.join(
        f'{k}:{len(v)}' for k, v in sorted(result_paths.items())
    ) or '(无图生成；检查结果目录是否完整)'
    skipped = sorted(set((kinds or list(ALL_KINDS))) - set(result_paths.keys()))

    state = load_state(project, state_dir=_state_dir(args))
    state.append_history({
        'cmd': 'visualize',
        'args_summary': {
            'kinds': kinds or list(ALL_KINDS),
            'dim': args.dim,
            'top': args.top,
            'dpi': args.dpi,
        },
        'outputs': [
            p for paths in result_paths.values() for p in paths
        ],
        'duration_sec': round(time.time() - started, 2),
        'level_after': state.current_level,  # visualize 不推进 level
        'note': '只读后置；不推进 level',
    })
    state.save()

    extras = [f'charts={summary}']
    if skipped:
        extras.append(f'skipped={",".join(skipped)}（缺对应 CSV/规则）')
    _print_stamp(
        format_status_stamp(
            'visualize', project, state.current_level,
            inputs=[f'data/results/{project}/'],
            outputs=[f'{out_dir_display}/'],
            extras=extras,
        ),
        args,
    )
    return 0
