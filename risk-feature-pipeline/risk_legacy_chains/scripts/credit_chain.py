# -*- coding: utf-8 -*-
"""征信链路 (Pipeline A) — run_credit_pipeline（从 risk_pipeline/pipeline.py 逐字迁出）。

算法/前端/内核均未改动；仅把模块级 _load_module/_banner 改为 from ._common 引入。
"""
import pandas as pd  # noqa: F401  函数体内亦局部 import，保留以对齐原模块

from risk_pipeline.config import COL_TARGET
from risk_mining.export import assemble_exports

from ._common import _load_module, _banner


def run_credit_pipeline(steps=None, verbose=True):
    """
    执行征信风险特征分析全流程

    参数:
        steps: 要执行的步骤列表，默认全部执行
               可选: ['data_prep', 'univariate', 'lr', 'iv', 'export']
        verbose: 是否打印详细日志

    返回:
        results: 包含各步骤结果的字典
    """
    import pandas as pd

    # 加载各模块
    mod_data_prep = _load_module('risk_data_prep', 'data_prep')
    mod_config = _load_module('risk_data_prep', 'config')
    mod_iv_diag = _load_module('risk_iv_diagnosis', 'iv_group_diagnosis')
    mod_iv_calc = _load_module('risk_iv_diagnosis', 'iv_analysis')

    CREDIT_CONFIG = mod_config.CREDIT_CONFIG

    if steps is None:
        steps = ['data_prep', 'feature_engineering', 'univariate', 'lr', 'iv', 'export']

    results = {}

    # Step 1: 数据准备
    if 'data_prep' in steps:
        if verbose:
            _banner(1, '数据准备（征信宽表）')
        data = mod_data_prep.load_credit_data()
        df, summary = mod_data_prep.prepare_credit_wide_table(data)
        results['wide_table'] = df
        results['summary'] = summary
        results['data'] = data

        # 自动检测维度
        category_dims, qual_dims = mod_iv_diag.detect_dims(df)
        results['category_dims'] = category_dims
        results['qual_dims'] = qual_dims

        # 特征列
        raw_features = CREDIT_CONFIG['raw_features']
        derived_features = CREDIT_CONFIG['derived_features']
        feature_cols = [f for f in raw_features + derived_features if f in df.columns]
        
        # 自动过滤零方差特征
        zero_var_feats = [f for f in feature_cols if f in df.columns and df[f].std() == 0]
        if zero_var_feats:
            if verbose:
                print(f"  [跳过] 方差为零的特征（将从分析中排除）: {zero_var_feats}")
            feature_cols = [f for f in feature_cols if f not in zero_var_feats]
            
        results['feature_cols'] = feature_cols
        results['raw_features'] = [f for f in raw_features if f in df.columns and f not in zero_var_feats]
        results['derived_features'] = [f for f in derived_features if f in df.columns and f not in zero_var_feats]

        if verbose:
            print(f"\n  宽表: {df.shape[0]} 行 x {df.shape[1]} 列")
            print(f"  特征: {len(feature_cols)} 个")
            print(f"  类别维度: {category_dims}")
            print(f"  资质标签: {len(qual_dims)} 个")

    df = results.get('wide_table')
    feature_cols = results.get('feature_cols', [])
    category_dims = results.get('category_dims', [])
    qual_dims = results.get('qual_dims', [])

    if df is None:
        print("[错误] 没有宽表数据，请先执行 data_prep 步骤")
        return results

    # Step 1.5: 特征工程（征信衍生特征）
    if 'feature_engineering' in steps:
        if verbose:
            _banner('1.5', '征信特征工程（衍生比率特征）')

        mod_credit_fe = _load_module('risk_feature_engineering', 'credit_feature_engineering')
        df = mod_credit_fe.create_credit_features(df)
        results['wide_table'] = df

        # 用 get_feature_sets 重新计算有效特征（过滤 std=0 的列）
        feat_sets = mod_credit_fe.get_feature_sets(df)
        feature_cols     = feat_sets['all']        # 原始+衍生，过滤无效
        raw_features     = feat_sets['raw']
        derived_features = feat_sets['derived']

        results['feature_cols']     = feature_cols
        results['raw_features']     = raw_features
        results['derived_features'] = derived_features

        if verbose:
            print(f"  原始特征: {len(raw_features)} 个")
            print(f"  衍生特征: {len(derived_features)} 个")
            print(f"  总特征数: {len(feature_cols)} 个")

    # Step 2: 单变量分析
    if 'univariate' in steps:
        if verbose:
            _banner(2, '单变量风险分析')

        corr_results, meta_results = {}, {}
        for dim in category_dims:
            corr_df, diff_df, pval_df, meta_df, skipped = mod_iv_diag.univariate_by_group(
                df, dim, feature_cols
            )
            corr_results[dim] = corr_df
            meta_results[dim] = meta_df

        if qual_dims:
            corr_q, pval_q, meta_q, skipped_q = mod_iv_diag.univariate_by_qualification(
                df, qual_dims, feature_cols
            )
            corr_results['资质标签'] = corr_q
            meta_results['资质标签'] = meta_q

        results['corr_results'] = corr_results
        results['meta_results'] = meta_results

    # Step 4: IV 分析
    if 'iv' in steps:
        if verbose:
            _banner(4, 'IV 分析与可信度诊断')

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

        lr_coef_results, lr_auc_results = {}, {}
        for dim in category_dims:
            coef_df, auc_df, skipped = mod_iv_diag.lr_by_group(df, dim, feature_cols)
            lr_coef_results[dim] = coef_df
            lr_auc_results[dim] = auc_df

        if qual_dims:
            coef_q, auc_q, skipped_q = mod_iv_diag.lr_by_qualification(
                df, qual_dims, feature_cols
            )
            lr_coef_results['资质标签'] = coef_q
            lr_auc_results['资质标签'] = auc_q

        # 原始 vs 衍生特征 AUC 对比
        raw_feats = results.get('raw_features', [])
        derived_feats = results.get('derived_features', [])
        if raw_feats and derived_feats:
            comp_all = []
            for dim in category_dims:
                comp = mod_iv_diag.compare_feature_sets(df, dim, raw_feats, derived_feats)
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

        mod_report = _load_module('risk_export_report', 'report_analysis')
        mod_io = _load_module('risk_export_report', 'io_utils')
        project_root = mod_io.get_project_root()

        # 装配 4 张导出表（corr/lr/comprehensive/llm_report_data）→ results
        # 唯一实现见 risk_mining.export.assemble_exports；credit 显式补 target_col=COL_TARGET
        # 为一致性对齐（其目标列本就是 is_bad，行为与旧实现逐字一致）。
        assemble_exports(
            results,
            df=df,
            feature_cols=feature_cols,
            category_dims=category_dims,
            qual_dims=qual_dims,
            target_col=COL_TARGET,
        )

        exported = mod_report.export_results(project_root, results)
        results['exported_files'] = exported

        if verbose:
            print(f"\n  共导出 {len(exported)} 个文件")

    if verbose:
        print(f"\n{'=' * 60}")
        print('征信链路分析完成')
        print('=' * 60)

    return results
