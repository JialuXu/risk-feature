# -*- coding: utf-8 -*-
"""risk_mining 统一 CLI 入口（组合根路由层）。

对 agent 暴露的入口仍是 `python -m risk_pipeline <subcommand>`（转发至此）。

使用方式：
  python -m risk_pipeline <subcommand> [args]

子命令：
  prepare            构建 prepared.csv + features.json（前置态）
  analyze            跑 univariate/iv/lr/rules 子集 → _intermediate/（过渡态）
  export             重建结果 → 8 张 CSV + LLM JSON（→ Level 1）
  query              只读已有结果，top-N / 分群查询（不改 level）
  trigger            客户级触碰提取 → 三张表（→ Level 2）
  report             LLM JSON → docx（→ Level 3）
  visualize          生成 IV/相关性/LR/分群/规则/组合可视化 PNG（Level 1 后）
  explore_thresholds 候选规则阈值探索：optbinning 单变量最优切点 + 业务级判定（Level 1 后；不改 level）
  run                便捷组合：generic 走 prepare→analyze→export；credit/gsfc 转发现有链路
"""
from __future__ import annotations

import argparse
import sys


def _make_global_parent(for_subcommand: bool = False) -> argparse.ArgumentParser:
    """返回一个含全局 flag 的 parent parser，让顶层与每个子命令都接受这些 flag。

    for_subcommand=True 时各 flag 的 default 为 SUPPRESS：子命令里没写的 flag 不产生
    默认值，从而不会覆盖写在子命令**之前**的同名 flag（argparse 子解析器默认值
    会覆盖父解析器已解析值——曾导致 ``-q prepare ...`` 里的 -q 被静默丢弃）。
    """
    d = {'default': argparse.SUPPRESS} if for_subcommand else {}
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument('--state-dir', help='自定义 state.json 目录（默认随 project）', **d)
    p.add_argument('-q', '--quiet', action='store_true', help='静默', **d)
    p.add_argument('--verbose', action='store_true', help='打印底层 pipeline 详细日志', **d)
    return p


def _build_parser() -> argparse.ArgumentParser:
    global_parent = _make_global_parent()
    sub_global_parent = _make_global_parent(for_subcommand=True)

    parser = argparse.ArgumentParser(
        prog='python -m risk_pipeline',
        description='风险特征分析统一 CLI（9 子命令）',
        parents=[global_parent],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
典型用法：
  prepare:  python -m risk_pipeline prepare --wide data/raw/x.csv \\
              --bad-customer data/raw/bad.csv --id-col 客户编号 \\
              --target-col is_bad --project xxx
  analyze:  python -m risk_pipeline analyze --project xxx \\
              --steps univariate,iv,lr --category-dims 企业规模
  analyze 含规则挖掘（供 visualize 出决策树/组合图）：
            python -m risk_pipeline analyze --project xxx \\
              --steps univariate,iv,lr,rules --category-dims 企业规模
  export:   python -m risk_pipeline export --project xxx
  query:    python -m risk_pipeline query --project xxx --kind iv --top 15
  trigger:  python -m risk_pipeline trigger --project xxx --use-default-features
  report:   python -m risk_pipeline report --project xxx \\
              --report-markdown report.md --purpose internal
  visualize: python -m risk_pipeline visualize --project xxx
  explore_thresholds:
            python -m risk_pipeline explore_thresholds --project xxx \\
              --pairs-file path/to/pairs.csv
  run:      python -m risk_pipeline run --pipeline generic \\
              --wide data/raw/x.csv --id-col 客户编号 --target-col is_bad \\
              --project xxx
""",
    )
    sub = parser.add_subparsers(dest='cmd', required=True, metavar='SUBCOMMAND')

    # 9 子命令的 flag 全部来自 argspec 单一注册表（解耦重构 Stage 4）：
    # 每 flag 只在 argspec.SPECS 声明一次；run 的 flag 集由 prepare∪analyze 并集派生。
    from .argspec import SUBCOMMAND_HELP, SUBCOMMAND_ORDER, flags_for

    for name in SUBCOMMAND_ORDER:
        p = sub.add_parser(name, parents=[sub_global_parent], help=SUBCOMMAND_HELP[name])
        for entry in flags_for(name):
            if 'group' in entry:
                grp = p.add_mutually_exclusive_group(required=entry.get('required', False))
                for member in entry['group']:
                    grp.add_argument(*member['opts'], **member['kwargs'])
            else:
                p.add_argument(*entry['opts'], **entry['kwargs'])

    return parser


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.quiet:
        from risk_core.paths import get_output_root, get_project_root
        print(f'[路径] 项目根={get_project_root()}  输出根={get_output_root()}'
              f'（可用 RISK_PROJECT_ROOT / RISK_OUTPUT_ROOT 覆盖）')

    from . import commands

    func = getattr(commands, f'cmd_{args.cmd}', None)
    if func is None:
        parser.error(f'未实现的子命令: {args.cmd}')
    return func(args) or 0


if __name__ == '__main__':
    sys.exit(main())
