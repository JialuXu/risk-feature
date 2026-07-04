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
from pathlib import Path

# 把 risk-feature-pipeline/ 加入 sys.path，便于 CLI 内部 fully-qualified import
# 子 skill（risk_data_prep / risk_export_report / ...）。
_MY_SKILLS_ROOT = str(Path(__file__).resolve().parent.parent)
if _MY_SKILLS_ROOT not in sys.path:
    sys.path.insert(0, _MY_SKILLS_ROOT)


def _make_global_parent() -> argparse.ArgumentParser:
    """返回一个含全局 flag 的 parent parser，让每个子命令都接受这些 flag。"""
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument('--state-dir', default=None, help='自定义 state.json 目录（默认随 project）')
    p.add_argument('-q', '--quiet', action='store_true', help='静默')
    p.add_argument('--verbose', action='store_true', help='打印底层 pipeline 详细日志')
    return p


def _build_parser() -> argparse.ArgumentParser:
    global_parent = _make_global_parent()

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

    # ----- prepare -----
    p = sub.add_parser('prepare', parents=[global_parent],
                        help='构建 prepared.csv + features.json（前置态）')
    p.add_argument('--wide', required=True, help='宽表 CSV 路径')
    p.add_argument('--bad-customer', default=None, help='坏客户清单 CSV（宽表已有 target 时可省略）')
    p.add_argument('--merge-table', default=None,
                   help='可选：在主键上 left-join 的补充表 CSV（如分群维度在另一张表，'
                        '如客户信息.csv）。免去手抄 pandas merge')
    p.add_argument('--merge-id-col', default=None,
                   help='补充表主键列名（默认与 --id-col 同）')
    p.add_argument('--merge-cols', default=None,
                   help='只从补充表带入这些列（逗号分隔；缺省=带入全部非主键列）')
    p.add_argument('--id-col', required=True, help='主键列名（无默认，必填）')
    p.add_argument('--target-col', required=True, help='目标列名（无默认，必填）')
    p.add_argument('--bad-id-col', default=None, help='坏客户清单主键列名（默认与 --id-col 同）')
    p.add_argument('--filter-file', default=None,
                   help='filter 规则 JSON。规则键: exclude/include(类别) | min/max/range(数值) | drop_na(布尔)。'
                        '示例: {"企业规模": {"exclude": ["0"]}, "非银机构占比": {"range": [0, 1]}, '
                        '"资产负债率": {"max": 1.0, "drop_na": true}}')
    p.add_argument('--exclude-features-file', default=None,
                   help='不参与分析的特征 JSON 数组')
    p.add_argument('--project', '--project-name', dest='project', required=True,
                   help='项目名（用作输出目录前缀）')
    p.add_argument('--confirmed-new-dataset', action='store_true',
                   help='[阻断节点 1] 首次使用新数据集时必传（一键确认）')
    # C15：拆分版确认 flag——三项全填 + 与 --id-col/--target-col 一致才视为确认通过
    p.add_argument('--confirmed-id-col', default=None,
                   help='[阻断节点 1 / 拆分版] 显式声明确认的主键列名（须与 --id-col 一致）')
    p.add_argument('--confirmed-target-col', default=None,
                   help='[阻断节点 1 / 拆分版] 显式声明确认的目标列名（须与 --target-col 一致）')
    p.add_argument('--confirmed-target-positive', default=None,
                   help='[阻断节点 1 / 拆分版] 显式声明坏客户标记的取值（如 "1"），写入 audit')
    p.add_argument('--skip-preflight', action='store_true',
                   help='跳过 column_mapping.yaml 与宽表的字段映射预检（仅当你确认只跑全样本、'
                        '不需要分群分析时使用；否则建议先编辑 config/column_mapping.yaml）')

    # ----- analyze -----
    p = sub.add_parser('analyze', parents=[global_parent],
                        help='跑 univariate/iv/lr 子集（过渡态）')
    p.add_argument('--project', required=True)
    p.add_argument('--prepared', default=None, help='默认 data/processed/{project}/prepared.csv')
    p.add_argument('--features-file', default=None, help='默认 data/processed/{project}/features.json')
    p.add_argument('--steps', default='univariate,iv,lr',
                   help='子集，逗号分隔；可选: univariate,iv,lr,rules；'
                        'CLI 强制按 univariate→iv→lr→rules 顺序。'
                        '加 rules 会跑决策树规则挖掘并把树持久化到 _intermediate/，'
                        '供 visualize 出真树图 / 规则散点 / 指标组合 / 共现网络')
    p.add_argument('--category-dims', default=None,
                   help='类别维度列名（逗号分隔），默认自动检测')
    p.add_argument('--qual-dims', default=None,
                   help='资质标签列名（逗号分隔；空字符串=不用），默认自动检测')
    p.add_argument('--target-col', default=None, help='默认从 features.json 读取')

    # ----- export -----
    p = sub.add_parser('export', parents=[global_parent],
                        help='_intermediate/ → 8 张 CSV + LLM JSON（→ Level 1）')
    p.add_argument('--project', required=True)
    p.add_argument('--intermediate-dir', default=None,
                   help='默认 data/processed/{project}/_intermediate/')
    p.add_argument('--output-subdir', default=None,
                   help='data/results/ 下的子目录名，默认 {project}')

    # ----- query -----
    p = sub.add_parser('query', parents=[global_parent],
                        help='只读已有结果，top-N / 分群查询')
    p.add_argument('--project', required=True)
    p.add_argument('--kind', choices=['iv', 'iv_group', 'corr', 'lr'], required=True)
    p.add_argument('--dim', default=None, help='分群维度（如 企业规模）')
    p.add_argument('--group', default=None, help='分群名称（如 小型企业）')
    p.add_argument('--top', '-n', type=int, default=15, help='取前 N 条（默认 15）')
    p.add_argument('--sign', choices=['positive', 'negative'], default=None,
                   help='仅 kind=lr 生效')
    p.add_argument('--output-format', choices=['table', 'csv', 'json'], default='table')

    # ----- trigger -----
    p = sub.add_parser('trigger', parents=[global_parent],
                        help='客户级触碰提取（→ Level 2）')
    p.add_argument('--project', required=True)
    p.add_argument('--prepared', default=None)
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument('--use-default-features', action='store_true',
                     help='使用 RISK_FEATURES 默认特征配置')
    grp.add_argument('--features-file', default=None, help='项目专属特征列表 JSON')
    p.add_argument('--id-col', default=None, help='默认从 features.json 读取')
    p.add_argument('--target-col', default=None, help='默认从 features.json 读取')
    p.add_argument('--keep-metadata-cols', default=None,
                   help='宽表 CSV 中要保留的元信息列（逗号分隔），如 "企业规模,所属行业"。'
                        '默认全部剔除以避免与 prepared.csv merge 撞列冲突')
    p.add_argument('--confirmed', action='store_true',
                   help='[阻断节点 2] 必传：确认 features 配置正确')

    # ----- report -----
    p = sub.add_parser('report', parents=[global_parent],
                        help='LLM JSON → docx（→ Level 3）')
    p.add_argument('--project', required=True)
    p.add_argument('--llm-json', default=None,
                   help='默认 output/{project}/{project}_LLM报告数据.json')
    p.add_argument('--report-markdown', required=True, help='LLM 生成的 Markdown 报告')
    p.add_argument('--output', default=None, help='默认 output/{project}/{project}.docx')
    p.add_argument('--purpose', choices=['internal', 'external'], required=True,
                   help='[阻断节点 3] internal=内部审阅 / external=对外交付')
    p.add_argument('--appendix-mode', default=None,
                   choices=['both', 'feature', 'segment', 'none', 'compact'],
                   help='附录模式（默认 both）')
    p.add_argument('--confirmed-final-version', action='store_true',
                   help='[阻断节点 3] purpose=external 时必传')

    # ----- visualize -----
    p = sub.add_parser('visualize', parents=[global_parent],
                        help='生成 IV/相关性/LR/分群/规则/组合可视化（→ output/<project>/charts/）')
    p.add_argument('--project', required=True)
    p.add_argument('--kinds', default=None,
                   help='逗号分隔: iv,iv_heatmap,corr_heatmap,lr_heatmap,'
                        'auc,segment,rules,combos,thresholds（默认全部）')
    p.add_argument('--dim', default=None,
                   help='限定单一分群维度，如 企业规模（对 corr_heatmap/lr_heatmap/auc 生效）')
    p.add_argument('--top', type=int, default=15, help='top-N 条形图截断（默认 15）')
    p.add_argument('--out-dir', default=None,
                   help='输出目录，默认 output/<project>/charts/')
    p.add_argument('--dpi', type=int, default=300)

    # ----- explore_thresholds -----
    p = sub.add_parser('explore_thresholds', parents=[global_parent],
                        help='候选规则阈值探索（optbinning 最优切点 + 业务级有效性判定）')
    p.add_argument('--project', required=True)
    p.add_argument('--prepared', default=None, help='默认 data/processed/{project}/prepared.csv')
    p.add_argument('--pairs-file', required=True,
                   help='pair-list 文件（.csv 或 .json）：列 分群维度,分群名称,特征')
    p.add_argument('--target-col', default=None, help='默认从 features.json 读取')
    p.add_argument('--results-subdir', default=None,
                   help='结果子目录名，默认与 --project 同；产物落在 data/results/<subdir>/')
    p.add_argument('--min-risk-ratio', type=float, default=None,
                   help='风险倍数下限（默认 2.0）')
    p.add_argument('--max-p', type=float, default=None,
                   help='卡方 p 值上限（默认 0.05）')
    p.add_argument('--min-bad-high', type=int, default=None,
                   help='高风险侧坏客户数下限（默认 10）')
    p.add_argument('--alert-rate-min', type=float, default=None,
                   help='触警率下限（默认 0.01）')
    p.add_argument('--alert-rate-max', type=float, default=None,
                   help='触警率上限（默认 0.30）')
    p.add_argument('--min-iv', type=float, default=None,
                   help='参考 IV 下限（默认 0.02 = IV_THRESHOLD.weak；优先取分群 IV，缺失回落全样本）')
    p.add_argument('--min-bin-size', type=float, default=None,
                   help='optbinning min_bin_size（默认 0.05；zero-inflated 数据可降到 0.02-0.03）')

    # ----- run -----
    p = sub.add_parser('run', parents=[global_parent],
                        help='便捷组合：generic 走 prepare→analyze→export')
    p.add_argument('--pipeline', choices=['credit', 'gsfc', 'generic'], required=True)
    p.add_argument('--project', default=None, help='generic 必填')
    p.add_argument('--wide', default=None, help='generic 必填')
    p.add_argument('--bad-customer', default=None)
    p.add_argument('--merge-table', default=None,
                   help='[generic] 同 prepare --merge-table；在主键上 left-join 的补充表 CSV')
    p.add_argument('--merge-id-col', default=None,
                   help='[generic] 同 prepare --merge-id-col')
    p.add_argument('--merge-cols', default=None,
                   help='[generic] 同 prepare --merge-cols')
    p.add_argument('--id-col', default=None, help='generic 必填')
    p.add_argument('--target-col', default=None, help='generic 必填')
    p.add_argument('--steps', default=None,
                   help='credit/gsfc 步骤透传；generic 透传给 analyze')
    p.add_argument('--category-dims', default=None,
                   help='[generic] 类别维度列名（逗号分隔），默认自动检测；透传给 analyze。'
                        'credit/gsfc 用预置维度，传了会被忽略并告警')
    p.add_argument('--confirmed-new-dataset', action='store_true',
                   help='[阻断节点 1] 首次使用新数据集时必传')
    # generic 路径透传给 cmd_prepare 的参数（原 cmd_run 硬编码 None 导致这些功能不可用）
    p.add_argument('--bad-id-col', default=None,
                   help='[generic] 同 prepare --bad-id-col；坏客户清单主键列名')
    p.add_argument('--filter-file', default=None,
                   help='[generic] 同 prepare --filter-file；filter 规则 JSON')
    p.add_argument('--exclude-features-file', default=None,
                   help='[generic] 同 prepare --exclude-features-file；'
                        '不参与分析的特征 JSON 数组')
    p.add_argument('--confirmed-id-col', default=None,
                   help='[generic / 阻断节点 1 拆分版] 同 prepare --confirmed-id-col')
    p.add_argument('--confirmed-target-col', default=None,
                   help='[generic / 阻断节点 1 拆分版] 同 prepare --confirmed-target-col')
    p.add_argument('--confirmed-target-positive', default=None,
                   help='[generic / 阻断节点 1 拆分版] 同 prepare --confirmed-target-positive')
    p.add_argument('--skip-preflight', action='store_true',
                   help='[generic] 同 prepare --skip-preflight；透传给 prepare 阶段')

    return parser


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, 'quiet', False):
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
