# -*- coding: utf-8 -*-
"""兼容 shim：三条链路的 Python API 已分别迁出，本模块逐字再导出旧路径。

  run_generic_pipeline / _build_long_format → risk_mining.pipeline（挖掘内核）
  run_credit_pipeline / run_gsfc_pipeline   → risk_legacy_chains.scripts（黑盒老链路）

另保留旧 ``python -m shared`` 的 argparse 入口 ``main()``（新入口：``python -m risk_pipeline run``）。
新代码请直接 import 上面的目标模块。
"""
import argparse

import pandas as pd

from risk_legacy_chains.scripts import (  # noqa: F401  再导出
    run_credit_pipeline,
    run_gsfc_pipeline,
)
from risk_mining.pipeline import (  # noqa: F401  再导出
    _banner,
    _build_long_format,
    run_generic_pipeline,
)


# =========================================================================
# 旧 CLI 入口（``python -m shared`` 转发至此；新入口是 ``python -m risk_pipeline run``）
# =========================================================================

VALID_STEPS_CREDIT = ['data_prep', 'feature_engineering', 'univariate', 'iv', 'lr', 'export']
VALID_STEPS_GSFC = ['data_prep', 'feature_eng', 'univariate', 'iv', 'lr', 'export']
VALID_STEPS_GENERIC = ['univariate', 'iv', 'lr', 'export']

def main():
    parser = argparse.ArgumentParser(
        description='风险特征分析流水线',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m shared.pipeline -p credit
  python -m shared.pipeline -p gsfc
  python -m shared.pipeline -p gsfc -s data_prep,feature_eng,univariate
  python -m shared.pipeline -p credit -s data_prep,iv
  python -m shared.pipeline -p generic --input data.csv --target is_bad --project-name 舆情特征分析

征信链路可选步骤: data_prep, feature_engineering, univariate, iv, lr, export
工商财务链路可选步骤: data_prep, feature_eng, univariate, iv, lr, export
通用宽表可选步骤: univariate, iv, lr, export
        """,
    )
    parser.add_argument(
        '--pipeline', '-p',
        choices=['credit', 'gsfc', 'generic'],
        required=True,
        help='选择链路: credit(征信) 或 gsfc(工商财务) 或 generic(通用宽表)',
    )
    parser.add_argument('--input', '-i', default=None, help='宽表CSV路径（generic模式必填）')
    parser.add_argument('--target', default='is_bad', help='目标变量列名（默认 is_bad）')
    parser.add_argument('--project-name', default='风险特征分析', help='输出文件前缀')
    parser.add_argument('--feature-cols', default=None, help='特征列名（逗号分隔），默认自动检测')
    parser.add_argument('--merge-target', default=None, help='如果宽表中没有目标变量，可以指定包含目标变量的CSV路径，将自动与宽表按主键左连接')
    parser.add_argument('--id-col', default=None, help='合并主键列名；缺省时按 ColumnMapper().customer_id 解析（默认 客户编号）')
    
    parser.add_argument(
        '--steps', '-s',
        default=None,
        help='要执行的步骤（逗号分隔），默认全部执行',
    )
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='静默模式',
    )

    args = parser.parse_args()
    steps = args.steps.split(',') if args.steps else None

    # 校验步骤名称
    if steps:
        if args.pipeline == 'credit':
            valid = VALID_STEPS_CREDIT
        elif args.pipeline == 'gsfc':
            valid = VALID_STEPS_GSFC
        else:
            valid = VALID_STEPS_GENERIC
        invalid = [s for s in steps if s not in valid]
        if invalid:
            parser.error(f"无效步骤: {invalid}。可选: {valid}")

    if args.pipeline == 'credit':
        run_credit_pipeline(steps=steps, verbose=not args.quiet)
    elif args.pipeline == 'gsfc':
        run_gsfc_pipeline(steps=steps, verbose=not args.quiet)
    elif args.pipeline == 'generic':
        if not args.input:
            parser.error("generic 模式需要 --input 指定宽表CSV路径")
        df = pd.read_csv(args.input, encoding='utf-8-sig')

        # 解析合并主键：优先 --id-col，其次 ColumnMapper().customer_id
        if args.id_col:
            join_key = args.id_col
        else:
            from risk_core.column_mapper import ColumnMapper
            join_key = ColumnMapper().customer_id

        # 合并目标变量（如果需要）
        if args.merge_target:
            df_target = pd.read_csv(args.merge_target, encoding='utf-8-sig')
            if join_key in df.columns and join_key in df_target.columns:
                # 场景 1: df_target 中有 target_col (例如 is_bad)，直接 join 并填充 0
                if args.target in df_target.columns:
                    df = df.merge(df_target[[join_key, args.target]], on=join_key, how='left')
                    df[args.target] = df[args.target].fillna(0).astype(int)
                    if not args.quiet:
                        print(f"[INFO] 成功从 {args.merge_target} 合并目标变量 {args.target}。")
                # 场景 2: df_target 是一个坏客户清单，没有 target_col
                else:
                    # 将 df_target 中的客户视为坏客户 (1)，不在里面的视为好客户 (0)
                    bad_customers = set(df_target[join_key].astype(str).str.strip())
                    df[args.target] = df[join_key].astype(str).str.strip().isin(bad_customers).astype(int)
                    if not args.quiet:
                        print(f"[INFO] 成功从 {args.merge_target} (坏客户清单) 匹配出 {df[args.target].sum()} 个坏客户。")
            else:
                parser.error(f"宽表或目标文件中未找到合并主键 '{join_key}'，无法自动合并。可用 --id-col 指定。")

        if args.target not in df.columns:
            parser.error(f"宽表中不存在目标列 '{args.target}'。如果目标变量在另一文件中，请使用 --merge-target 指定包含目标变量的CSV文件。")

        if args.feature_cols:
            feature_cols = args.feature_cols.split(',')
        else:
            # 自动过滤零方差特征，数值型，非主键非target
            exclude_cols = {join_key, args.target}
            feature_cols = [
                c for c in df.select_dtypes(include='number').columns
                if c not in exclude_cols and df[c].std() > 0
            ]
            
        run_generic_pipeline(
            df=df,
            feature_cols=feature_cols,
            target_col=args.target,
            project_name=args.project_name,
            output_subdir=args.project_name,
            steps=steps,
            verbose=not args.quiet,
        )


if __name__ == '__main__':
    main()
