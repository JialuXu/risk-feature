# -*- coding: utf-8 -*-
"""挖掘内核·导出装配唯一实现（解耦重构 Stage 3）。

背景（DECOUPLING-DESIGN §1.2 根因2 / §5.4）：``build_corr_export`` /
``build_lr_export`` / ``build_comprehensive_table`` / ``build_llm_report_data``
四个 report 构建器的**调用序列**曾在 4 处各抄一份——
``pipeline.py`` 的 credit/gsfc/generic 三段 + ``commands/export.py`` 的 ``cmd_export``。
四份平行副本导致「改一处导出字段要同步四处、漏一处运行期静默降级」。

本模块把这段装配收敛为**唯一** ``assemble_exports()``：读 results 中间产物、
调 4 个构建器、把 ``corr_exports/lr_exports/comprehensive/llm_report_data`` 写回
results（原地）。落盘参数（project_name / output_subdir / results_base /
output_base）因链路而异、**不属装配范围**——各调用方在 assemble 之后各自
``export_results(...)``。

不变量（§7「对外 schema 一致」）：credit/gsfc 行为逐字保住——
- credit/gsfc 历史上**不传** raw/derived → 构建器走 ``None`` 默认、跳过原始-衍生对比；
  故本函数默认 ``raw_features=derived_features=None``，调用方不传即维持旧行为
  （``None`` 与 ``[]`` 在两个构建器里等价：``if a or b`` / ``set(a or [])``）。
- credit 历史上**不传** ``target_col`` → 构建器默认 ``COL_TARGET='is_bad'``；credit 的
  目标列本就是 ``is_bad``，故显式补传 ``target_col`` 是**一致性对齐、非行为修复**。
"""
from __future__ import annotations

from risk_core.config import COL_TARGET


def assemble_exports(
    results,
    *,
    df,
    feature_cols,
    category_dims,
    qual_dims,
    raw_features=None,
    derived_features=None,
    target_col=COL_TARGET,
):
    """把 4 个 report 构建器的调用序列收敛为唯一装配点（就地写回 ``results``）。

    参数:
        results: 分析中间产物 dict（含 corr_results/meta_results/lr_coef_results/
                 lr_auc_results/iv_full/iv_group_all/reliability_summary/... 等键）。
                 本函数会**就地新增** corr_exports/lr_exports/comprehensive/
                 llm_report_data 四个键。
        df: 宽表 DataFrame，仅 ``build_llm_report_data`` 需要（要数坏客户等）。
            为 ``None`` 时跳过 LLM 报告数据构建——对齐 ``cmd_export`` 在
            prepared.csv 缺失时不构建 LLM 数据的历史行为。
        feature_cols / category_dims / qual_dims: 透传给 ``build_llm_report_data``。
        raw_features / derived_features: 原始/衍生特征列表；默认 ``None``（=不做
            原始-衍生对比），credit/gsfc 沿用默认，generic/cmd_export 显式传入。
        target_col: 目标列名，默认 ``COL_TARGET``。

    返回:
        results（与入参同一对象，便于链式使用）。
    """
    from risk_export_report.scripts.report_analysis import (
        build_corr_export,
        build_lr_export,
        build_comprehensive_table,
        build_llm_report_data,
    )

    corr_results = results.get('corr_results') or {}
    meta_results = results.get('meta_results') or {}
    lr_coef_results = results.get('lr_coef_results') or {}
    lr_auc_results = results.get('lr_auc_results') or {}

    if corr_results:
        results['corr_exports'] = build_corr_export(corr_results, meta_results)
    if lr_coef_results:
        results['lr_exports'] = build_lr_export(lr_coef_results, lr_auc_results)

    iv_full_df = results.get('iv_full')
    if iv_full_df is not None and not iv_full_df.empty:
        results['comprehensive'] = build_comprehensive_table(
            iv_full_df, corr_results, lr_coef_results,
            results.get('iv_group_all'),
            raw_features=raw_features or [],
            derived_features=derived_features or [],
        )

        # LLM 报告数据需宽表；df 为 None（cmd_export 下 prepared.csv 缺失）则跳过。
        if df is not None:
            try:
                results['llm_report_data'] = build_llm_report_data(
                    df=df,
                    iv_full_df=iv_full_df,
                    corr_results=corr_results,
                    meta_results=meta_results,
                    lr_coef_results=lr_coef_results,
                    lr_auc_results=lr_auc_results,
                    iv_group_all=results.get('iv_group_all'),
                    rel_summary=results.get('reliability_summary'),
                    rel_warnings=results.get('reliability_warnings', []),
                    comp_all=results.get('feature_set_comparison'),
                    feature_cols=feature_cols,
                    category_dims=category_dims,
                    qual_dims=qual_dims,
                    raw_features=raw_features or [],
                    derived_features=derived_features or [],
                    target_col=target_col,
                )
            except Exception as e:
                print(f"  [警告] LLM 报告数据构建失败：{e}")

    return results
