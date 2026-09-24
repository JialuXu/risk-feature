# -*- coding: utf-8 -*-
"""
分群摸底与单变量风险分析：类别维度统计、二值标签对比、点二列相关、T 检验与跨分群离散度。

阈值一律取自 config.SAMPLE_THRESHOLDS，与项目 rules 对齐。
"""

import pandas as pd

from .config import CREDIT_CONFIG, SAMPLE_THRESHOLDS, COL_TARGET
from .univariate import calc_correlation_pvalue, ttest_good_bad

import sys
from pathlib import Path
_MY_SKILLS_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _MY_SKILLS_ROOT not in sys.path:
    sys.path.insert(0, _MY_SKILLS_ROOT)
from risk_core.column_mapper import ColumnMapper

_T = SAMPLE_THRESHOLDS
_mapper = ColumnMapper()


def _print_sample_summary(df, label='全量', target=COL_TARGET, indent=2):
    """输出样本概况（总样本/坏客户/好客户/坏客户率）"""
    prefix = ' ' * indent
    n_total = len(df)
    n_bad = int(df[target].sum())
    n_good = n_total - n_bad
    bad_rate = n_bad / n_total if n_total > 0 else 0
    print(
        f"{prefix}[{label}] "
        f"总样本={n_total}, 坏客户={n_bad}, 好客户={n_good}, "
        f"坏客户率={bad_rate:.4f}"
    )
    return n_total, n_bad, n_good


def _print_group_table(analyzed, skipped_list, analysis_name,
                       thresholds=None, indent=2):
    """输出分群筛选汇总（已分析 / 已跳过）"""
    prefix = ' ' * indent
    n_analyzed = len(analyzed)
    n_skipped = len(skipped_list)
    n_total_groups = n_analyzed + n_skipped
    if thresholds:
        thr_str = ', '.join(f'{k}>={v}' for k, v in thresholds.items())
        print(f"{prefix}[{analysis_name}] 门槛条件: {thr_str}")
    print(
        f"{prefix}[{analysis_name}] "
        f"分群总数={n_total_groups}, "
        f"纳入分析={n_analyzed}, 跳过={n_skipped}"
    )
    if analyzed:
        total_samples = sum(a['样本数'] for a in analyzed)
        total_bad = sum(a['坏客户数'] for a in analyzed)
        print(
            f"{prefix}  纳入分析的分群合计: "
            f"样本={total_samples}, 坏客户={total_bad}"
        )
        for a in analyzed:
            print(
                f"{prefix}    - {a['分群名称']}: "
                f"样本={a['样本数']}, 坏客户={a['坏客户数']}, "
                f"好客户={a['样本数'] - a['坏客户数']}, "
                f"坏客户率={a['坏客户数'] / a['样本数']:.4f}"
            )


def detect_dims(df, category_dims=None, qual_prefix=None):
    """
    自动检测可用的分群维度

    返回:
        category_dims: 有效的类别型维度列表（来自配置且在表中有非空值）
        qual_dims: 二进制资质标签列名列表（通过 ColumnMapper 配置的前缀检测）
    """
    if category_dims is None:
        category_dims = _mapper.credit_category_dims
    effective_dims = [
        c for c in category_dims
        if c in df.columns and df[c].notna().sum() > 0
    ]
    qual_dims = _mapper.detect_qual_cols(df.columns, prefix_override=qual_prefix)
    return effective_dims, qual_dims


def segment_stats(df, dim_col, min_group_size=None):
    """
    类别型维度的分群统计（按样本数降序，过滤小分群）

    min_group_size 默认 SAMPLE_THRESHOLDS['MIN_SAMPLES']
    """
    if min_group_size is None:
        min_group_size = _T['MIN_SAMPLES']

    df_v = df[df[dim_col].notna()]
    if len(df_v) == 0:
        return pd.DataFrame()

    g = df_v.groupby(dim_col)[COL_TARGET].agg(['count', 'sum', 'mean']).round(4)
    g.columns = ['样本数', '坏客户数', '坏客户率']
    g['占比%'] = (g['样本数'] / g['样本数'].sum() * 100).round(2)
    g = g.sort_values('样本数', ascending=False)

    n_before = len(g)
    g = g[g['样本数'] >= min_group_size]
    n_filtered = n_before - len(g)
    if n_filtered > 0:
        print(
            f"  {dim_col}: 过滤 {n_filtered} 个小分群"
            f"（样本数 < {min_group_size}），保留 {len(g)} 个"
        )

    return g


def qualification_stats(df, qual_cols):
    """
    二进制标签维度的分群统计（有/无资质对比）

    返回:
        stats_df: 资质标签统计表
        pivot: 坏客户率透视（含有/无资质差异列，若可计算）
    """
    rows = []
    for qc in qual_cols:
        if qc not in df.columns:
            continue
        df_v = df[df[qc].notna()]
        qname = _mapper.strip_qual_prefix(qc)
        for label, subset in [
            ('有该资质', df_v[df_v[qc] == 1]),
            ('无该资质', df_v[df_v[qc] == 0]),
        ]:
            if len(subset) > 0:
                rows.append({
                    '资质类别': qname,
                    '分组': label,
                    '样本数': len(subset),
                    '坏客户数': int(subset[COL_TARGET].sum()),
                    '坏客户率': float(subset[COL_TARGET].mean()),
                })

    if not rows:
        return pd.DataFrame(), pd.DataFrame()

    df_out = pd.DataFrame(rows)
    pivot = df_out.pivot_table(
        index='资质类别', columns='分组', values='坏客户率', aggfunc='first'
    )
    if '有该资质' in pivot.columns and '无该资质' in pivot.columns:
        pivot = pivot.copy()
        pivot['坏客户率差异'] = pivot['有该资质'] - pivot['无该资质']

    return df_out, pivot


def _univariate_single_group(group_df, feature_cols, target=COL_TARGET):
    """单个分群内：点二列相关、均值差、Welch T 检验 P 值（与 univariate 模块对齐）"""
    corr_row, diff_row, pval_row = {}, {}, {}
    for feat in feature_cols:
        if feat not in group_df.columns:
            continue
        g = group_df[[feat, target]].copy()
        g[feat] = g[feat].fillna(0)

        corr, _ = calc_correlation_pvalue(g, feat, target)
        if pd.isna(corr):
            corr = 0.0
        elif float(g[feat].std()) == 0:
            corr = 0.0

        good_mean, bad_mean, _, p = ttest_good_bad(g, feat, target)
        diff_row[feat] = (
            bad_mean - good_mean
            if pd.notna(bad_mean) and pd.notna(good_mean) else 0.0
        )
        pval_row[feat] = float(p) if pd.notna(p) else 1.0
        corr_row[feat] = float(corr)

    return corr_row, diff_row, pval_row


def univariate_by_group(
    df, dim_col, feature_cols,
    min_bad=None, min_good=None, min_group_size=None, target=COL_TARGET,
):
    """
    按类别型维度分群做单变量分析。

    默认门槛：MIN_SAMPLES、MIN_BAD_CORR、MIN_GOOD_CORR（均来自 SAMPLE_THRESHOLDS）。
    """
    if min_bad is None:
        min_bad = _T['MIN_BAD_CORR']
    if min_good is None:
        min_good = _T['MIN_GOOD_CORR']
    if min_group_size is None:
        min_group_size = _T['MIN_SAMPLES']

    _print_sample_summary(df, label=f'单变量分析({dim_col}) - 输入全量', target=target)
    df_v = df[df[dim_col].notna()]
    _print_sample_summary(df_v, label=f'剔除{dim_col}为空后', target=target)

    corr_dict, diff_dict, pval_dict, meta_rows = {}, {}, {}, []
    skipped = []
    analyzed = []

    for gname, gdf in df_v.groupby(dim_col):
        n_total = len(gdf)
        n_bad = int(gdf[target].sum())
        n_good = n_total - n_bad

        if n_total < min_group_size:
            skipped.append(f"{gname}: 总样本数={n_total} < {min_group_size}")
            continue
        if n_bad < min_bad:
            skipped.append(f"{gname}: 坏客户数={n_bad} < {min_bad}")
            continue
        if n_good < min_good:
            skipped.append(f"{gname}: 好客户数={n_good} < {min_good}")
            continue

        c, d, p = _univariate_single_group(gdf, feature_cols, target=target)
        corr_dict[gname] = c
        diff_dict[gname] = d
        pval_dict[gname] = p
        meta_rows.append({
            '分群名称': gname,
            '样本数': n_total,
            '坏客户数': n_bad,
            '坏客户率': n_bad / n_total,
        })
        analyzed.append({
            '分群名称': gname,
            '样本数': n_total,
            '坏客户数': n_bad,
        })

    _print_group_table(
        analyzed,
        skipped,
        '单变量分析',
        thresholds={
            '总样本': min_group_size,
            '坏客户': min_bad,
            '好客户': min_good,
        },
    )
    if skipped:
        print(f"\n  [{dim_col}] 跳过 {len(skipped)} 个分群:")
        for s in skipped:
            print(f"    - {s}")

    corr_df = pd.DataFrame(corr_dict).T
    diff_df = pd.DataFrame(diff_dict).T
    pval_df = pd.DataFrame(pval_dict).T
    meta_df = (
        pd.DataFrame(meta_rows).set_index('分群名称')
        if meta_rows else pd.DataFrame()
    )

    if not meta_df.empty:
        order = meta_df.sort_values('样本数', ascending=False).index
        idx = [i for i in order if i in corr_df.index]
        corr_df = corr_df.reindex(idx)
        diff_df = diff_df.reindex(idx)
        pval_df = pval_df.reindex(idx)
        meta_df = meta_df.reindex(idx)

    return corr_df, diff_df, pval_df, meta_df, skipped


def univariate_by_qualification(
    df, qual_cols, feature_cols,
    min_bad=None, min_good=None, target=COL_TARGET,
):
    """
    按二进制标签：仅在有该资质（值为 1）的子样本内做单变量分析。

    默认门槛：MIN_BAD_CORR、MIN_GOOD_CORR。
    """
    if min_bad is None:
        min_bad = _T['MIN_BAD_CORR']
    if min_good is None:
        min_good = _T['MIN_GOOD_CORR']

    _print_sample_summary(
        df, label='单变量分析(资质标签) - 输入全量', target=target,
    )

    corr_dict, pval_dict, meta_rows = {}, {}, []
    skipped = []
    analyzed = []

    for qc in qual_cols:
        if qc not in df.columns:
            continue
        df_yes = df[df[qc] == 1]
        qname = _mapper.strip_qual_prefix(qc)
        n_bad = int(df_yes[target].sum())
        n_good = len(df_yes) - n_bad

        if n_bad < min_bad:
            skipped.append(f"{qname}: 坏客户数={n_bad} < {min_bad}")
            continue
        if n_good < min_good:
            skipped.append(f"{qname}: 好客户数={n_good} < {min_good}")
            continue

        c, _, p = _univariate_single_group(df_yes, feature_cols, target=target)
        corr_dict[qname] = c
        pval_dict[qname] = p
        meta_rows.append({
            '分群名称': qname,
            '样本数': len(df_yes),
            '坏客户数': n_bad,
            '坏客户率': n_bad / len(df_yes),
        })
        analyzed.append({
            '分群名称': qname,
            '样本数': len(df_yes),
            '坏客户数': n_bad,
        })

    _print_group_table(
        analyzed,
        skipped,
        '单变量分析(资质标签)',
        thresholds={'坏客户': min_bad, '好客户': min_good},
    )
    if skipped:
        print(f"\n  [资质标签] 跳过 {len(skipped)} 个分群:")
        for s in skipped:
            print(f"    - {s}")

    corr_df = pd.DataFrame(corr_dict).T
    pval_df = pd.DataFrame(pval_dict).T
    meta_df = (
        pd.DataFrame(meta_rows).set_index('分群名称')
        if meta_rows else pd.DataFrame()
    )

    return corr_df, pval_df, meta_df, skipped


def cross_group_variance(corr_results):
    """
    跨分群特征风险贡献差异：对 corr_results 中各维度的相关系数矩阵做离散度汇总。

    参数:
        corr_results: dict, {维度名: corr_df}

    返回:
        variance_df: 各特征在各维度下的相关系数统计
        feat_summary: 特征一致性汇总（按平均极差降序）
    """
    rows = []
    for dim_name, corr_df in corr_results.items():
        if corr_df is None or corr_df.empty:
            continue
        for feat in corr_df.columns:
            vals = corr_df[feat].dropna()
            if len(vals) > 1:
                rows.append({
                    '分群维度': dim_name,
                    '特征': feat,
                    '相关系数均值': vals.mean(),
                    '相关系数标准差': vals.std(),
                    '极差': vals.max() - vals.min(),
                    '分群数': len(vals),
                })

    if not rows:
        return pd.DataFrame(), pd.DataFrame()

    var_df = pd.DataFrame(rows)
    feat_summary = var_df.groupby('特征').agg({
        '相关系数均值': 'mean',
        '相关系数标准差': 'mean',
        '极差': 'mean',
    }).round(4)
    feat_summary.columns = ['平均相关系数', '平均标准差', '平均极差']
    feat_summary = feat_summary.sort_values('平均极差', ascending=False)

    return var_df, feat_summary
