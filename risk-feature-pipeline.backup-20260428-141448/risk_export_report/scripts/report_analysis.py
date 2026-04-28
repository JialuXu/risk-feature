# -*- coding: utf-8 -*-
"""
企业征信风险特征分析核心模块

提供征信数据的完整分析流水线：
- 数据加载与预处理
- 特征工程（原始特征 + 衍生比率特征）
- 分群基础分析（类别型 + 二进制标签型）
- 单变量风险分析（相关系数 + T检验）
- 多变量逻辑回归（支持交叉验证AUC）
- IV值分析（自适应分箱 + WOE截断 + 可信度评估）
- 可信度诊断
- 结果导出
"""

import os
import warnings
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_score

from .config import (
    CREDIT_CONFIG,
    CREDIT_PIPELINE_PATHS,
    GENERIC_PIPELINE_PATHS,
    CREDIT_LLM_REPORT_GOAL_TEMPLATE,
    SAMPLE_THRESHOLDS,
    MIN_SAMPLES,
    MIN_BAD_SAMPLES,
    COL_CUSTOMER_ID, COL_CUSTOMER_ID_STR, COL_TARGET,
    COL_REPORT_DATE, COL_QUAL_PREFIX,
    COL_INDUSTRY_DATA_COLS, COL_AMOUNT_COLS, COL_SEGMENT_DIMS,
)
from .io_utils import get_project_root, read_csv_auto_encoding, ensure_dir, _clean_id, safe_divide

import sys as _sys
from pathlib import Path as _Path
_MY_SKILLS_ROOT = str(_Path(__file__).resolve().parent.parent.parent)
if _MY_SKILLS_ROOT not in _sys.path:
    _sys.path.insert(0, _MY_SKILLS_ROOT)
from shared.column_mapper import ColumnMapper

_mapper = ColumnMapper()
from .iv_analysis import calc_iv as _calc_iv_base, _assess_iv_reliability

warnings.filterwarnings('ignore')

# 从配置中提取阈值常量
_T = SAMPLE_THRESHOLDS


def _print_sample_summary(df, label='全量', target=COL_TARGET, indent=2):
    """输出样本概况（总样本/坏客户/好客户/坏客户率）"""
    prefix = ' ' * indent
    n_total = len(df)
    n_bad = int(df[target].sum())
    n_good = n_total - n_bad
    bad_rate = n_bad / n_total if n_total > 0 else 0
    print(f"{prefix}[{label}] "
          f"总样本={n_total}, 坏客户={n_bad}, 好客户={n_good}, "
          f"坏客户率={bad_rate:.4f}")
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
    print(f"{prefix}[{analysis_name}] "
          f"分群总数={n_total_groups}, "
          f"纳入分析={n_analyzed}, 跳过={n_skipped}")
    if analyzed:
        total_samples = sum(a['样本数'] for a in analyzed)
        total_bad = sum(a['坏客户数'] for a in analyzed)
        print(f"{prefix}  纳入分析的分群合计: "
              f"样本={total_samples}, 坏客户={total_bad}")
        for a in analyzed:
            print(f"{prefix}    - {a['分群名称']}: "
                  f"样本={a['样本数']}, 坏客户={a['坏客户数']}, "
                  f"好客户={a['样本数'] - a['坏客户数']}, "
                  f"坏客户率={a['坏客户数'] / a['样本数']:.4f}")


# =============================================================================
# Section 1: 数据加载与准备
# =============================================================================

def load_credit_data(project_root=None):
    """
    加载征信分析所需的全部数据

    参数:
        project_root: 项目根目录，为None时自动检测

    返回:
        data: dict，包含各数据表的DataFrame
    """
    if project_root is None:
        project_root = get_project_root()

    data = {}
    data_config = CREDIT_CONFIG['data']
    for name, rel_path in data_config.items():
        full_path = os.path.join(project_root, rel_path)
        if os.path.exists(full_path):
            data[name] = read_csv_auto_encoding(full_path)
            print(f"  {name}: {data[name].shape}")
        else:
            print(f"  [警告] {name} 文件不存在: {full_path}")
    return data


def prepare_credit_wide_table(data):
    """
    构建征信分析宽表

    处理流程：
    1. 以客户信息为总样本基准表（定义分析的总体范围）
    2. 添加坏客户标签
    3. 征信数据按报告日期去重（取最新记录），LEFT JOIN到客户基准表
    4. 合并产业数据（产业属性 + 企业资质标签）
    5. 缺失值处理

    总样本以客户信息为准，征信数据中不在客户范围内的记录不纳入分析。

    参数:
        data: dict，load_credit_data() 的返回值

    返回:
        df: 合并后的宽表（行数 = 客户信息去重后的客户数）
        summary: 合并概况dict
    """
    df_cust = data['客户信息'].copy()
    df_bad = data['坏客户标记'].copy()

    # -- 统一主键格式 + 去重 --
    df_cust[COL_CUSTOMER_ID_STR] = _clean_id(df_cust[COL_CUSTOMER_ID])
    df_cust = df_cust.drop_duplicates(
        subset=[COL_CUSTOMER_ID_STR], keep='first'
    ).reset_index(drop=True)

    # -- 标记坏客户 --
    bad_set = set(_clean_id(df_bad[COL_CUSTOMER_ID]))
    df_cust[COL_TARGET] = df_cust[COL_CUSTOMER_ID_STR].isin(bad_set).astype(int)

    # -- 处理客户信息中的金额字段 --
    _amt_cols = COL_AMOUNT_COLS
    if all(c in df_cust.columns for c in _amt_cols):
        for c in _amt_cols:
            df_cust[c] = df_cust[c].replace('-', np.nan)
            df_cust[c] = (
                df_cust[c].astype(str)
                .str.replace(',', '', regex=False)
            )
            df_cust[c] = pd.to_numeric(df_cust[c], errors='coerce')

        _sub_cols = [c for c in COL_AMOUNT_COLS[1:] if c in df_cust.columns]
        _sub_sum = df_cust[_sub_cols].sum(axis=1, min_count=1)
        _fix_mask = df_cust[COL_AMOUNT_COLS[0]].isna() & _sub_sum.notna()
        n_fixed = _fix_mask.sum()
        if n_fixed > 0:
            df_cust.loc[_fix_mask, COL_AMOUNT_COLS[0]] = _sub_sum[_fix_mask]
            print(f"  [修复] {COL_AMOUNT_COLS[0]}为空但有余额子项的 {n_fixed} 行，"
                  f"已用余额子项加总回补")

    n_total = len(df_cust)
    n_bad = int(df_cust[COL_TARGET].sum())

    summary = {
        '客户总数(总样本)': n_total,
        '坏客户数': n_bad,
        '坏客户率': float(df_cust[COL_TARGET].mean()),
    }

    print(f"  总样本基准(客户信息): {n_total} 户, "
          f"坏客户 {n_bad}, 坏客户率 {summary['坏客户率']:.4f}")

    # -- 征信数据去重 + LEFT JOIN到客户基准表 --
    df_base = df_cust
    if '征信数据' in data:
        df_credit_raw = data['征信数据'].copy()

        # 按报告日期降序，每个客户保留最新记录
        if COL_REPORT_DATE in df_credit_raw.columns:
            df_credit_raw[COL_REPORT_DATE] = pd.to_datetime(
                df_credit_raw[COL_REPORT_DATE], errors='coerce'
            )
            df_credit = (
                df_credit_raw
                .sort_values(COL_REPORT_DATE, ascending=False)
                .drop_duplicates(subset=[COL_CUSTOMER_ID], keep='first')
                .reset_index(drop=True)
            )
        else:
            df_credit = df_credit_raw.drop_duplicates(
                subset=[COL_CUSTOMER_ID], keep='first'
            ).reset_index(drop=True)

        df_credit[COL_CUSTOMER_ID_STR] = _clean_id(df_credit[COL_CUSTOMER_ID])

        # 统计征信数据与客户范围的匹配情况
        cust_set = set(df_cust[COL_CUSTOMER_ID_STR])
        n_credit_dedup = len(df_credit)
        credit_in_scope = df_credit[COL_CUSTOMER_ID_STR].isin(cust_set)
        n_in_scope = int(credit_in_scope.sum())
        n_out_scope = n_credit_dedup - n_in_scope

        print(f"  征信数据去重后: {n_credit_dedup} 条")
        print(f"    - 匹配客户范围: {n_in_scope} 条")
        print(f"    - 超出客户范围(已排除): {n_out_scope} 条")

        # 筛选征信特征列（排除主键和日期）
        credit_feature_cols = [
            c for c in df_credit.columns
            if c not in (COL_CUSTOMER_ID, COL_CUSTOMER_ID_STR, COL_REPORT_DATE)
        ]
        merge_cols = [COL_CUSTOMER_ID_STR] + credit_feature_cols

        # LEFT JOIN: 以客户信息为基准，左连接征信数据
        df_base = df_cust.merge(
            df_credit[merge_cols], on=COL_CUSTOMER_ID_STR, how='left'
        )

        credit_id_set = set(df_credit[COL_CUSTOMER_ID_STR])
        n_matched = int(
            df_base[COL_CUSTOMER_ID_STR].isin(credit_id_set).sum()
        )
        n_no_credit = n_total - n_matched
        summary['匹配征信数据'] = n_matched
        summary['无征信数据客户'] = n_no_credit
        print(f"    - 有征信数据的客户: {n_matched} "
              f"({n_matched / n_total * 100:.1f}%)")
        print(f"    - 无征信数据的客户: {n_no_credit} "
              f"({n_no_credit / n_total * 100:.1f}%)")

    # -- 合并产业数据 --
    if '产业数据' in data:
        df_ind = data['产业数据'].copy()
        df_ind[COL_CUSTOMER_ID_STR] = _clean_id(df_ind[COL_CUSTOMER_ID])
        # 产业属性列 + 资质标签列
        ind_cols = [COL_CUSTOMER_ID_STR]
        for c in COL_INDUSTRY_DATA_COLS:
            if c in df_ind.columns:
                ind_cols.append(c)
        # 二进制资质标签列（以 '是_' 开头）
        qual_cols = [c for c in df_ind.columns if c.startswith(COL_QUAL_PREFIX)]
        ind_cols.extend(qual_cols)
        # 去重
        ind_cols = list(dict.fromkeys(ind_cols))
        df_base = df_base.merge(
            df_ind[ind_cols], on=COL_CUSTOMER_ID_STR, how='left'
        )
        n_matched_ind = (
            df_base[COL_INDUSTRY_DATA_COLS[0]].notna().sum()
            if COL_INDUSTRY_DATA_COLS[0] in df_base.columns else 0
        )
        summary['匹配产业信息'] = n_matched_ind

    # -- 千分位逗号修复：部分数值列含逗号分隔符（如 "1,404"），需先去逗号再转数值 --
    object_skip_cols = (
        COL_CUSTOMER_ID, COL_CUSTOMER_ID_STR, COL_REPORT_DATE,
    ) + tuple(COL_SEGMENT_DIMS) + (
        '行业大类', '行业小类',
    ) + tuple(COL_INDUSTRY_DATA_COLS)
    for col in df_base.columns:
        if df_base[col].dtype == object and col not in object_skip_cols:
            sample = df_base[col].dropna().head(200)
            if len(sample) == 0:
                continue
            cleaned = sample.astype(str).str.replace(',', '', regex=False)
            converted = pd.to_numeric(cleaned, errors='coerce')
            pct_numeric = converted.notna().sum() / len(sample)
            if pct_numeric >= 0.8:
                df_base[col] = (
                    df_base[col].astype(str)
                    .str.replace(',', '', regex=False)
                )
                df_base[col] = pd.to_numeric(df_base[col], errors='coerce')
                print(f"  [修复] 列 '{col}' 含千分位逗号，已转为数值类型")

    # -- 缺失值处理：数值型填0（无征信数据的客户特征填0） --
    numeric_cols = [c for c in df_base.select_dtypes(include=[np.number]).columns if c not in [COL_CUSTOMER_ID, COL_TARGET]]
    if numeric_cols:
        missing_counts = df_base[numeric_cols].isna().sum()
        missing_cols = missing_counts[missing_counts > 0].index.tolist()
        if missing_cols:
            df_base[missing_cols] = df_base[missing_cols].fillna(0)
            fill_count = missing_counts[missing_cols].sum()
        else:
            fill_count = 0
    else:
        fill_count = 0
    summary['填充缺失值数'] = int(fill_count)

    print(f"\n合并后数据形状: {df_base.shape}")
    print(f"总样本: {summary['客户总数(总样本)']}, "
          f"坏客户: {summary['坏客户数']}"
          f" (坏客户率: {summary['坏客户率']:.4f})")

    return df_base, summary


# =============================================================================
# Section 2: 特征工程
# =============================================================================

def create_credit_features(df):
    """
    构建征信衍生特征（比值/占比型，消除规模影响）

    设计原则：
    1. 消除企业规模影响，使大小企业可比
    2. 提取行为逻辑，反映融资行为模式
    3. 避免除零错误，使用安全除法
    """
    df = df.copy()

    # 辅助变量（避免除零）
    total_org = df['总机构数'].replace(0, 1)
    bank_org = df['银行授信机构数'].replace(0, 1)
    unsettled_org = df['信贷交易未结清总机构数'].replace(0, 1)

    # -- 结构占比类 --
    df['非银机构占比'] = safe_divide(df['非银授信机构数'], total_org)
    df['银行机构占比'] = safe_divide(df['银行授信机构数'], total_org)
    df['小贷公司占比'] = safe_divide(df['小额贷款公司数'], total_org)
    df['消金公司占比'] = safe_divide(df['消费金融公司数'], total_org)
    df['未结清机构占比'] = safe_divide(df['信贷交易未结清总机构数'], total_org)

    # -- 渠道风险特征 --
    df['高风险渠道数'] = df['小额贷款公司数'] + df['消费金融公司数']
    df['高风险渠道占比'] = safe_divide(df['高风险渠道数'], total_org)
    df['是否有高风险渠道'] = (df['高风险渠道数'] > 0).astype(int)
    df['非银银行比例'] = safe_divide(df['非银授信机构数'], bank_org)

    # -- 行为指标类 --
    df['授信分散度'] = np.log1p(df['总机构数'])

    # -- 效率比值类（核心衍生指标）--
    # 业务含义：每个未结清机构平均产生的担保查询次数，反映融资尝试效率
    df['担保查询未结清比'] = safe_divide(df['担保人征信查询次数'], unsettled_org)
    df['担保查询机构比'] = safe_divide(df['担保人征信查询次数'], total_org)

    # -- 交叉特征 --
    df['高风险未结清交叉'] = df['高风险渠道数'] * df['信贷交易未结清总机构数']

    # -- 缩尾处理 (Winsorize) 防止异常极值 --
    ratio_cols = [
        '非银机构占比', '银行机构占比', '小贷公司占比', '消金公司占比',
        '未结清机构占比', '高风险渠道占比', '非银银行比例',
        '担保查询未结清比', '担保查询机构比'
    ]
    for col in ratio_cols:
        if col in df.columns:
            lower = df[col].quantile(0.01)
            upper = df[col].quantile(0.99)
            df[col] = df[col].clip(lower=lower, upper=upper)

    return df


def get_feature_sets(df):
    """
    获取三套特征集（过滤无效特征）

    返回:
        dict: {
            'raw': 原始特征列表,
            'derived': 衍生特征列表,
            'all': 全部特征列表,
            'default': 默认使用的特征列表（衍生）
        }
    """
    def _filter(feat_list):
        return [c for c in feat_list if c in df.columns and df[c].std() > 0]

    raw = _filter(CREDIT_CONFIG['raw_features'])
    derived = _filter(CREDIT_CONFIG['derived_features'])
    all_feats = _filter(CREDIT_CONFIG['raw_features'] + CREDIT_CONFIG['derived_features'])

    return {
        'raw': raw,
        'derived': derived,
        'all': all_feats,
        'default': derived,  # 默认使用衍生特征
    }


# =============================================================================
# Section 3: 分群基础分析
# =============================================================================

def detect_dims(df, category_dims=None, qual_prefix=None):
    """
    自动检测可用的分群维度

    返回:
        category_dims: 有效的类别型维度列表
        qual_dims: 有效的二进制标签维度列表
    """
    if category_dims is None:
        category_dims = _mapper.credit_category_dims
    effective_dims = [
        c for c in category_dims
        if c in df.columns and df[c].notna().sum() > 0
    ]
    qual_dims = _mapper.detect_qual_cols(df.columns, prefix_override=qual_prefix)
    return effective_dims, qual_dims


def data_overview(df, category_dims, qual_dims):
    """
    数据基础摸底：输出全量及各分群维度的概况

    返回:
        overview_df: 概况表
    """
    rows = [{
        '维度': '全量',
        '分群名称': '-',
        '样本数': len(df),
        '坏客户数': int(df[COL_TARGET].sum()),
        '坏客户率': float(df[COL_TARGET].mean()),
    }]

    for dim in category_dims:
        df_v = df[df[dim].notna()]
        for name, grp in df_v.groupby(dim):
            rows.append({
                '维度': dim,
                '分群名称': name,
                '样本数': len(grp),
                '坏客户数': int(grp[COL_TARGET].sum()),
                '坏客户率': float(grp[COL_TARGET].mean()),
            })

    for qc in qual_dims:
        if qc not in df.columns:
            continue
        df_yes = df[df[qc] == 1]
        if len(df_yes) > 0:
            rows.append({
                '维度': '资质标签',
                '分群名称': _mapper.strip_qual_prefix(qc),
                '样本数': len(df_yes),
                '坏客户数': int(df_yes[COL_TARGET].sum()),
                '坏客户率': float(df_yes[COL_TARGET].mean()),
            })

    return pd.DataFrame(rows)


def segment_stats(df, dim_col, min_group_size=None):
    """
    类别型维度的分群统计（按样本数降序，过滤小分群）

    参数:
        df: 数据框
        dim_col: 分群维度列名
        min_group_size: 最小分群样本数，为None则使用配置默认值

    返回:
        stats_df: 分群统计表
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

    # 过滤小分群
    n_before = len(g)
    g = g[g['样本数'] >= min_group_size]
    n_filtered = n_before - len(g)
    if n_filtered > 0:
        print(f"  {dim_col}: 过滤 {n_filtered} 个小分群"
              f"（样本数 < {min_group_size}），保留 {len(g)} 个")

    return g


def qualification_stats(df, qual_cols):
    """
    二进制标签维度的分群统计（有/无资质对比）

    返回:
        stats_df: 资质标签统计表（含坏客户率差异）
    """
    rows = []
    for qc in qual_cols:
        if qc not in df.columns:
            continue
        df_v = df[df[qc].notna()]
        qname = _mapper.strip_qual_prefix(qc)
        for label, subset in [('有该资质', df_v[df_v[qc] == 1]),
                               ('无该资质', df_v[df_v[qc] == 0])]:
            if len(subset) > 0:
                rows.append({
                    '资质类别': qname,
                    '分组': label,
                    '样本数': len(subset),
                    '坏客户数': int(subset[COL_TARGET].sum()),
                    '坏客户率': float(subset[COL_TARGET].mean()),
                })

    if not rows:
        return pd.DataFrame()

    df_out = pd.DataFrame(rows)
    # 计算有/无资质的坏客户率差异
    pivot = df_out.pivot_table(
        index='资质类别', columns='分组', values='坏客户率', aggfunc='first'
    )
    if '有该资质' in pivot.columns and '无该资质' in pivot.columns:
        pivot['坏客户率差异'] = pivot['有该资质'] - pivot['无该资质']

    return df_out, pivot


# =============================================================================
# Section 4: 单变量风险分析
# =============================================================================

def _univariate_single_group(group_df, feature_cols):
    """单个分群的单变量分析"""
    corr_row, diff_row, pval_row = {}, {}, {}
    for feat in feature_cols:
        if feat not in group_df.columns:
            continue
        feat_data = group_df[feat].fillna(0)

        # 相关系数（点二列相关）
        corr_row[feat] = (
            feat_data.corr(group_df[COL_TARGET]) if feat_data.std() > 0 else 0.0
        )

        # 好坏客户均值差异
        m_bad = group_df.loc[group_df[COL_TARGET] == 1, feat].mean()
        m_good = group_df.loc[group_df[COL_TARGET] == 0, feat].mean()
        diff_row[feat] = m_bad - m_good if pd.notna(m_bad) and pd.notna(m_good) else 0.0

        # Welch's t检验
        bad_vals = group_df.loc[group_df[COL_TARGET] == 1, feat].dropna()
        good_vals = group_df.loc[group_df[COL_TARGET] == 0, feat].dropna()
        if len(bad_vals) > 1 and len(good_vals) > 1:
            try:
                _, p = stats.ttest_ind(bad_vals, good_vals, equal_var=False)
                pval_row[feat] = p
            except Exception:
                pval_row[feat] = 1.0
        else:
            pval_row[feat] = 1.0

    return corr_row, diff_row, pval_row


def univariate_by_group(df, dim_col, feature_cols,
                        min_bad=None, min_good=None, min_group_size=None):
    """
    按类别型维度进行分群单变量分析

    参数:
        df: 数据框
        dim_col: 分群维度列名
        feature_cols: 特征列表
        min_bad: 最小坏客户数（默认从配置读取）
        min_good: 最小好客户数（默认从配置读取）
        min_group_size: 最小分群样本数

    返回:
        corr_df: 相关系数矩阵 (分群 x 特征)
        diff_df: 均值差异矩阵
        pval_df: P值矩阵
        meta_df: 分群元信息（样本数、坏客户数、坏客户率）
        skipped: 跳过的分群列表
    """
    if min_bad is None:
        min_bad = _T['MIN_BAD_CORR']
    if min_good is None:
        min_good = _T['MIN_GOOD_CORR']
    if min_group_size is None:
        min_group_size = _T['MIN_SAMPLES']

    # -- 样本概况输出 --
    _print_sample_summary(df, label=f'单变量分析({dim_col}) - 输入全量')
    df_v = df[df[dim_col].notna()]
    _print_sample_summary(df_v, label=f'剔除{dim_col}为空后')

    corr_dict, diff_dict, pval_dict, meta_rows = {}, {}, {}, []
    skipped = []
    analyzed = []

    for gname, gdf in df_v.groupby(dim_col):
        n_total = len(gdf)
        n_bad = int(gdf[COL_TARGET].sum())
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

        c, d, p = _univariate_single_group(gdf, feature_cols)
        corr_dict[gname] = c
        diff_dict[gname] = d
        pval_dict[gname] = p
        meta_rows.append({
            '分群名称': gname, '样本数': n_total,
            '坏客户数': n_bad, '坏客户率': n_bad / n_total,
        })
        analyzed.append({'分群名称': gname, '样本数': n_total, '坏客户数': n_bad})

    _print_group_table(
        analyzed, skipped, '单变量分析',
        thresholds={'总样本': min_group_size, '坏客户': min_bad, '好客户': min_good},
    )
    if skipped:
        print(f"\n  [{dim_col}] 跳过 {len(skipped)} 个分群:")
        for s in skipped:
            print(f"    - {s}")

    corr_df = pd.DataFrame(corr_dict).T
    diff_df = pd.DataFrame(diff_dict).T
    pval_df = pd.DataFrame(pval_dict).T
    meta_df = pd.DataFrame(meta_rows).set_index('分群名称') if meta_rows else pd.DataFrame()

    # 按样本数降序排列
    if not meta_df.empty:
        order = meta_df.sort_values('样本数', ascending=False).index
        corr_df = corr_df.reindex([i for i in order if i in corr_df.index])
        diff_df = diff_df.reindex([i for i in order if i in diff_df.index])
        pval_df = pval_df.reindex([i for i in order if i in pval_df.index])

    return corr_df, diff_df, pval_df, meta_df, skipped


def univariate_by_qualification(df, qual_cols, feature_cols,
                                min_bad=None, min_good=None):
    """
    按二进制标签维度进行分群单变量分析
    （只分析有该资质的客户群体）

    返回:
        corr_df: 相关系数矩阵 (资质类型 x 特征)
        pval_df: P值矩阵
        meta_df: 元信息
        skipped: 跳过列表
    """
    if min_bad is None:
        min_bad = _T['MIN_BAD_CORR']
    if min_good is None:
        min_good = _T['MIN_GOOD_CORR']

    # -- 样本概况输出 --
    _print_sample_summary(df, label='单变量分析(资质标签) - 输入全量')

    corr_dict, pval_dict, meta_rows = {}, {}, []
    skipped = []
    analyzed = []

    for qc in qual_cols:
        if qc not in df.columns:
            continue
        df_yes = df[df[qc] == 1]
        qname = _mapper.strip_qual_prefix(qc)
        n_bad = int(df_yes[COL_TARGET].sum())
        n_good = len(df_yes) - n_bad

        if n_bad < min_bad:
            skipped.append(f"{qname}: 坏客户数={n_bad} < {min_bad}")
            continue
        if n_good < min_good:
            skipped.append(f"{qname}: 好客户数={n_good} < {min_good}")
            continue

        c, _, p = _univariate_single_group(df_yes, feature_cols)
        corr_dict[qname] = c
        pval_dict[qname] = p
        meta_rows.append({
            '分群名称': qname, '样本数': len(df_yes),
            '坏客户数': n_bad, '坏客户率': n_bad / len(df_yes),
        })
        analyzed.append({'分群名称': qname, '样本数': len(df_yes), '坏客户数': n_bad})

    _print_group_table(
        analyzed, skipped, '单变量分析(资质标签)',
        thresholds={'坏客户': min_bad, '好客户': min_good},
    )
    if skipped:
        print(f"\n  [资质标签] 跳过 {len(skipped)} 个分群:")
        for s in skipped:
            print(f"    - {s}")

    corr_df = pd.DataFrame(corr_dict).T
    pval_df = pd.DataFrame(pval_dict).T
    meta_df = pd.DataFrame(meta_rows).set_index('分群名称') if meta_rows else pd.DataFrame()

    return corr_df, pval_df, meta_df, skipped


def cross_group_variance(corr_results):
    """
    跨分群特征风险贡献差异分析

    识别哪些特征在不同分群下的风险贡献差异最大，
    这些特征可能需要分群差异化建模。

    参数:
        corr_results: dict, {维度名: corr_df}

    返回:
        variance_df: 各特征在各维度下的相关系数统计
        feat_summary: 特征一致性汇总
    """
    rows = []
    for dim_name, corr_df in corr_results.items():
        if corr_df is None or corr_df.empty:
            continue
        for feat in corr_df.columns:
            vals = corr_df[feat].dropna()
            if len(vals) > 1:
                rows.append({
                    '分群维度': dim_name, '特征': feat,
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


# =============================================================================
# Section 5: 多变量逻辑回归分析
# =============================================================================

def _fit_lr_single(X_scaled, y, feature_names, n_samples, n_bad):
    """
    拟合单个逻辑回归模型并计算AUC

    关键合规项：
    - 样本 >= 200 且坏客户 >= 30 时，使用5折交叉验证AUC
    - 否则使用训练集AUC（标注类型）
    """
    model = LogisticRegression(
        penalty='l2', C=1.0, solver='lbfgs', max_iter=1000, random_state=42
    )
    model.fit(X_scaled, y)

    coef_dict = dict(zip(feature_names, model.coef_[0]))

    # AUC评估：优先使用交叉验证
    if n_samples >= _T['MIN_SAMPLES_CV'] and n_bad >= _T['MIN_BAD_CV']:
        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
        try:
            cv_scores = cross_val_score(
                model, X_scaled, y, cv=cv, scoring='roc_auc'
            )
            auc_val = float(cv_scores.mean())
            auc_type = '5折交叉验证'
        except Exception:
            y_prob = model.predict_proba(X_scaled)[:, 1]
            auc_val = float(roc_auc_score(y, y_prob))
            auc_type = '训练集(CV失败)'
    else:
        y_prob = model.predict_proba(X_scaled)[:, 1]
        try:
            auc_val = float(roc_auc_score(y, y_prob))
        except Exception:
            auc_val = np.nan
        auc_type = '训练集(样本不足)'

    return coef_dict, auc_val, auc_type


def lr_by_group(df, dim_col, feature_cols,
                min_bad=None, min_good=None, min_group_size=None):
    """
    按类别型维度进行分群逻辑回归分析

    技术说明：
    - L2正则化：抑制共线性导致的系数不稳定
    - StandardScaler：标准化后系数可直接比较大小
    - 交叉验证AUC：样本充足时使用，避免高估模型性能

    返回:
        coef_df: 标准化系数矩阵 (分群 x 特征)
        auc_df: AUC及样本信息
        skipped: 跳过的分群列表
    """
    if min_bad is None:
        min_bad = _T['MIN_BAD_LR']
    if min_good is None:
        min_good = _T['MIN_GOOD_LR']
    if min_group_size is None:
        min_group_size = _T['MIN_SAMPLES']

    # -- 样本概况输出 --
    _print_sample_summary(df, label=f'逻辑回归({dim_col}) - 输入全量')
    df_v = df[df[dim_col].notna()]
    _print_sample_summary(df_v, label=f'剔除{dim_col}为空后')

    coef_dict, auc_rows = {}, []
    skipped = []
    analyzed = []

    valid_feats = [f for f in feature_cols if f in df_v.columns]

    for gname, gdf in df_v.groupby(dim_col):
        n_total = len(gdf)
        n_bad = int(gdf[COL_TARGET].sum())
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

        X = gdf[valid_feats].fillna(0)
        y = gdf[COL_TARGET]
        nz = [c for c in X.columns if X[c].std() > 0]
        if len(nz) < 2:
            skipped.append(f"{gname}: 有效特征数不足")
            continue
        X = X[nz]

        try:
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)
            coefs, auc_val, auc_type = _fit_lr_single(
                X_scaled, y, nz, n_total, n_bad
            )
            coef_dict[gname] = coefs
            auc_rows.append({
                '分群名称': gname, 'AUC': auc_val, 'AUC类型': auc_type,
                '样本数': n_total, '坏客户数': n_bad,
                '坏客户率': n_bad / n_total,
            })
            analyzed.append({'分群名称': gname, '样本数': n_total, '坏客户数': n_bad})
        except Exception as e:
            skipped.append(f"{gname}: 模型拟合失败 - {e}")

    _print_group_table(
        analyzed, skipped, '逻辑回归',
        thresholds={'总样本': min_group_size, '坏客户': min_bad, '好客户': min_good},
    )
    if skipped:
        print(f"\n  [{dim_col}] LR跳过 {len(skipped)} 个分群:")
        for s in skipped:
            print(f"    - {s}")

    coef_df = pd.DataFrame(coef_dict).T
    auc_df = pd.DataFrame(auc_rows).set_index('分群名称') if auc_rows else pd.DataFrame()

    # 按样本数排序
    if not auc_df.empty:
        order = auc_df.sort_values('样本数', ascending=False).index
        coef_df = coef_df.reindex([i for i in order if i in coef_df.index])
        auc_df = auc_df.reindex(order)

    return coef_df, auc_df, skipped


def lr_by_qualification(df, qual_cols, feature_cols,
                        min_bad=None, min_good=None):
    """
    按二进制标签维度进行逻辑回归分析
    （只分析有该资质的客户群体）

    返回:
        coef_df, auc_df, skipped
    """
    if min_bad is None:
        min_bad = _T['MIN_BAD_LR']
    if min_good is None:
        min_good = _T['MIN_GOOD_LR']

    # -- 样本概况输出 --
    _print_sample_summary(df, label='逻辑回归(资质标签) - 输入全量')

    valid_feats = [f for f in feature_cols if f in df.columns]
    coef_dict, auc_rows = {}, []
    skipped = []
    analyzed = []

    for qc in qual_cols:
        if qc not in df.columns:
            continue
        df_yes = df[df[qc] == 1]
        qname = _mapper.strip_qual_prefix(qc)
        n_bad = int(df_yes[COL_TARGET].sum())
        n_good = len(df_yes) - n_bad

        if n_bad < min_bad:
            skipped.append(f"{qname}: 坏客户数={n_bad} < {min_bad}")
            continue
        if n_good < min_good:
            skipped.append(f"{qname}: 好客户数={n_good} < {min_good}")
            continue

        X = df_yes[valid_feats].fillna(0)
        y = df_yes[COL_TARGET]
        nz = [c for c in X.columns if X[c].std() > 0]
        if len(nz) < 2:
            skipped.append(f"{qname}: 有效特征数不足")
            continue

        try:
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X[nz])
            coefs, auc_val, auc_type = _fit_lr_single(
                X_scaled, y, nz, len(df_yes), n_bad
            )
            coef_dict[qname] = coefs
            auc_rows.append({
                '分群名称': qname, 'AUC': auc_val, 'AUC类型': auc_type,
                '样本数': len(df_yes), '坏客户数': n_bad,
                '坏客户率': n_bad / len(df_yes),
            })
            analyzed.append({'分群名称': qname, '样本数': len(df_yes), '坏客户数': n_bad})
        except Exception as e:
            skipped.append(f"{qname}: 模型拟合失败 - {e}")

    _print_group_table(
        analyzed, skipped, '逻辑回归(资质标签)',
        thresholds={'坏客户': min_bad, '好客户': min_good},
    )
    if skipped:
        print(f"\n  [资质标签] LR跳过 {len(skipped)} 个分群:")
        for s in skipped:
            print(f"    - {s}")

    coef_df = pd.DataFrame(coef_dict).T
    auc_df = pd.DataFrame(auc_rows).set_index('分群名称') if auc_rows else pd.DataFrame()
    return coef_df, auc_df, skipped


def compare_corr_lr(corr_df, lr_coef_df):
    """
    对比相关系数与逻辑回归系数

    识别：
    - 稳健特征：两种方法都显示重要
    - 冗余特征：相关系数高但LR系数低（被其他特征解释）
    - 抑制变量：相关系数低但LR系数高（控制其他变量后才显现）

    返回:
        comparison_df: 对比结果
    """
    if corr_df is None or lr_coef_df is None or corr_df.empty or lr_coef_df.empty:
        return pd.DataFrame()

    common_groups = list(set(corr_df.index) & set(lr_coef_df.index))
    common_feats = list(set(corr_df.columns) & set(lr_coef_df.columns))
    if not common_groups or not common_feats:
        return pd.DataFrame()

    corr_mean = corr_df.loc[common_groups, common_feats].mean()
    lr_mean = lr_coef_df.loc[common_groups, common_feats].mean()

    comp = pd.DataFrame({
        '平均相关系数': corr_mean,
        '平均LR系数': lr_mean,
        '|相关系数|': corr_mean.abs(),
        '|LR系数|': lr_mean.abs(),
    })

    condlist = [
        (comp['|相关系数|'] > 0.05) & (comp['|LR系数|'] > 0.1),
        (comp['|相关系数|'] > 0.05) & (comp['|LR系数|'] <= 0.1),
        (comp['|相关系数|'] <= 0.05) & (comp['|LR系数|'] > 0.1)
    ]
    choicelist = ['稳健特征', '冗余特征', '抑制变量']
    comp['特征类型'] = np.select(condlist, choicelist, default='弱相关')
    return comp.sort_values('|LR系数|', ascending=False)


# =============================================================================
# Section 6: IV值分析
# =============================================================================

def iv_full_analysis(df, feature_cols, target=COL_TARGET):
    """
    全量数据IV值分析（使用自适应分箱 + WOE截断 + 可信度评估）

    返回:
        iv_df: IV分析结果表
    """
    _print_sample_summary(df, label='IV全量分析 - 输入样本', target=target)
    print(f"  分析特征数: {len(feature_cols)}")

    rows = []
    raw_set = set(CREDIT_CONFIG['raw_features'])

    for feat in feature_cols:
        if feat not in df.columns:
            continue
        iv_val, meta = _calc_iv_base(df, feat, target)
        if meta:
            reliability = _assess_iv_reliability(
                iv_val, meta['n_samples'], meta['n_bad'], meta['n_bins_actual']
            )
        else:
            reliability = '无法计算'

        if pd.isna(iv_val):
            level = '无法计算'
        elif iv_val < 0.02:
            level = '无预测能力'
        elif iv_val < 0.1:
            level = '弱'
        elif iv_val < 0.3:
            level = '中等'
        elif iv_val < 0.5:
            level = '强'
        else:
            level = '过强'

        rows.append({
            '特征名称': feat,
            '特征类型': '原始' if feat in raw_set else '衍生',
            'IV值': iv_val,
            '预测能力': level,
            'IV可信度': reliability,
            '总样本数': len(df),
            '总坏客户数': int(df[target].sum()),
        })

    return pd.DataFrame(rows).sort_values('IV值', ascending=False, na_position='last')


def iv_by_group(df, dim_col, feature_cols, target=COL_TARGET,
                min_bad=None, min_samples=None):
    """
    按类别型维度的分群IV值分析

    返回:
        iv_results: 各分群各特征的IV值明细表
    """
    if min_bad is None:
        min_bad = _T['MIN_BAD_SAMPLES']
    if min_samples is None:
        min_samples = _T['MIN_SAMPLES']

    # -- 样本概况输出 --
    _print_sample_summary(df, label=f'IV分群分析({dim_col}) - 输入全量', target=target)
    df_v = df[df[dim_col].notna()]
    _print_sample_summary(df_v, label=f'剔除{dim_col}为空后', target=target)

    rows = []
    skipped = []
    analyzed = []

    for gname, gdf in df_v.groupby(dim_col):
        n_total = len(gdf)
        n_bad = int(gdf[target].sum())
        if n_total < min_samples:
            skipped.append(f"{gname}: 总样本={n_total}")
            continue
        if n_bad < min_bad:
            skipped.append(f"{gname}: 坏客户={n_bad}")
            continue

        analyzed.append({'分群名称': gname, '样本数': n_total, '坏客户数': n_bad})

        for feat in feature_cols:
            if feat not in gdf.columns:
                continue
            iv_val, meta = _calc_iv_base(gdf, feat, target)
            if meta:
                reliability = _assess_iv_reliability(
                    iv_val, meta['n_samples'], meta['n_bad'], meta['n_bins_actual']
                )
            else:
                reliability = '无法计算'

            rows.append({
                '分群维度': dim_col, '分群名称': gname,
                '样本数': n_total, '坏客户数': n_bad,
                '坏客户率': n_bad / n_total,
                '特征': feat, 'IV值': iv_val,
                'IV可信度': reliability,
            })

    _print_group_table(
        analyzed, skipped, 'IV分析',
        thresholds={'总样本': min_samples, '坏客户': min_bad},
    )
    if skipped:
        print(f"  [{dim_col}] IV跳过 {len(skipped)} 个分群:")
        for s in skipped[:5]:
            print(f"    - {s}")
        if len(skipped) > 5:
            print(f"    ... 共 {len(skipped)} 个")

    return pd.DataFrame(rows)


def iv_by_qualification(df, qual_cols, feature_cols, target=COL_TARGET,
                        min_bad=None, min_samples=None):
    """
    按二进制标签维度的IV值分析

    返回:
        iv_results: IV值明细表
    """
    if min_bad is None:
        min_bad = _T['MIN_BAD_SAMPLES']
    if min_samples is None:
        min_samples = _T['MIN_SAMPLES']

    # -- 样本概况输出 --
    _print_sample_summary(df, label='IV分群分析(资质标签) - 输入全量', target=target)

    rows = []
    analyzed = []
    skipped = []

    for qc in qual_cols:
        if qc not in df.columns:
            continue
        df_yes = df[df[qc] == 1]
        qname = _mapper.strip_qual_prefix(qc)
        n_total = len(df_yes)
        n_bad = int(df_yes[target].sum())

        if n_total < min_samples or n_bad < min_bad:
            reason = []
            if n_total < min_samples:
                reason.append(f'总样本={n_total}<{min_samples}')
            if n_bad < min_bad:
                reason.append(f'坏客户={n_bad}<{min_bad}')
            skipped.append(f"{qname}: {', '.join(reason)}")
            continue

        analyzed.append({'分群名称': qname, '样本数': n_total, '坏客户数': n_bad})

        for feat in feature_cols:
            if feat not in df_yes.columns:
                continue
            iv_val, meta = _calc_iv_base(df_yes, feat, target)
            if meta:
                reliability = _assess_iv_reliability(
                    iv_val, meta['n_samples'], meta['n_bad'], meta['n_bins_actual']
                )
            else:
                reliability = '无法计算'
            rows.append({
                '分群维度': '资质标签', '分群名称': qname,
                '样本数': n_total, '坏客户数': n_bad,
                '坏客户率': n_bad / n_total,
                '特征': feat, 'IV值': iv_val,
                'IV可信度': reliability,
            })

    _print_group_table(
        analyzed, skipped, 'IV分析(资质标签)',
        thresholds={'总样本': min_samples, '坏客户': min_bad},
    )

    return pd.DataFrame(rows)


# =============================================================================
# Section 7: 特征集对比
# =============================================================================

def compare_feature_sets(df, dim_col, raw_features, derived_features,
                         min_bad=None, min_good=None):
    """
    对比原始特征集与衍生特征集的AUC表现

    返回:
        comp_df: 各分群的AUC对比表
    """
    if min_bad is None:
        min_bad = _T['MIN_BAD_LR']
    if min_good is None:
        min_good = _T['MIN_GOOD_LR']

    # -- 样本概况输出 --
    _print_sample_summary(df, label=f'特征集对比({dim_col}) - 输入全量')
    df_v = df[df[dim_col].notna()]
    _print_sample_summary(df_v, label=f'剔除{dim_col}为空后')

    rows = []
    analyzed = []
    skipped = []

    for gname, gdf in df_v.groupby(dim_col):
        n_bad = int(gdf[COL_TARGET].sum())
        n_good = len(gdf) - n_bad
        if n_bad < min_bad or n_good < min_good:
            reason = []
            if n_bad < min_bad:
                reason.append(f'坏客户={n_bad}<{min_bad}')
            if n_good < min_good:
                reason.append(f'好客户={n_good}<{min_good}')
            skipped.append(f"{gname}: {', '.join(reason)}")
            continue

        analyzed.append({'分群名称': gname, '样本数': len(gdf), '坏客户数': n_bad})

        y = gdf[COL_TARGET]
        auc_raw, auc_derived = np.nan, np.nan

        for feat_set, label in [(raw_features, 'raw'), (derived_features, 'derived')]:
            X = gdf[[f for f in feat_set if f in gdf.columns]].fillna(0)
            X = X[[c for c in X.columns if X[c].std() > 0]]
            if len(X.columns) < 2:
                continue
            try:
                scaler = StandardScaler()
                Xs = scaler.fit_transform(X)
                mdl = LogisticRegression(
                    penalty='l2', C=1.0, solver='lbfgs',
                    max_iter=1000, random_state=42
                )
                mdl.fit(Xs, y)

                n_total = len(gdf)
                if n_total >= _T['MIN_SAMPLES_CV'] and n_bad >= _T['MIN_BAD_CV']:
                    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
                    auc = float(cross_val_score(
                        mdl, Xs, y, cv=cv, scoring='roc_auc'
                    ).mean())
                else:
                    auc = float(roc_auc_score(y, mdl.predict_proba(Xs)[:, 1]))

                if label == 'raw':
                    auc_raw = auc
                else:
                    auc_derived = auc
            except Exception:
                pass

        diff = (auc_derived - auc_raw
                if pd.notna(auc_raw) and pd.notna(auc_derived) else np.nan)
        rows.append({
            '分群': gname, '样本数': len(gdf), '坏客户数': n_bad,
            '坏客户率': n_bad / len(gdf),
            'AUC_原始特征': auc_raw, 'AUC_衍生特征': auc_derived,
            'AUC差异': diff,
        })

    _print_group_table(
        analyzed, skipped, '特征集对比',
        thresholds={'坏客户': min_bad, '好客户': min_good},
    )

    return pd.DataFrame(rows)


# =============================================================================
# Section 8: 可信度诊断
# =============================================================================

def reliability_diagnosis(all_iv_df):
    """
    构建IV可信度诊断报告

    参数:
        all_iv_df: 包含 'IV可信度' 列的分群IV明细表

    返回:
        summary_df: 分群可信度汇总表
        dist_df: 可信度等级分布
        warnings: 告警信息列表
    """
    if all_iv_df.empty or 'IV可信度' not in all_iv_df.columns:
        return pd.DataFrame(), pd.DataFrame(), []

    # 可信度等级分布
    dist = all_iv_df['IV可信度'].value_counts()
    dist_df = pd.DataFrame({
        '等级': dist.index, '记录数': dist.values,
        '占比%': (dist.values / dist.values.sum() * 100).round(1),
    })

    # 分群可信度汇总
    rows = []
    for (dim, gname), grp in all_iv_df.groupby(['分群维度', '分群名称']):
        n_total = len(grp)
        n_reliable = (grp['IV可信度'] == '可信').sum()
        n_ref = (grp['IV可信度'] == '参考').sum()
        n_unreliable = n_total - n_reliable - n_ref
        rows.append({
            '分群维度': dim, '分群名称': gname,
            '样本数': grp['样本数'].iloc[0] if '样本数' in grp.columns else 0,
            '坏客户数': grp['坏客户数'].iloc[0] if '坏客户数' in grp.columns else 0,
            '特征数': n_total,
            '可信数': n_reliable, '参考数': n_ref, '不可信数': n_unreliable,
            'IV可信率%': round(n_reliable / n_total * 100, 1) if n_total > 0 else 0,
        })

    summary_df = pd.DataFrame(rows)

    # 告警：可信率低于50%的分群
    warn_list = []
    for _, row in summary_df.iterrows():
        if row['IV可信率%'] < 50:
            warn_list.append(
                f"[告警] {row['分群维度']}/{row['分群名称']}: "
                f"IV可信率仅 {row['IV可信率%']}%"
                f" (样本数={row['样本数']}, 坏客户数={row['坏客户数']})"
            )

    return summary_df, dist_df, warn_list


# =============================================================================
# Section 9: 结果导出
# =============================================================================

def export_results(project_root, results, project_name=None, output_subdir=None,
                   results_base=None, output_base=None):
    """
    导出全部分析结果到CSV

    参数:
        project_root:  项目根目录
        results:       dict，包含各步骤分析结果
        project_name:  可选的项目名称前缀，默认使用 CREDIT_CONFIG['project_name']
        output_subdir: 结果目录下的子目录名称，默认使用 timestamp
        results_base:  data/results 级别的相对路径，None → CREDIT_PIPELINE_PATHS['results_rel']
        output_base:   output 级别的相对路径，       None → CREDIT_PIPELINE_PATHS['output_rel']

    返回:
        exported: 导出的文件列表
    """
    from datetime import datetime

    pname = project_name or results.get('project_name') or CREDIT_CONFIG['project_name']
    subdir = output_subdir or results.get('output_subdir') or datetime.now().strftime('%Y%m%d_%H%M')

    _results_base = results_base or CREDIT_PIPELINE_PATHS['results_rel']
    _output_base  = output_base  or CREDIT_PIPELINE_PATHS['output_rel']

    out_dir = os.path.join(project_root, _output_base, subdir)
    res_dir = os.path.join(project_root, _results_base, subdir)
    ensure_dir(out_dir)
    ensure_dir(res_dir)

    exported = []

    def _save(df, filename, directory=res_dir):
        if df is not None and not df.empty:
            path = os.path.join(directory, filename)
            df.to_csv(path, index=False, encoding='utf-8-sig')
            exported.append(filename)
            print(f"  -> {filename} ({len(df)} 行)")

    # 1. 全量IV分析结果
    iv_full = results.get('iv_full')
    if iv_full is not None and not iv_full.empty:
        if '分群' in iv_full.columns:
            iv_full_export = iv_full[iv_full['分群'] == '全量'].copy()
        else:
            iv_full_export = iv_full
        _save(iv_full_export, f'{pname}_IV分析结果.csv')

    # 2. 特征风险相关性（分群相关系数 + 元信息）
    corr_exports = results.get('corr_exports')
    if corr_exports is not None:
        _save(corr_exports, f'{pname}_特征风险相关性.csv')

    # 3. 逻辑回归系数
    lr_exports = results.get('lr_exports')
    if lr_exports is not None:
        _save(lr_exports, f'{pname}_逻辑回归系数.csv')

    # 4. 分群IV值明细
    iv_group = results.get('iv_group_all')
    _save(iv_group, f'{pname}_IV值分析.csv')

    # 5. IV可信度透视表
    if iv_group is not None and not iv_group.empty and '特征' in iv_group.columns:
        try:
            iv_pivot = iv_group.pivot_table(
                index='分群名称', columns='特征', values='IV值', aggfunc='first'
            )
            rel_pivot = iv_group.pivot_table(
                index='分群名称', columns='特征', values='IV可信度', aggfunc='first'
            )
            iv_pivot.to_csv(
                os.path.join(res_dir, f'{pname}_IV值透视表.csv'),
                encoding='utf-8-sig'
            )
            rel_pivot.to_csv(
                os.path.join(res_dir, f'{pname}_IV可信度透视表.csv'),
                encoding='utf-8-sig'
            )
            exported.append(f'{pname}_IV值透视表.csv')
            exported.append(f'{pname}_IV可信度透视表.csv')
        except Exception:
            pass

    # 6. IV可信度诊断 (原分群样本概况)
    _save(results.get('reliability_summary'), f'{pname}_IV可信度诊断.csv')

    # 7. 原始vs衍生特征AUC对比
    comp_all = results.get('feature_set_comparison')
    _save(comp_all, f'{pname}_原始vs衍生特征AUC对比.csv')

    # 8. 综合特征分析结果（输出到 res_dir 与其他保持一致）
    _save(results.get('comprehensive'), f'{pname}_综合特征分析结果.csv')

    # 9. LLM报告数据（JSON + CSV，输出到out_dir）
    llm_data = results.get('llm_report_data')
    if llm_data is not None:
        try:
            json_path = _export_llm_report_json(project_root, llm_data, out_dir=out_dir, project_name=pname)
            exported.append(os.path.basename(json_path))
            print(f"  -> {os.path.basename(json_path)} (LLM报告数据-JSON)")

            # 同时导出两个CSV供直接查看
            feat_df = llm_data.get('feature_summary')
            if feat_df is not None and not feat_df.empty:
                _save(feat_df, f'{pname}_LLM_特征有效性汇总.csv', directory=out_dir)
            seg_df = llm_data.get('segment_profiles')
            if seg_df is not None and not seg_df.empty:
                _save(seg_df, f'{pname}_LLM_分群画像.csv', directory=out_dir)
        except Exception as e:
            print(f"  [警告] LLM报告数据导出失败: {e}")

    return exported


def build_comprehensive_table(iv_full_df, corr_results, lr_coef_results,
                              iv_group_all, raw_features=None, derived_features=None):
    """
    构建综合特征分析汇总表

    参数:
        iv_full_df: 全量IV结果
        corr_results: {dim: corr_df} 各维度相关系数
        lr_coef_results: {dim: coef_df} 各维度LR系数
        iv_group_all: 全部分群IV明细

    返回:
        df_comp: 综合汇总表
    """
    if iv_full_df is None or iv_full_df.empty:
        return pd.DataFrame()

    # 兼容 run_iv_analysis 输出（列名为 '特征'/'分群'）
    _full = iv_full_df
    if '分群' in _full.columns:
        _full = _full[_full['分群'] == '全量']
    feat_col = '特征名称' if '特征名称' in _full.columns else '特征'

    base_cols = [feat_col, 'IV值', 'IV可信度']
    if '特征类型' in _full.columns:
        base_cols.insert(1, '特征类型')
    df = _full[base_cols].copy()
    df = df.rename(columns={feat_col: '特征名称', 'IV值': 'iv_all'})

    if raw_features or derived_features:
        raw_set = set(raw_features or [])
        der_set = set(derived_features or [])
        def _feat_type(name):
            if name in raw_set:   return '原始'
            if name in der_set:   return '衍生'
            return ''
        df['特征类型'] = df['特征名称'].apply(_feat_type)

    # 衍生预测能力标签
    def _iv_power(v):
        if v >= 0.3:
            return '强'
        if v >= 0.1:
            return '中'
        if v >= 0.02:
            return '弱'
        return '无'

    if '预测能力' not in df.columns:
        df['预测能力'] = df['iv_all'].apply(_iv_power)

    # 添加全量相关系数
    for dim_name, corr_df in corr_results.items():
        if corr_df is not None and not corr_df.empty:
            mean_corr = corr_df.mean()
            df[f'corr_{dim_name}'] = df['特征名称'].map(mean_corr)

    # 添加LR系数均值
    all_coefs = []
    for coef_df in lr_coef_results.values():
        if coef_df is not None and not coef_df.empty:
            all_coefs.append(coef_df)
    if all_coefs:
        combined = pd.concat(all_coefs)
        lr_mean = combined.mean()
        df['lr_coef_mean'] = df['特征名称'].map(lr_mean)

    # 添加各维度IV均值
    if iv_group_all is not None and not iv_group_all.empty:
        feat_col_g = '特征' if '特征' in iv_group_all.columns else '特征名称'
        for dim_name in iv_group_all['分群维度'].unique():
            dim_iv = iv_group_all[iv_group_all['分群维度'] == dim_name]
            iv_mean = dim_iv.groupby(feat_col_g)['IV值'].mean()
            df[f'iv_{dim_name}'] = df['特征名称'].map(iv_mean)

    df = df.sort_values('iv_all', ascending=False, na_position='last')
    return df


def build_llm_report_data(df, iv_full_df, corr_results, meta_results,
                          lr_coef_results, lr_auc_results,
                          iv_group_all, rel_summary, rel_warnings,
                          comp_all, feature_cols, category_dims, qual_dims,
                          raw_features=None, derived_features=None, target_col=COL_TARGET):
    """
    构建面向LLM报告生成的三层结构化数据

    将分散的分析结果提炼为：
      第1层 - 分析概览（overview）：全局元信息，供LLM写报告开头
      第2层 - 特征有效性汇总（feature_summary）：每个特征一行，集成IV/相关性/LR/稳定性
      第3层 - 分群画像（segment_profiles）：每个分群一行，含样本概况+模型表现+关键特征

    参数:
        df: 宽表原始数据（用于提取全局统计）
        iv_full_df: 全量IV分析结果
        corr_results: {dim: corr_df} 各维度相关系数
        meta_results: {dim: meta_df} 各维度样本元信息
        lr_coef_results: {dim: coef_df} 各维度LR系数
        lr_auc_results: {dim: auc_df} 各维度AUC
        iv_group_all: 分群IV明细 DataFrame
        rel_summary: 分群可信度汇总 DataFrame
        rel_warnings: 可信度告警列表
        comp_all: 原始vs衍生特征AUC对比 DataFrame
        feature_cols: 当前使用的特征列表
        category_dims: 类别型分群维度列表
        qual_dims: 资质标签维度列表

    返回:
        dict: {
            'overview': dict,  # 分析概览
            'feature_summary': pd.DataFrame,  # 特征有效性汇总
            'segment_profiles': pd.DataFrame,  # 分群画像
        }
    """
    total = len(df)
    bad = int(df[target_col].sum())
    bad_rate = round(bad / total, 4) if total > 0 else 0

    # 标准化 iv_full_df：兼容 run_iv_analysis 输出（列名为 '特征'/'分群'）
    if iv_full_df is not None and not iv_full_df.empty:
        if '分群' in iv_full_df.columns:
            iv_full_df = iv_full_df[iv_full_df['分群'] == '全量'].copy()
        if '特征' in iv_full_df.columns and '特征名称' not in iv_full_df.columns:
            iv_full_df = iv_full_df.rename(columns={'特征': '特征名称'})
        if '预测能力' not in iv_full_df.columns:
            def _iv_power(v):
                if v >= 0.3: return '强'
                if v >= 0.1: return '中'
                if v >= 0.02: return '弱'
                return '无'
            iv_full_df['预测能力'] = iv_full_df['IV值'].apply(_iv_power)

    # ==================================================================
    # 第1层：分析概览
    # ==================================================================
    # 统计参与分析的分群数 & 可信分群数
    n_segments = 0
    n_reliable_segments = 0
    if rel_summary is not None and not rel_summary.empty:
        n_segments = len(rel_summary)
        n_reliable_segments = int((rel_summary['IV可信率%'] >= 50).sum())

    overview = {
        '数据概况': {
            '总样本数': total,
            '坏客户数': bad,
            '坏客户率': bad_rate,
        },
        '分群维度': {
            '类别型维度': category_dims,
            '类别型维度数量': len(category_dims),
            '资质标签维度': [_mapper.strip_qual_prefix(q) for q in qual_dims],
            '资质标签维度数量': len(qual_dims),
        },
        '特征集': {
            '当前分析特征': feature_cols,
            '特征数量': len(feature_cols),
        },
        '分析范围': {
            '参与分析的分群总数': n_segments,
            'IV可信率>=50%的分群数': n_reliable_segments,
            'IV可信率<50%的分群数': n_segments - n_reliable_segments,
        },
        '可信度告警': rel_warnings if rel_warnings else [],
    }

    # ==================================================================
    # 第2层：特征有效性汇总（每个特征一行）
    # ==================================================================
    feat_rows = []

    # -- 全局IV数据
    iv_map = {}
    iv_power_map = {}
    iv_rel_map = {}
    iv_type_map = {}
    
    raw_set = set(raw_features or [])
    der_set = set(derived_features or [])
    
    if iv_full_df is not None and not iv_full_df.empty:
        for _, r in iv_full_df.iterrows():
            fname = r['特征名称']
            iv_map[fname] = r['IV值']
            iv_power_map[fname] = r['预测能力']
            iv_rel_map[fname] = r['IV可信度']
            iv_type_map[fname] = '原始' if fname in raw_set else ('衍生' if fname in der_set else r.get('特征类型', ''))

    # -- 跨分群相关系数统计（仅用可信分群）
    # 收集所有可信分群名称
    reliable_groups = set()
    if rel_summary is not None and not rel_summary.empty:
        reliable_mask = rel_summary['IV可信率%'] >= 50
        reliable_groups = set(rel_summary.loc[reliable_mask, '分群名称'])

    def _reliable_stats(corr_results_dict):
        """计算可信分群下各特征的相关系数统计"""
        feat_vals = {}  # {feat: [values]}
        for dim_name, corr_df in corr_results_dict.items():
            if corr_df is None or corr_df.empty:
                continue
            for feat in corr_df.columns:
                if feat not in feat_vals:
                    feat_vals[feat] = []
                for grp_name, val in corr_df[feat].items():
                    if pd.notna(val) and grp_name in reliable_groups:
                        feat_vals[feat].append(val)
        result = {}
        for feat, vals in feat_vals.items():
            if vals:
                arr = np.array(vals)
                
                # 调整方向一致性评级：引入容忍度阈值 (≥ 80%)，并忽略接近零的相关系数
                signs = np.sign(arr[np.abs(arr) > 0.02])
                if len(signs) >= 3:
                    dominant = np.sum(signs > 0) / len(signs)
                    sign_consistent = bool(dominant >= 0.8 or dominant <= 0.2)
                else:
                    sign_consistent = bool(np.all(arr > 0) or np.all(arr < 0))
                
                result[feat] = {
                    'mean': float(np.mean(arr)),
                    'std': float(np.std(arr)),
                    'range': float(np.max(arr) - np.min(arr)),
                    'n_groups': len(arr),
                    'sign_consistent': sign_consistent,
                }
        return result

    corr_stats = _reliable_stats(corr_results)

    # -- 跨分群LR系数统计（仅用可信分群）
    lr_feat_vals = {}
    for dim_name, coef_df in lr_coef_results.items():
        if coef_df is None or coef_df.empty:
            continue
        for feat in coef_df.columns:
            if feat not in lr_feat_vals:
                lr_feat_vals[feat] = []
            for grp_name, val in coef_df[feat].items():
                if pd.notna(val) and grp_name in reliable_groups:
                    lr_feat_vals[feat].append(val)
    lr_stats = {}
    for feat, vals in lr_feat_vals.items():
        if vals:
            arr = np.array(vals)
            lr_stats[feat] = {
                'mean': float(np.mean(arr)),
                'std': float(np.std(arr)),
            }

    # -- 综合评级逻辑
    def _rate_feature(iv_val, corr_mean, corr_range, sign_consistent):
        """
        综合评级规则：
        - 核心特征：全局IV >= 0.2 且跨分群方向一致
        - 重要特征：全局IV >= 0.1 或跨分群相关性均值绝对值 >= 0.05
        - 辅助特征：全局IV 0.02~0.1
        - 无效特征：全局IV < 0.02
        """
        if iv_val >= 0.2 and sign_consistent:
            return '核心特征'
        if iv_val >= 0.2:
            return '重要特征'
        if iv_val >= 0.1:
            return '重要特征'
        if iv_val >= 0.02 or (corr_mean is not None and abs(corr_mean) >= 0.05):
            return '辅助特征'
        return '无效特征'

    # -- 跨分群一致性评级
    def _consistency_level(corr_range, sign_consistent):
        if sign_consistent:
            return '高'
        if corr_range is not None and corr_range < 0.2:
            return '中'
        if corr_range is not None and corr_range < 0.4:
            return '低'
        return '低'

    # -- 汇总每个特征
    all_features = list(iv_map.keys()) if iv_map else feature_cols
    for feat in all_features:
        iv_val = iv_map.get(feat, 0)
        cs = corr_stats.get(feat, {})
        ls = lr_stats.get(feat, {})

        corr_mean = cs.get('mean')
        corr_range = cs.get('range')
        sign_consistent = cs.get('sign_consistent', False)

        row = {
            '特征名称': feat,
            '特征类型': iv_type_map.get(feat, ''),
            '全局IV': round(iv_val, 4),
            'IV预测力': iv_power_map.get(feat, ''),
            'IV可信度': iv_rel_map.get(feat, ''),
            '可信分群平均相关系数': round(corr_mean, 4) if corr_mean is not None else None,
            '可信分群相关系数极差': round(corr_range, 4) if corr_range is not None else None,
            '可信分群分析数': cs.get('n_groups', 0),
            '跨分群方向一致': sign_consistent,
            '跨分群一致性': _consistency_level(corr_range, sign_consistent),
            '可信分群平均LR系数': round(ls.get('mean', 0), 4) if ls else None,
            '综合评级': _rate_feature(iv_val, corr_mean, corr_range, sign_consistent),
        }
        feat_rows.append(row)

    feature_summary = pd.DataFrame(feat_rows)
    if not feature_summary.empty:
        # 按综合评级排序：核心 > 重要 > 辅助 > 无效，同级按IV降序
        rating_order = {'核心特征': 0, '重要特征': 1, '辅助特征': 2, '无效特征': 3}
        feature_summary['_sort'] = feature_summary['综合评级'].map(rating_order)
        feature_summary = feature_summary.sort_values(
            ['_sort', '全局IV'], ascending=[True, False]
        ).drop(columns='_sort').reset_index(drop=True)

    # ==================================================================
    # 第3层：分群画像（每个分群一行）
    # ==================================================================
    seg_rows = []

    # 收集所有分群的 (dim, grp_name) -> 各项数据
    # 3a. 从 meta_results 获取分群样本概况
    seg_meta = {}
    for dim_name, meta_df in meta_results.items():
        if meta_df is None or meta_df.empty:
            continue
        for grp_name in meta_df.index:
            key = (dim_name, grp_name)
            row_data = meta_df.loc[grp_name]
            seg_meta[key] = {
                '样本数': int(row_data.get('样本数', 0)) if '样本数' in row_data.index else 0,
                '坏客户数': int(row_data.get('坏客户数', 0)) if '坏客户数' in row_data.index else 0,
                '坏客户率': round(float(row_data.get('坏客户率', 0)), 4) if '坏客户率' in row_data.index else 0,
            }

    # 3a-补充. 从 rel_summary 回填 meta_results 中缺失的分群样本信息
    # （部分分群因样本不足被单变量分析跳过，但IV分析仍有记录）
    if rel_summary is not None and not rel_summary.empty:
        for _, r in rel_summary.iterrows():
            key = (r['分群维度'], r['分群名称'])
            if key not in seg_meta:
                seg_meta[key] = {
                    '样本数': int(r['样本数']),
                    '坏客户数': int(r['坏客户数']),
                    '坏客户率': round(r['坏客户数'] / r['样本数'], 4) if r['样本数'] > 0 else 0,
                }

    # 3b. 从 lr_auc_results 获取模型AUC
    seg_auc = {}
    for dim_name, auc_df in lr_auc_results.items():
        if auc_df is None or auc_df.empty:
            continue
        for grp_name in auc_df.index:
            key = (dim_name, grp_name)
            seg_auc[key] = {
                'AUC': round(float(auc_df.loc[grp_name, 'AUC']), 4) if 'AUC' in auc_df.columns else None,
                'AUC类型': str(auc_df.loc[grp_name, 'AUC类型']) if 'AUC类型' in auc_df.columns else '',
            }

    # 3c. 从 rel_summary 获取IV可信率
    seg_rel = {}
    if rel_summary is not None and not rel_summary.empty:
        for _, r in rel_summary.iterrows():
            key = (r['分群维度'], r['分群名称'])
            seg_rel[key] = float(r['IV可信率%'])

    # 3d. 从 comp_all 获取特征集对比
    seg_comp = {}
    if comp_all is not None and not comp_all.empty:
        dim_col = '分群维度' if '分群维度' in comp_all.columns else None
        # comp_all 可能用 '分群' 或 '分群名称' 作为列名
        grp_col = None
        for candidate in ['分群名称', '分群']:
            if candidate in comp_all.columns:
                grp_col = candidate
                break
        if dim_col and grp_col:
            for _, r in comp_all.iterrows():
                key = (r[dim_col], r[grp_col])
                auc_diff = float(r.get('AUC差异', 0))
                seg_comp[key] = {
                    '特征集优胜': '衍生' if auc_diff > 0 else ('原始' if auc_diff < 0 else '持平'),
                    'AUC差异': round(auc_diff, 4),
                }

    # 3e. 提取 Top3 风险特征（相关系数绝对值最大的3个）
    def _top3_by_corr(dim_name, grp_name, corr_results_dict):
        corr_df = corr_results_dict.get(dim_name)
        if corr_df is None or corr_df.empty or grp_name not in corr_df.index:
            return ''
        row = corr_df.loc[grp_name].dropna()
        if row.empty:
            return ''
        top3 = row.abs().nlargest(3)
        parts = []
        for feat_name in top3.index:
            val = row[feat_name]
            direction = '+' if val > 0 else '-'
            parts.append(f"{feat_name}({direction}{abs(val):.3f})")
        return ', '.join(parts)

    # 3f. 提取 Top3 IV特征
    def _top3_by_iv(dim_name, grp_name, iv_group_all_df):
        if iv_group_all_df is None or iv_group_all_df.empty:
            return ''
        mask = (iv_group_all_df['分群维度'] == dim_name) & \
               (iv_group_all_df['分群名称'] == grp_name) & \
               (iv_group_all_df['IV可信度'] == '可信')
        sub = iv_group_all_df.loc[mask].nlargest(3, 'IV值')
        if sub.empty:
            # 退而求其次取参考级别
            mask2 = (iv_group_all_df['分群维度'] == dim_name) & \
                    (iv_group_all_df['分群名称'] == grp_name)
            sub = iv_group_all_df.loc[mask2].nlargest(3, 'IV值')
        if sub.empty:
            return ''
        parts = [f"{r['特征']}({r['IV值']:.3f})" for _, r in sub.iterrows()]
        return ', '.join(parts)

    # 3g. 生成风险特征概要文本
    def _risk_summary(dim_name, grp_name, n_samples, bad_rate_grp, auc_val,
                      corr_results_dict, lr_coef_results_dict):
        """
        自动生成一句话风险特征概要:
        - 坏客户率 > 全局2倍 => 高风险分群
        - 相关系数+LR系数同向且显著 => 特征描述
        - AUC < 0.6 => 模型区分力有限
        - 无相关性数据 => 标注样本不足
        """
        parts = []

        # 检查是否有相关性分析数据
        corr_df = corr_results_dict.get(dim_name)
        has_corr = (corr_df is not None and grp_name in corr_df.index)

        # 坏客户率对比（仅样本数>0时有意义）
        if n_samples > 0 and bad_rate_grp > 0:
            if bad_rate_grp > bad_rate * 2:
                parts.append(f"坏客户率({bad_rate_grp:.1%})显著高于整体({bad_rate:.1%})")
            elif bad_rate_grp < bad_rate * 0.5:
                parts.append(f"坏客户率({bad_rate_grp:.1%})显著低于整体({bad_rate:.1%})")

        # 模型效果
        if auc_val is not None:
            if auc_val < 0.6:
                parts.append("模型区分力有限")
            elif auc_val >= 0.75:
                parts.append(f"模型区分力较好(AUC={auc_val:.3f})")

        # 关键特征方向（仅在有相关性数据时）
        lr_df = lr_coef_results_dict.get(dim_name)
        if has_corr:
            row_corr = corr_df.loc[grp_name].dropna()
            top_feat = row_corr.abs().nlargest(2)
            corr_added = False
            for fname in top_feat.index:
                cval = row_corr[fname]
                lr_val = None
                if lr_df is not None and grp_name in lr_df.index and fname in lr_df.columns:
                    lr_val = lr_df.loc[grp_name, fname]
                if abs(cval) >= 0.08:
                    direction = '越高风险越高' if cval > 0 else '越高风险越低'
                    stable = ''
                    if lr_val is not None and (cval > 0) == (lr_val > 0):
                        stable = '(稳健)'
                    parts.append(f"{fname}{direction}{stable}")
                    corr_added = True
            if not corr_added:
                max_abs = row_corr.abs().max()
                parts.append(f"特征相关性均较弱（最大|r|={max_abs:.3f}<0.08），无显著线性风险特征")
        elif n_samples > 0:
            parts.append("样本不足，未进行相关性分析")

        return '; '.join(parts) if parts else '数据不足，无法分析'

    # -- 收集所有分群的key
    all_keys = set()
    all_keys.update(seg_meta.keys())
    for dim_name, corr_df in corr_results.items():
        if corr_df is not None:
            for grp_name in corr_df.index:
                all_keys.add((dim_name, grp_name))
    if rel_summary is not None and not rel_summary.empty:
        for _, r in rel_summary.iterrows():
            all_keys.add((r['分群维度'], r['分群名称']))

    for (dim_name, grp_name) in sorted(all_keys):
        meta = seg_meta.get((dim_name, grp_name), {})
        auc_info = seg_auc.get((dim_name, grp_name), {})
        rel_rate = seg_rel.get((dim_name, grp_name))
        comp_info = seg_comp.get((dim_name, grp_name), {})

        n_samples = meta.get('样本数', 0)
        n_bad = meta.get('坏客户数', 0)
        grp_bad_rate = meta.get('坏客户率', 0)
        auc_val = auc_info.get('AUC')

        top3_corr = _top3_by_corr(dim_name, grp_name, corr_results)
        top3_iv = _top3_by_iv(dim_name, grp_name, iv_group_all)
        risk_text = _risk_summary(
            dim_name, grp_name, n_samples, grp_bad_rate, auc_val,
            corr_results, lr_coef_results
        )

        seg_rows.append({
            '分群维度': dim_name,
            '分群名称': grp_name,
            '样本数': n_samples,
            '坏客户数': n_bad,
            '坏客户率': grp_bad_rate,
            '模型AUC': auc_val,
            'AUC类型': auc_info.get('AUC类型', ''),
            'IV可信率%': rel_rate,
            'Top3风险特征_相关性': top3_corr,
            'Top3预测特征_IV': top3_iv,
            '特征集优胜': comp_info.get('特征集优胜', ''),
            '特征集AUC差异': comp_info.get('AUC差异', ''),
            '风险特征概要': risk_text,
        })

    segment_profiles = pd.DataFrame(seg_rows)

    return {
        'overview': overview,
        'feature_summary': feature_summary,
        'segment_profiles': segment_profiles,
    }


def _generate_key_findings(overview, feat_df, seg_df):
    """
    从分析结果中自动提炼核心发现（5-8条），供LLM撰写报告摘要使用。

    提炼维度：最强特征、跨分群稳健性、模型最佳分群、风险异常分群、可信度概况。
    """
    findings = []
    global_bad_rate = overview.get('数据概况', {}).get('坏客户率', 0)

    # -- 特征层面
    if feat_df is not None and not feat_df.empty:
        important = feat_df[feat_df['综合评级'].isin(['核心特征', '重要特征'])]
        n_imp = len(important)
        if n_imp > 0:
            top = important.iloc[0]
            findings.append(
                f"共识别{n_imp}个重要/核心风险特征，"
                f"最强特征'{top['特征名称']}'(全局IV={top['全局IV']:.4f})"
            )
            if '跨分群方向一致' in important.columns:
                consistent = important[important['跨分群方向一致'] == True]
            else:
                consistent = pd.DataFrame()
            if not consistent.empty:
                names = consistent['特征名称'].tolist()[:3]
                findings.append(
                    f"跨分群方向一致的稳健特征: {', '.join(names)}"
                )

    # -- 分群层面
    if seg_df is not None and not seg_df.empty:
        has_auc = seg_df[seg_df['模型AUC'].notna()]
        if not has_auc.empty:
            best = has_auc.loc[has_auc['模型AUC'].idxmax()]
            if best['模型AUC'] >= 0.65:
                findings.append(
                    f"模型区分力最强: {best['分群维度']}/{best['分群名称']}"
                    f"(AUC={best['模型AUC']:.3f})"
                )

        seen = set()
        high_names = []
        for _, r in seg_df.iterrows():
            if r['坏客户率'] > global_bad_rate * 2 and r['分群名称'] not in seen:
                seen.add(r['分群名称'])
                high_names.append(f"{r['分群名称']}({r['坏客户率']:.1%})")
        if high_names:
            if len(high_names) > 5:
                high_names = high_names[:5] + [f'等共{len(high_names)}个']
            findings.append(
                f"高风险分群(坏客户率>{global_bad_rate * 2:.1%}): "
                + ', '.join(high_names)
            )

        seen = set()
        low_names = []
        for _, r in seg_df.iterrows():
            br = r['坏客户率']
            if 0 < br < global_bad_rate * 0.5 and r['分群名称'] not in seen:
                seen.add(r['分群名称'])
                low_names.append(f"{r['分群名称']}({br:.1%})")
        if low_names:
            if len(low_names) > 5:
                low_names = low_names[:5] + [f'等共{len(low_names)}个']
            findings.append(
                f"低风险分群(坏客户率<{global_bad_rate * 0.5:.1%}): "
                + ', '.join(low_names)
            )

    # -- 可信度概况
    n_reliable = overview.get('分析范围', {}).get('IV可信率>=50%的分群数', 0)
    n_total = overview.get('分析范围', {}).get('参与分析的分群总数', 0)
    if n_total > 0:
        ratio = n_reliable / n_total
        findings.append(
            f"可信度: {n_reliable}/{n_total}个分群IV可信率>=50%，"
            + ('结论整体可靠' if ratio >= 0.5 else '部分分群结论需谨慎解读')
        )

    return findings


def _detect_redundant_dims(seg_records):
    """
    检测高度重叠的分群维度对。

    当两个维度 >=70% 的分群名称相同且样本数/坏客户数一致时，标记后者为冗余。
    返回 {被标记维度: 主维度} 映射。
    """
    dim_segments = {}
    for item in seg_records:
        dim = item.get('分群维度', '')
        name = item.get('分群名称', '')
        n = item.get('样本数', 0)
        b = item.get('坏客户数', 0)
        dim_segments.setdefault(dim, {})[name] = (n, b)

    redundant = {}
    dims = list(dim_segments.keys())
    for i in range(len(dims)):
        for j in range(i + 1, len(dims)):
            d1, d2 = dims[i], dims[j]
            s1, s2 = dim_segments[d1], dim_segments[d2]
            common = set(s1) & set(s2)
            if not common:
                continue
            identical = sum(1 for n in common if s1[n] == s2[n])
            smaller = min(len(s1), len(s2))
            if smaller > 0 and identical / smaller >= 0.7:
                if len(s2) <= len(s1):
                    redundant[d2] = d1
                else:
                    redundant[d1] = d2
    return redundant


def _export_llm_report_json(project_root, llm_data, out_dir=None, project_name=None,
                            output_base=None):
    """
    将LLM报告数据导出为面向大模型报告撰写的精简JSON文件。

    精简策略：
    1. 增加「报告目标」业务语境提示
    2. 增加「核心发现」摘要层（5-8条自动提炼）
    3. 概览层特征列表仅保留数量+Top10摘要
    4. 无效特征仅输出名称列表
    5. 分群画像拆分为「重点分群」（完整）和「简略分群」（精简字段）
    6. 自动检测并去重高度重叠的维度（如赛道与产业大类）
    """
    import json

    pname = project_name or CREDIT_CONFIG['project_name']
    if out_dir is None:
        _base = output_base or CREDIT_PIPELINE_PATHS['output_rel']
        out_dir = os.path.join(project_root, _base)
    ensure_dir(out_dir)

    def _serialize_val(val):
        if pd.isna(val):
            return None
        if isinstance(val, (np.integer,)):
            return int(val)
        if isinstance(val, (np.floating,)):
            return round(float(val), 4)
        if isinstance(val, (np.bool_,)):
            return bool(val)
        return val

    # ================================================================
    # 0. 业务语境（低优先级）
    # ================================================================
    output = {
        '报告目标': CREDIT_LLM_REPORT_GOAL_TEMPLATE.format(pname=pname),
    }

    # ================================================================
    # 1. 分析概览（精简特征列表）
    # ================================================================
    overview = {}
    for k, v in llm_data['overview'].items():
        if k == '特征集' and isinstance(v, dict):
            feat_list = v.get('当前分析特征', [])
            overview['特征集'] = {
                '特征数量': len(feat_list),
                '特征列表摘要': (
                    feat_list[:10] + ([f'...等共{len(feat_list)}个']
                                     if len(feat_list) > 10 else [])
                ),
            }
        else:
            overview[k] = v
    output['分析概览'] = overview

    # ================================================================
    # 2. 核心发现（高优先级 - 自动提炼）
    # ================================================================
    feat_df = llm_data['feature_summary']
    seg_df = llm_data['segment_profiles']
    output['核心发现'] = _generate_key_findings(overview, feat_df, seg_df)

    # ================================================================
    # 3. 特征有效性（无效特征压缩为名称列表）
    # ================================================================
    重点特征 = []
    无效特征名称 = []

    if feat_df is not None and not feat_df.empty:
        for _, row in feat_df.iterrows():
            rating = row.get('综合评级', '')
            if rating == '无效特征':
                无效特征名称.append(row['特征名称'])
            else:
                item = {}
                for col in feat_df.columns:
                    val = _serialize_val(row[col])
                    if val is not None:
                        item[col] = val
                重点特征.append(item)

    output['特征有效性汇总'] = 重点特征
    output['无效特征列表'] = 无效特征名称

    # ================================================================
    # 4. 分群画像（分级 + 去重）
    # ================================================================
    global_bad_rate = overview.get('数据概况', {}).get('坏客户率', 0)

    # 4a. 先把所有分群序列化（跳过空字段）
    all_seg_records = []
    if seg_df is not None and not seg_df.empty:
        for _, row in seg_df.iterrows():
            item = {}
            for col in seg_df.columns:
                val = row[col]
                if pd.isna(val) or val == '' or val is None:
                    continue
                item[col] = _serialize_val(val)
            all_seg_records.append(item)

    # 4b. 维度去重：检测高度重叠的维度
    redundant_dims = _detect_redundant_dims(all_seg_records)
    去重说明 = {}
    filtered_records = []

    if redundant_dims:
        primary_segs = {}
        for item in all_seg_records:
            dim = item.get('分群维度', '')
            if dim not in redundant_dims:
                primary_segs.setdefault(dim, set()).add(item.get('分群名称', ''))

        for item in all_seg_records:
            dim = item.get('分群维度', '')
            name = item.get('分群名称', '')
            if dim in redundant_dims:
                primary_dim = redundant_dims[dim]
                primary_names = primary_segs.get(primary_dim, set())
                if name in primary_names:
                    continue
                去重说明[dim] = (
                    f"与'{primary_dim}'高度重叠，仅保留差异分群"
                )
            filtered_records.append(item)
    else:
        filtered_records = all_seg_records

    # 4c. 分级：重点 vs 简略
    简略字段 = {'分群维度', '分群名称', '样本数', '坏客户数', '坏客户率', '模型AUC', 'AUC类型', '风险特征概要'}
    重点分群 = []
    简略分群 = []

    for item in filtered_records:
        auc = item.get('模型AUC')
        br = item.get('坏客户率', 0)
        is_key = False

        if auc is not None and auc >= 0.65:
            is_key = True
        if global_bad_rate > 0 and br > global_bad_rate * 2:
            is_key = True
        if global_bad_rate > 0 and 0 < br < global_bad_rate * 0.5:
            is_key = True
        if item.get('样本数', 0) >= 1000 and auc is not None:
            is_key = True

        if is_key:
            重点分群.append(item)
        else:
            简略分群.append({k: item[k] for k in 简略字段 if k in item})

    output['分群画像_重点'] = 重点分群
    output['分群画像_简略'] = 简略分群

    if 去重说明:
        output['维度去重说明'] = 去重说明

    # ================================================================
    # 写出
    # ================================================================
    filepath = os.path.join(out_dir, f'{pname}_LLM报告数据.json')
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    return filepath


def calc_feature_thresholds(df, segment_feature_pairs, target=COL_TARGET):
    """
    使用 optbinning 最优分箱为指定的"分群-特征"组合寻找关键业务阈值。

    参数:
        df: 完整的宽表 DataFrame(含分群列和特征列)
        segment_feature_pairs: 列表，每项为 (分群维度列名, 分群值, 特征名)
            例: [('企业规模', '大型企业', '非银机构占比'), ...]
        target: 目标变量列名

    返回:
        threshold_df: 阈值汇总表（每个组合一行）
        detail_tables: dict {(分群值, 特征名): 分箱明细 DataFrame}
    """
    from optbinning import OptimalBinning
    from scipy.stats import chi2_contingency

    results = []
    detail_tables = {}

    for dim_col, group_val, feat in segment_feature_pairs:
        label = f"{group_val}-{feat}"

        if dim_col not in df.columns:
            print(f"  [跳过] {label}: 维度列 '{dim_col}' 不存在")
            continue
        if feat not in df.columns:
            print(f"  [跳过] {label}: 特征列 '{feat}' 不存在")
            continue

        df_sub = df[df[dim_col] == group_val].copy()
        n_total = len(df_sub)
        n_bad = int(df_sub[target].sum())

        if n_total < MIN_SAMPLES:
            print(f"  [跳过] {label}: 样本不足 (n={n_total} < {MIN_SAMPLES})")
            continue
        if n_bad < MIN_BAD_SAMPLES:
            print(f"  [跳过] {label}: 坏客户不足 (bad={n_bad} < {MIN_BAD_SAMPLES})")
            continue

        x = df_sub[feat].fillna(0).values
        y = df_sub[target].values

        if pd.Series(x).nunique() <= 1:
            print(f"  [跳过] {label}: 特征无变异")
            continue

        try:
            optb = OptimalBinning(
                name=feat, dtype="numerical", solver="cp",
                min_bin_size=0.05, max_n_bins=8,
            )
            optb.fit(x, y)
        except Exception as e:
            print(f"  [跳过] {label}: optbinning 异常 - {e}")
            continue

        if optb.status not in ("OPTIMAL", "FEASIBLE"):
            print(f"  [跳过] {label}: optbinning 状态 = {optb.status}")
            continue

        splits = optb.splits
        if len(splits) == 0:
            print(f"  [跳过] {label}: 未产生有效分箱")
            continue

        bt_df = optb.binning_table.build()
        # 去除 Special 和 Missing 行
        data_rows = bt_df[~bt_df['Bin'].isin(['Special', 'Missing'])].copy()
        data_rows = data_rows.reset_index(drop=True)

        detail_tables[(group_val, feat)] = data_rows

        event_rates = data_rows['Event rate'].values
        if len(event_rates) < 2:
            print(f"  [跳过] {label}: 分箱不足 2 个")
            continue

        # 找坏客户率跳升最大的相邻边界
        diffs = np.diff(event_rates)
        abs_diffs = np.abs(diffs)
        max_jump_idx = int(np.argmax(abs_diffs))

        if max_jump_idx >= len(splits):
            max_jump_idx = len(splits) - 1
        critical_threshold = splits[max_jump_idx]

        # 判断风险方向：阈值处坏客户率是升高还是降低
        risk_above = diffs[max_jump_idx] > 0

        # 计算阈值两侧统计量
        mask_above = x > critical_threshold
        mask_below = ~mask_above

        n_above = int(mask_above.sum())
        n_below = int(mask_below.sum())
        bad_above = int(y[mask_above].sum())
        bad_below = int(y[mask_below].sum())
        rate_above = bad_above / n_above if n_above > 0 else 0
        rate_below = bad_below / n_below if n_below > 0 else 0

        if risk_above:
            high_risk_rate = rate_above
            low_risk_rate = rate_below
            high_risk_n = n_above
            risk_direction = '正向'
        else:
            high_risk_rate = rate_below
            low_risk_rate = rate_above
            high_risk_n = n_below
            risk_direction = '反向'

        risk_ratio = (high_risk_rate / low_risk_rate) if low_risk_rate > 0 else float('inf')

        # 卡方检验
        try:
            table = np.array([[bad_above, n_above - bad_above],
                              [bad_below, n_below - bad_below]])
            if table.min() >= 0 and table.sum() > 0:
                chi2, p_val, _, _ = chi2_contingency(table)
            else:
                p_val = 1.0
        except Exception:
            p_val = 1.0

        # 全局IV（来自 optbinning）
        iv_total = data_rows['IV'].sum() if 'IV' in data_rows.columns else np.nan

        # 显著性标记
        if p_val < 0.001:
            sig = '***'
        elif p_val < 0.01:
            sig = '**'
        elif p_val < 0.05:
            sig = '*'
        else:
            sig = 'ns'

        # 业务规则有效性判断
        if risk_ratio < 1.2 or p_val > 0.05:
            rule_valid = False
            rule_text = '区分力不足，不建议设置阈值规则'
        else:
            rule_valid = True
            if risk_above:
                rule_text = (f"{feat} > {critical_threshold:.4f} 时，"
                             f"坏客户率 {high_risk_rate:.2%}，"
                             f"是低风险侧的 {risk_ratio:.1f} 倍，建议加强关注")
            else:
                rule_text = (f"{feat} <= {critical_threshold:.4f} 时，"
                             f"坏客户率 {high_risk_rate:.2%}，"
                             f"是另一侧的 {risk_ratio:.1f} 倍，建议加强关注")

        results.append({
            '分群维度': dim_col,
            '分群': group_val,
            '特征': feat,
            '风险方向': risk_direction,
            '建议阈值': round(critical_threshold, 4),
            '高风险侧样本数': high_risk_n,
            '高风险侧坏客户率': round(high_risk_rate, 4),
            '低风险侧坏客户率': round(low_risk_rate, 4),
            '风险倍数': round(risk_ratio, 2),
            '卡方p值': round(p_val, 6),
            '显著性': sig,
            '总分箱数': len(data_rows),
            '全局IV': round(iv_total, 4) if not pd.isna(iv_total) else np.nan,
            '规则有效': rule_valid,
            '业务规则建议': rule_text,
            '分群总样本': n_total,
            '分群坏客户数': n_bad,
            '分群坏客户率': round(n_bad / n_total, 4),
        })

        print(f"  [{group_val}] {feat}: 阈值={critical_threshold:.4f}, "
              f"风险倍数={risk_ratio:.1f}x, p={p_val:.4f} {sig}")

    threshold_df = pd.DataFrame(results)
    return threshold_df, detail_tables


def build_corr_export(corr_results, meta_results):
    """合并各维度相关系数结果用于导出"""
    dfs = []
    for dim_name, corr_df in corr_results.items():
        if corr_df is None or corr_df.empty:
            continue
        export = corr_df.copy()
        export['分群维度'] = dim_name
        export['分群名称'] = export.index
        meta = meta_results.get(dim_name)
        if meta is not None and not meta.empty:
            export = export.reset_index(drop=True)
            meta_reset = meta.reset_index()
            export = export.merge(meta_reset, on='分群名称', how='left')
        dfs.append(export)

    if not dfs:
        return None

    result = pd.concat(dfs, ignore_index=True)
    # 调整列顺序
    meta_cols = ['分群维度', '分群名称', '样本数', '坏客户数', '坏客户率']
    feat_cols = [c for c in result.columns if c not in meta_cols]
    cols = [c for c in meta_cols if c in result.columns] + feat_cols
    return result[cols]


def build_lr_export(lr_coef_results, lr_auc_results):
    """合并各维度逻辑回归结果用于导出"""
    dfs = []
    for dim_name, coef_df in lr_coef_results.items():
        if coef_df is None or coef_df.empty:
            continue
        export = coef_df.copy()
        export['分群维度'] = dim_name
        export['分群名称'] = export.index
        auc_df = lr_auc_results.get(dim_name)
        if auc_df is not None and not auc_df.empty:
            export = export.reset_index(drop=True)
            auc_reset = auc_df[['AUC', 'AUC类型', '样本数', '坏客户数']].reset_index()
            export = export.merge(auc_reset, on='分群名称', how='left')
        dfs.append(export)

    if not dfs:
        return None

    result = pd.concat(dfs, ignore_index=True)
    meta_cols = ['分群维度', '分群名称', 'AUC', 'AUC类型', '样本数', '坏客户数']
    feat_cols = [c for c in result.columns if c not in meta_cols]
    cols = [c for c in meta_cols if c in result.columns] + feat_cols
    return result[cols]
