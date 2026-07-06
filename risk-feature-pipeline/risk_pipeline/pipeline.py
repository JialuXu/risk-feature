# -*- coding: utf-8 -*-
"""
风险特征分析一键执行入口

支持两条链路：
  - 征信链路 (credit)：征信数据 → 分群分析 → IV/LR → 导出
  - 工商财务链路 (gsfc)：工商+财务数据 → 特征工程 → 分群分析 → IV/LR → 导出

使用方法：
---------
# 方式1：Python API
>>> from risk_pipeline.pipeline import run_credit_pipeline, run_gsfc_pipeline
>>> results = run_credit_pipeline()
>>> results = run_gsfc_pipeline()

# 方式2：命令行
$ cd risk-feature-pipeline && python -m risk_pipeline run --pipeline credit
$ cd risk-feature-pipeline && python -m risk_pipeline run --pipeline gsfc
$ cd risk-feature-pipeline && python -m risk_pipeline run --pipeline gsfc --steps data_prep,feature_eng,univariate
"""

import sys
import importlib
import argparse
from pathlib import Path
import pandas as pd

# 确保 risk-feature-pipeline/ 在 sys.path 中
_MY_SKILLS_ROOT = str(Path(__file__).resolve().parent.parent)
if _MY_SKILLS_ROOT not in sys.path:
    sys.path.insert(0, _MY_SKILLS_ROOT)

from risk_pipeline.config import COL_TARGET
from risk_mining.export import assemble_exports

# 征信/工商财务黑盒链路已抽取为独立 skill ``risk_legacy_chains``（解耦收尾）。
# 逐字转发以保号：``from risk_pipeline.pipeline import run_credit_pipeline`` 等旧路径不变。
from risk_legacy_chains.scripts import (  # noqa: E402,F401
    run_credit_pipeline,
    run_gsfc_pipeline,
)


def _load_module(skill_name, module_name):
    """从指定 Skill 以**限定名**导入模块（`risk_X.scripts.Y`）。

    历史上这里用 sys.path/sys.modules 全局突变（清空 `scripts.*` 缓存 + 改写
    sys.path，把目标 Skill 目录顶到最前）来让 6 个同名 `scripts` 包不互相冲突。
    现在每个 scripts/ 都是带 __init__.py 的真包，限定导入天然唯一，无需任何
    全局状态突变——也就消除了重入/并发下「当前激活 Skill」串味的隐患。

    例: _load_module('risk_data_prep', 'data_prep')
        等价于: import risk_data_prep.scripts.data_prep
    """
    return importlib.import_module(f'{skill_name}.scripts.{module_name}')


def _banner(step_num, title):
    print(f"\n{'=' * 60}")
    print(f"Step {step_num}: {title}")
    print('=' * 60)


# =========================================================================
# 通用宽表链路 (Pipeline C)
# =========================================================================

def run_generic_pipeline(
    df,                          # 已准备好的宽表 DataFrame
    feature_cols,                # 要分析的特征列名列表
    target_col='is_bad',         # 目标变量列名（允许自定义）
    project_name='风险特征分析', # 输出文件前缀
    output_subdir=None,          # data/results/ 下的子目录，默认用 project_name
    raw_features=None,           # 原始特征列表（用于原始vs衍生对比，可为None）
    derived_features=None,       # 衍生特征列表（可为None）
    category_dims=None,          # 类别型维度（None=自动检测）
    qual_dims=None,              # 资质标签维度（None=自动检测）
    steps=None,
    verbose=True,
):
    """
    执行通用宽表风险特征分析全流程
    """
    import pandas as pd

    mod_iv_diag = _load_module('risk_iv_diagnosis', 'iv_group_diagnosis')
    mod_iv_calc = _load_module('risk_iv_diagnosis', 'iv_analysis')
    mod_report = _load_module('risk_export_report', 'report_analysis')
    mod_io = _load_module('risk_export_report', 'io_utils')

    if steps is None:
        steps = ['univariate', 'iv', 'lr', 'export']

    results = {}
    results['wide_table'] = df
    results['feature_cols'] = feature_cols
    results['raw_features'] = raw_features or []
    results['derived_features'] = derived_features or []
    results['project_name'] = project_name

    if output_subdir is None:
        output_subdir = project_name
    results['output_subdir'] = output_subdir

    if category_dims is None or qual_dims is None:
        det_cat, det_qual = mod_iv_diag.detect_dims(df, category_dims=category_dims)
        if category_dims is None:
            category_dims = det_cat
        if qual_dims is None:
            qual_dims = det_qual

    results['category_dims'] = category_dims
    results['qual_dims'] = qual_dims

    if verbose:
        _banner(1, f'通用宽表初始化 ({project_name})')
        print(f"  宽表: {df.shape[0]} 行 x {df.shape[1]} 列")
        print(f"  目标变量: {target_col} (坏客户数: {df[target_col].sum()})")
        print(f"  特征: {len(feature_cols)} 个")
        print(f"  类别维度: {category_dims}")
        print(f"  资质标签: {len(qual_dims)} 个")

    # Step 2: 单变量分析
    if 'univariate' in steps:
        if verbose:
            _banner(2, '单变量风险分析')

        corr_results, diff_results, meta_results = {}, {}, {}
        for dim in category_dims:
            corr_df, diff_df, pval_df, meta_df, skipped = mod_iv_diag.univariate_by_group(
                df, dim, feature_cols, target=target_col
            )
            corr_results[dim] = corr_df
            diff_results[dim] = diff_df
            meta_results[dim] = meta_df

        if qual_dims:
            corr_q, pval_q, meta_q, skipped_q = mod_iv_diag.univariate_by_qualification(
                df, qual_dims, feature_cols, target=target_col
            )
            corr_results['资质标签'] = corr_q
            meta_results['资质标签'] = meta_q

        results['corr_results'] = corr_results
        results['diff_results'] = diff_results
        results['meta_results'] = meta_results

    # Step 4: IV 分析
    if 'iv' in steps:
        if verbose:
            _banner(4, 'IV 分析与可信度诊断')

        iv_full_df = mod_iv_calc.run_iv_analysis(df, feature_cols, target=target_col)
        results['iv_full'] = iv_full_df

        iv_group_all = []
        for dim in category_dims:
            iv_df, skipped = mod_iv_diag.iv_by_group(df, dim, feature_cols, target=target_col)
            if iv_df is not None:
                iv_group_all.append(iv_df)

        if qual_dims:
            iv_q, skipped_q = mod_iv_diag.iv_by_qualification(df, qual_dims, feature_cols, target=target_col)
            if iv_q is not None:
                iv_group_all.append(iv_q)

        if iv_group_all:
            iv_group_all = pd.concat(iv_group_all, ignore_index=True)
            results['iv_group_all'] = iv_group_all

            rel_summary, rel_dist, rel_warnings = mod_iv_diag.reliability_diagnosis(iv_group_all)
            results['reliability_summary'] = rel_summary
            results['reliability_dist'] = rel_dist
            results['reliability_warnings'] = rel_warnings

    # Step 5: 逻辑回归
    if 'lr' in steps:
        if verbose:
            _banner(5, '逻辑回归分析')

        lr_coef_results, lr_auc_results = {}, {}
        for dim in category_dims:
            coef_df, auc_df, skipped = mod_iv_diag.lr_by_group(df, dim, feature_cols, target=target_col)
            lr_coef_results[dim] = coef_df
            lr_auc_results[dim] = auc_df

        if qual_dims:
            coef_q, auc_q, skipped_q = mod_iv_diag.lr_by_qualification(
                df, qual_dims, feature_cols, target=target_col
            )
            lr_coef_results['资质标签'] = coef_q
            lr_auc_results['资质标签'] = auc_q

        if results['raw_features'] and results['derived_features']:
            comp_all = []
            for dim in category_dims:
                comp = mod_iv_diag.compare_feature_sets(df, dim, results['raw_features'], results['derived_features'], target=target_col)
                if comp is not None:
                    comp_all.append(comp)
            if comp_all:
                results['feature_set_comparison'] = pd.concat(comp_all, ignore_index=True)

        results['lr_coef_results'] = lr_coef_results
        results['lr_auc_results'] = lr_auc_results

    # Step 6: 导出
    if 'export' in steps:
        if verbose:
            _banner(6, '结果导出')

        project_root = mod_io.get_project_root()
        # 装配 4 张导出表（唯一实现 risk_mining.export.assemble_exports）；
        # generic 传入原始/衍生特征与自定义 target_col。
        assemble_exports(
            results,
            df=df,
            feature_cols=feature_cols,
            category_dims=category_dims,
            qual_dims=qual_dims,
            raw_features=results.get('raw_features', []),
            derived_features=results.get('derived_features', []),
            target_col=target_col,
        )

        exported = mod_report.export_results(
            project_root, results,
            project_name=project_name,
            output_subdir=output_subdir,
            results_base='data/results',   # generic 链路不加业务类型子目录
            output_base='output',
        )
        results['exported_files'] = exported

        if verbose:
            print(f"\n  共导出 {len(exported)} 个文件")

    # 构建长格式 DataFrame，方便 agent 代码直接按列名过滤
    _build_long_format(results)

    if verbose:
        print(f"\n{'=' * 60}")
        print('通用宽表链路分析完成')
        print('=' * 60)

    return results


def _build_long_format(results):
    """将宽矩阵格式的分析结果转成长格式 DataFrame，追加到 results 中。

    新增键：
      corr_long    列: 分群维度, 分群名称, 特征, 相关系数, |相关系数|
      diff_long    列: 分群维度, 分群名称, 特征, 均值差
      lr_coef_long 列: 分群维度, 分群名称, 特征, 系数, |系数|
      lr_auc_long  列: 分群维度, 分群名称, AUC, AUC类型, 样本数, 坏客户数
    """
    # corr_long
    corr_rows = []
    for dim, wide in (results.get('corr_results') or {}).items():
        if wide is None or wide.empty:
            continue
        for seg in wide.index:
            for feat in wide.columns:
                val = wide.at[seg, feat]
                if pd.notna(val):
                    corr_rows.append({'分群维度': dim, '分群名称': seg, '特征': feat,
                                      '相关系数': val, '|相关系数|': abs(val)})
    results['corr_long'] = pd.DataFrame(corr_rows)

    # diff_long
    diff_rows = []
    for dim, wide in (results.get('diff_results') or {}).items():
        if wide is None or wide.empty:
            continue
        for seg in wide.index:
            for feat in wide.columns:
                val = wide.at[seg, feat]
                if pd.notna(val):
                    diff_rows.append({'分群维度': dim, '分群名称': seg, '特征': feat, '均值差': val})
    results['diff_long'] = pd.DataFrame(diff_rows)

    # lr_coef_long
    coef_rows = []
    for dim, wide in (results.get('lr_coef_results') or {}).items():
        if wide is None or wide.empty:
            continue
        for seg in wide.index:
            for feat in wide.columns:
                val = wide.at[seg, feat]
                if pd.notna(val):
                    coef_rows.append({'分群维度': dim, '分群名称': seg, '特征': feat,
                                      '系数': val, '|系数|': abs(val)})
    results['lr_coef_long'] = pd.DataFrame(coef_rows)

    # lr_auc_long
    auc_rows = []
    for dim, auc_df in (results.get('lr_auc_results') or {}).items():
        if auc_df is None or auc_df.empty:
            continue
        for seg, row in auc_df.iterrows():
            entry = {'分群维度': dim, '分群名称': seg}
            entry.update(row.to_dict())
            auc_rows.append(entry)
    results['lr_auc_long'] = pd.DataFrame(auc_rows)


# =========================================================================
# CLI 入口
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
        import pandas as pd
        if not args.input:
            parser.error("generic 模式需要 --input 指定宽表CSV路径")
        df = pd.read_csv(args.input, encoding='utf-8-sig')

        # 解析合并主键：优先 --id-col，其次 ColumnMapper().customer_id
        if args.id_col:
            join_key = args.id_col
        else:
            from risk_pipeline.column_mapper import ColumnMapper
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
