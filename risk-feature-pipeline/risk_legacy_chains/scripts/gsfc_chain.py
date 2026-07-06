# -*- coding: utf-8 -*-
"""工商财务链路 (Pipeline B) — run_gsfc_pipeline（从 risk_pipeline/pipeline.py 逐字迁出）。

算法/前端/内核均未改动；仅把模块级 _load_module/_banner 改为 from ._common 引入。
"""
import pandas as pd  # noqa: F401  函数体内亦局部 import，保留以对齐原模块

from risk_pipeline.config import COL_TARGET
from risk_mining.export import assemble_exports

from ._common import _load_module, _banner


def run_gsfc_pipeline(steps=None, verbose=True):
    """
    执行工商财务风险特征分析全流程

    参数:
        steps: 要执行的步骤列表，默认全部执行
               可选: ['data_prep', 'feature_eng', 'univariate', 'iv', 'lr', 'export']
        verbose: 是否打印详细日志

    返回:
        results: 包含各步骤结果的字典
    """
    import pandas as pd

    if steps is None:
        steps = ['data_prep', 'feature_eng', 'univariate', 'iv', 'lr', 'export']

    results = {}

    # Step 1: 数据准备
    if 'data_prep' in steps:
        if verbose:
            _banner(1, '数据准备（工商财务宽表）')

        mod_io = _load_module('risk_data_prep', 'io_utils')
        mod_config = _load_module('risk_data_prep', 'config')
        mod_builder = _load_module('risk_data_prep', 'wide_table_builder')

        project_root = mod_io.get_project_root()
        results['project_root'] = project_root
        data = mod_io.load_data(mod_config.DATA_CONFIG, project_root)
        df = mod_builder.build_wide_table(data)
        results['wide_table'] = df

        if verbose:
            n_bad = int(df[COL_TARGET].sum()) if COL_TARGET in df.columns else 0
            print(f"\n  宽表: {df.shape[0]} 行 x {df.shape[1]} 列")
            print(f"  坏客户: {n_bad} ({n_bad / len(df) * 100:.2f}%)")

    df = results.get('wide_table')
    if df is None:
        print("[错误] 没有宽表数据，请先执行 data_prep 步骤")
        return results

    # Step 2: 特征工程
    if 'feature_eng' in steps:
        if verbose:
            _banner(2, '特征工程')

        mod_fin_fe = _load_module('risk_feature_engineering', 'financial_feature_engineering')
        mod_chg_fe = _load_module('risk_feature_engineering', 'change_feature_engineering')

        df = mod_fin_fe.feature_engineering(df)
        df = mod_chg_fe.feature_engineering_gsbb(df)
        feature_cols = mod_fin_fe.get_feature_cols(df)

        results['wide_table'] = df
        results['feature_cols'] = feature_cols

        if verbose:
            print(f"\n  特征数: {len(feature_cols)}")

    feature_cols = results.get('feature_cols', [])

    # 检测分群维度
    mod_seg = _load_module('risk_segment_univariate', 'segment_univariate')
    category_dims, qual_dims = mod_seg.detect_dims(df)
    results['category_dims'] = category_dims
    results['qual_dims'] = qual_dims

    if verbose and ('univariate' in steps or 'iv' in steps or 'lr' in steps):
        print(f"\n  类别维度: {category_dims}")
        print(f"  资质标签: {len(qual_dims)} 个")

    # Step 3: 单变量分析
    if 'univariate' in steps:
        if verbose:
            _banner(3, '单变量风险分析')

        # 分群摸底
        segment_dfs = []
        for dim in category_dims:
            stats_df = mod_seg.segment_stats(df, dim)
            if not stats_df.empty:
                stats_df = stats_df.reset_index()
                stats_df.insert(0, '维度', dim)
                segment_dfs.append(stats_df)
        if segment_dfs:
            results['segment_stats'] = pd.concat(segment_dfs, ignore_index=True)

        # 资质标签摸底
        if qual_dims:
            qual_stats, qual_pivot = mod_seg.qualification_stats(df, qual_dims)
            results['qual_stats'] = qual_stats

        # 单变量分析
        corr_results, meta_results = {}, {}
        univariate_rows = []

        for dim in category_dims:
            corr_df, diff_df, pval_df, meta_df, skipped = mod_seg.univariate_by_group(
                df, dim, feature_cols
            )
            corr_results[dim] = corr_df
            meta_results[dim] = meta_df

            if not corr_df.empty:
                for group_name in corr_df.index:
                    for feat in corr_df.columns:
                        univariate_rows.append({
                            '维度': dim, '分群': group_name,
                            '特征': feat,
                            '相关系数': corr_df.loc[group_name, feat],
                            'P值': pval_df.loc[group_name, feat] if group_name in pval_df.index else None,
                        })

        if qual_dims:
            corr_q, pval_q, meta_q, skipped_q = mod_seg.univariate_by_qualification(
                df, qual_dims, feature_cols
            )
            corr_results['资质标签'] = corr_q
            meta_results['资质标签'] = meta_q

        results['corr_results'] = corr_results
        results['meta_results'] = meta_results
        if univariate_rows:
            results['univariate_long'] = pd.DataFrame(univariate_rows)

    # Step 4: IV 分析
    if 'iv' in steps:
        if verbose:
            _banner(4, 'IV 分析')

        mod_iv_calc = _load_module('risk_iv_diagnosis', 'iv_analysis')
        mod_iv_diag = _load_module('risk_iv_diagnosis', 'iv_group_diagnosis')

        iv_full_df = mod_iv_calc.run_iv_analysis(df, feature_cols)
        results['iv_full'] = iv_full_df

        iv_group_all = []
        for dim in category_dims:
            iv_df, skipped = mod_iv_diag.iv_by_group(df, dim, feature_cols)
            if iv_df is not None:
                iv_group_all.append(iv_df)

        if qual_dims:
            iv_q, skipped_q = mod_iv_diag.iv_by_qualification(df, qual_dims, feature_cols)
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

        mod_lr = _load_module('risk_logistic_regression', 'group_logistic_regression')

        lr_coef_results, lr_auc_results = {}, {}
        for dim in category_dims:
            coef_df, auc_df, skipped = mod_lr.lr_by_group(df, dim, feature_cols)
            lr_coef_results[dim] = coef_df
            lr_auc_results[dim] = auc_df

        if qual_dims:
            coef_q, auc_q, skipped_q = mod_lr.lr_by_qualification(
                df, qual_dims, feature_cols
            )
            lr_coef_results['资质标签'] = coef_q
            lr_auc_results['资质标签'] = auc_q

        results['lr_coef_results'] = lr_coef_results
        results['lr_auc_results'] = lr_auc_results

    # Step 6: 导出
    # 统一走 report_analysis（与 credit/generic 三链路对齐）。gsfc 的 univariate/iv/lr
    # 步骤已写入与 generic 完全一致的中间结果键（corr_results / meta_results / iv_full /
    # iv_group_all / reliability_summary / lr_coef_results / lr_auc_results），
    # 因此这里直接复用 generic 的导出装配；旧 report_export 因仍按 '分群' 旧 schema 取列，
    # 在新 schema 下会 KeyError，是 gsfc 无法到 Level 1 的根因。
    if 'export' in steps:
        if verbose:
            _banner(6, '结果导出')

        mod_report = _load_module('risk_export_report', 'report_analysis')
        mod_io = _load_module('risk_export_report', 'io_utils')
        mod_export_cfg = _load_module('risk_export_report', 'config')

        project_root = results.get('project_root') or mod_io.get_project_root()
        project_name = mod_export_cfg.GSFC_LLM_PROJECT_NAME

        # 装配 4 张导出表（唯一实现 risk_mining.export.assemble_exports）；
        # gsfc 目标列固定为 COL_TARGET，与 credit 一致、行为逐字保住。
        assemble_exports(
            results,
            df=df,
            feature_cols=feature_cols,
            category_dims=category_dims,
            qual_dims=qual_dims,
            target_col=COL_TARGET,
        )

        exported = mod_report.export_results(
            project_root, results,
            project_name=project_name,
            output_subdir=project_name,   # 稳定子目录，供 query/visualize/load_results 按项目名定位
            results_base=mod_export_cfg.RESULTS_DIR_GSFC,
            output_base=mod_export_cfg.OUTPUT_DIR_GSFC,
        )
        results['exported_files'] = exported

        if verbose:
            print(f"\n  共导出 {len(exported)} 个文件")

    if verbose:
        print(f"\n{'=' * 60}")
        print('工商财务链路分析完成')
        print('=' * 60)

    return results
