# -*- coding: utf-8 -*-
"""挖掘内核·generic 链路编排：``run_generic_pipeline``（Python API 主入口）。

解耦重构（DECOUPLING-DESIGN §4.2）：原 ``risk_pipeline/pipeline.py`` 的 generic 段迁入此处。
内核依赖规则（``tests/test_unit_kernel_boundary.py`` 锁定）：
  - 只调用 ``risk_mining.analysis``（engine / iv_core）与 ``risk_core``；
  - 不以任何形式（静态 import / importlib 字符串）引用子 skill，唯一例外是导出步的
    实现 ``risk_export_report``（§4.2：「不拆，是 export 步的实现，归 risk_mining.export 调用」）。
credit / gsfc 黑盒链路在 ``risk_legacy_chains``；旧路径 ``risk_pipeline.pipeline`` 继续转发三者。

    >>> from risk_mining.pipeline import run_generic_pipeline
"""
import pandas as pd

from risk_core.paths import get_output_root

from .analysis import engine, iv_core
from .export import assemble_exports


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
        det_cat, det_qual = engine.detect_dims(df, category_dims=category_dims)
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
            corr_df, diff_df, pval_df, meta_df, skipped = engine.univariate_by_group(
                df, dim, feature_cols, target=target_col
            )
            corr_results[dim] = corr_df
            diff_results[dim] = diff_df
            meta_results[dim] = meta_df

        if qual_dims:
            corr_q, pval_q, meta_q, skipped_q = engine.univariate_by_qualification(
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

        iv_full_df = iv_core.run_iv_analysis(df, feature_cols, target=target_col)
        results['iv_full'] = iv_full_df

        iv_group_all = []
        for dim in category_dims:
            iv_df, skipped = engine.iv_by_group(df, dim, feature_cols, target=target_col)
            if iv_df is not None:
                iv_group_all.append(iv_df)

        if qual_dims:
            iv_q, skipped_q = engine.iv_by_qualification(df, qual_dims, feature_cols, target=target_col)
            if iv_q is not None:
                iv_group_all.append(iv_q)

        if iv_group_all:
            iv_group_all = pd.concat(iv_group_all, ignore_index=True)
            results['iv_group_all'] = iv_group_all

            rel_summary, rel_dist, rel_warnings = engine.reliability_diagnosis(iv_group_all)
            results['reliability_summary'] = rel_summary
            results['reliability_dist'] = rel_dist
            results['reliability_warnings'] = rel_warnings

    # Step 5: 逻辑回归
    if 'lr' in steps:
        if verbose:
            _banner(5, '逻辑回归分析')

        lr_coef_results, lr_auc_results = {}, {}
        for dim in category_dims:
            coef_df, auc_df, skipped = engine.lr_by_group(df, dim, feature_cols, target=target_col)
            lr_coef_results[dim] = coef_df
            lr_auc_results[dim] = auc_df

        if qual_dims:
            coef_q, auc_q, skipped_q = engine.lr_by_qualification(
                df, qual_dims, feature_cols, target=target_col
            )
            lr_coef_results['资质标签'] = coef_q
            lr_auc_results['资质标签'] = auc_q

        if results['raw_features'] and results['derived_features']:
            comp_all = []
            for dim in category_dims:
                comp = engine.compare_feature_sets(df, dim, results['raw_features'], results['derived_features'], target=target_col)
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

        # 导出落盘走输出根（遵循 RISK_OUTPUT_ROOT，与 CLI export 一致）
        from risk_export_report.scripts.report_analysis import export_results
        output_root = get_output_root()
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

        exported = export_results(
            output_root, results,
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
