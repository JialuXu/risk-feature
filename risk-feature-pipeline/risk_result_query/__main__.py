# -*- coding: utf-8 -*-
"""risk_result_query 薄独立入口（解耦重构 Stage 5，首拆样板）。

    python -m risk_result_query <project> [--kind iv] [--dim 企业规模] [--group 小型企业]
                                [--top 15] [--sign positive]

仅供人工 / 测试直跑（DECOUPLING-DESIGN §4.3）：面向 agent 的路径统一是
`python -m risk_pipeline query ...`（flag 单一真源在组合根 argspec）。本入口
自带一份最小 argparse，不参与 argspec、不写进 SKILL.md 模板——两者互不牵连。
只读、不改 level、无副作用。
"""
from __future__ import annotations

import argparse
import sys


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog='python -m risk_result_query',
        description='只读查询已导出的风险特征分析结果（独立薄入口；agent 请用 python -m risk_pipeline query）',
    )
    parser.add_argument('project', help='项目名（results 目录与文件前缀）')
    parser.add_argument('--kind', default='iv',
                        choices=['iv', 'iv_group', 'corr', 'lr'], help='查询类型')
    parser.add_argument('--dim', default=None, help='分群维度（如 企业规模）')
    parser.add_argument('--group', default=None, help='分群名称（如 小型企业）')
    parser.add_argument('--top', '-n', type=int, default=15, help='取前多少条')
    parser.add_argument('--sign', default=None, choices=['positive', 'negative'],
                        help='仅 kind=lr 生效：按系数正/负向排序')
    args = parser.parse_args(argv)

    from .scripts.results_loader import load_results, top_features

    try:
        r = load_results(args.project)
    except FileNotFoundError as e:
        print(f'[risk_result_query] {e}', file=sys.stderr)
        return 1

    df = top_features(r, kind=args.kind, dim=args.dim, group=args.group,
                      n=args.top, sign=args.sign)
    if df is None or df.empty:
        print('(无结果)')
    else:
        print(df.to_string(index=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
