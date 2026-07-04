# -*- coding: utf-8 -*-
"""query 子命令：只读已有结果，top-N / 分群查询（不改 level，无副作用）。"""
from __future__ import annotations

import pandas as pd

from ._common import _err


def cmd_query(args) -> int:
    from risk_result_query.scripts.results_loader import load_results, top_features

    project = args.project
    try:
        r = load_results(project)
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
