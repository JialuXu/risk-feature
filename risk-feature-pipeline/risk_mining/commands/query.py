# -*- coding: utf-8 -*-
"""query 子命令：只读已有结果，top-N / 分群查询（不改 level，无副作用）。"""
from __future__ import annotations

import pandas as pd

from risk_mining.pipeline_state import last_export_subdir, peek_state

from ._common import _err, _output_root, _state_dir


def cmd_query(args) -> int:
    from risk_result_query.scripts.results_loader import load_results, top_features

    project = args.project
    # 与 export 同一位置：输出根（RISK_OUTPUT_ROOT）+ 最近一次 export 的 --output-subdir
    state = peek_state(project, state_dir=_state_dir(args)) or {}
    try:
        r = load_results(project, subdir=last_export_subdir(project, state.get('history')),
                         project_root=_output_root())
    except FileNotFoundError as e:
        _err(f'[query] {e}')

    df = top_features(
        r, kind=args.kind, dim=args.dim, group=args.group,
        n=args.top, sign=args.sign,
    )

    fmt = args.output_format
    if fmt == 'csv':
        print(df.to_csv(index=False))
    elif fmt == 'json':
        print(df.to_json(orient='records', force_ascii=False, indent=2))
    else:
        if df is None or df.empty:
            print('(无结果)')
        else:
            with pd.option_context('display.max_rows', None, 'display.max_columns', None,
                                   'display.width', 200):
                print(df.to_string(index=False))
    # query 不写 state（不改 level，无副作用）
    return 0
