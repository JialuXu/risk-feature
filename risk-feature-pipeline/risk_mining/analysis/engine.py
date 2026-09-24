# -*- coding: utf-8 -*-
"""共享分析引擎（去重后的单一实现）。

credit / gsfc / generic 三条链路共用的分群分析内核，纯计算、配置驱动、不绑定任何
具体数据集的列名（target / dim / 特征列均由调用方传入）：

- 分群基础摸底（类别维度 + 二进制资质标签）
- 单变量风险分析（相关系数 + T 检验）
- 多变量逻辑回归（标准化 + L2，样本充足时用 5 折交叉验证 AUC）
- 分群 IV（自适应分箱 + WOE 截断 + 可信度评估，底层调用 analysis.iv_core）
- 可信度诊断 / 特征集对比 / 候选阈值

历史：本实现曾以副本形式散落在 risk_iv_diagnosis / risk_export_report /
risk_logistic_regression 三个 Skill 的 scripts 下；现收敛于此，三处退化为 shim。
"""

import warnings
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_score

from risk_core.config import (
    CREDIT_CONFIG, SAMPLE_THRESHOLDS,
    MIN_SAMPLES, MIN_BAD_SAMPLES,
    IV_THRESHOLD, IV_PREDICTION_OVERSTRONG_MIN,
    COL_CUSTOMER_ID, COL_CUSTOMER_ID_STR, COL_TARGET,
    COL_REPORT_DATE, COL_QUAL_PREFIX,
    COL_INDUSTRY_DATA_COLS, COL_AMOUNT_COLS,
)
from .iv_core import calc_iv as _calc_iv_base, _assess_iv_reliability
from risk_core.column_mapper import ColumnMapper
from risk_core.missing import (
    MISSING_POLICY_MODEL, impute_for_model, impute_median, pairwise_valid,
)

warnings.filterwarnings('ignore')

# 从配置中提取阈值常量
_T = SAMPLE_THRESHOLDS
_mapper = ColumnMapper()


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


# =============================================================================
# Section 2: 特征工程
# =============================================================================


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


# =============================================================================
# Section 4: 单变量风险分析
# =============================================================================

def _univariate_single_group(group_df, feature_cols, target=COL_TARGET):
    """单个分群的单变量分析"""
    corr_row, diff_row, pval_row = {}, {}, {}
    for feat in feature_cols:
        if feat not in group_df.columns:
            continue
        # 缺失口径：统计检验一律成对删除（与下方均值差 / T 检验同一批样本）
        valid = pairwise_valid(group_df, feat, target)
        feat_data = valid[feat]

        # 相关系数（点二列相关）
        corr_row[feat] = (
            feat_data.corr(valid[target]) if len(valid) > 2 and feat_data.std() > 0 else 0.0
        )

        # 好坏客户均值差异
        m_bad = group_df.loc[group_df[target] == 1, feat].mean()
        m_good = group_df.loc[group_df[target] == 0, feat].mean()
        diff_row[feat] = m_bad - m_good if pd.notna(m_bad) and pd.notna(m_good) else 0.0

        # Welch's t检验
        bad_vals = group_df.loc[group_df[target] == 1, feat].dropna()
        good_vals = group_df.loc[group_df[target] == 0, feat].dropna()
        if len(bad_vals) > 1 and len(good_vals) > 1:
            try:
                _, p = stats.ttest_ind(bad_vals, good_vals, equal_var=False)
                pval_row[feat] = p
            except Exception:
                pval_row[feat] = 1.0
        else:
            pval_row[feat] = 1.0

    return corr_row, diff_row, pval_row


def univariate_by_group(df, dim_col, feature_cols, target=COL_TARGET,
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


def univariate_by_qualification(df, qual_cols, feature_cols, target=COL_TARGET,
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
    _print_sample_summary(df, label='单变量分析(资质标签) - 输入全量', target=target)

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
    # 默认即 L2 正则（sklearn 1.8 起 penalty 参数已弃用，1.10 移除；
    # 新默认 l1_ratio=0 与旧 penalty='l2' 数值等价，故不再显式传 penalty）
    model = LogisticRegression(
        C=1.0, solver='lbfgs', max_iter=1000, random_state=42
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


def lr_by_group(df, dim_col, feature_cols, target=COL_TARGET,
                min_bad=None, min_good=None, min_group_size=None,
                missing_policy=MISSING_POLICY_MODEL):
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
    _print_sample_summary(df, label=f'逻辑回归({dim_col}) - 输入全量', target=target)
    df_v = df[df[dim_col].notna()]
    _print_sample_summary(df_v, label=f'剔除{dim_col}为空后', target=target)

    coef_dict, auc_rows = {}, []
    skipped = []
    analyzed = []

    valid_feats = [f for f in feature_cols if f in df_v.columns]

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

        X = impute_for_model(gdf[valid_feats], missing_policy)
        y = gdf[target]
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


def lr_by_qualification(df, qual_cols, feature_cols, target=COL_TARGET,
                        min_bad=None, min_good=None,
                        missing_policy=MISSING_POLICY_MODEL):
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
    _print_sample_summary(df, label='逻辑回归(资质标签) - 输入全量', target=target)

    valid_feats = [f for f in feature_cols if f in df.columns]
    coef_dict, auc_rows = {}, []
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

        X = impute_for_model(df_yes[valid_feats], missing_policy)
        y = df_yes[target]
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
    tw, tm, ts = IV_THRESHOLD['weak'], IV_THRESHOLD['medium'], IV_THRESHOLD['strong']

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
        elif iv_val < tw:
            level = '无预测能力'
        elif iv_val < tm:
            level = '弱'
        elif iv_val < ts:
            level = '中等'
        elif iv_val < IV_PREDICTION_OVERSTRONG_MIN:
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

    return pd.DataFrame(rows), skipped


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

    return pd.DataFrame(rows), skipped


# =============================================================================
# Section 7: 特征集对比
# =============================================================================

def compare_feature_sets(df, dim_col, raw_features, derived_features, target=COL_TARGET,
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
    _print_sample_summary(df, label=f'特征集对比({dim_col}) - 输入全量', target=target)
    df_v = df[df[dim_col].notna()]
    _print_sample_summary(df_v, label=f'剔除{dim_col}为空后', target=target)

    rows = []
    analyzed = []
    skipped = []

    for gname, gdf in df_v.groupby(dim_col):
        n_bad = int(gdf[target].sum())
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

        y = gdf[target]
        auc_raw, auc_derived = np.nan, np.nan

        for feat_set, label in [(raw_features, 'raw'), (derived_features, 'derived')]:
            X = impute_median(gdf[[f for f in feat_set if f in gdf.columns]])
            X = X[[c for c in X.columns if X[c].std() > 0]]
            if len(X.columns) < 2:
                continue
            try:
                scaler = StandardScaler()
                Xs = scaler.fit_transform(X)
                mdl = LogisticRegression(
                    C=1.0, solver='lbfgs',
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
            except Exception as e:
                print(f"[WARN] 组合 LR 拟合失败（分群={gname}, 特征集={label}）: {e}")

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


def calc_feature_thresholds(df, segment_feature_pairs, target=COL_TARGET):
    """
    使用 optbinning 最优分箱为指定的"分群-特征"组合寻找关键业务阈值。

    参数:
        df: 完整的宽表 DataFrame（含分群列和特征列）
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

        x = impute_median(df_sub[[feat]])[feat].values  # 缺失口径：建模/切分 → 中位数填补
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
        # 去除 Special / Missing 行以及末尾的 Totals 汇总行（其 Bin 为空串）；
        # 汇总行若留着，会被当成最后一个箱参与跳升搜索，且让全局 IV 翻倍
        data_rows = bt_df[~bt_df['Bin'].isin(['Special', 'Missing', ''])].copy()
        data_rows = data_rows[
            ~data_rows['Bin'].astype(str).str.lower().str.contains('total')
        ].reset_index(drop=True)

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

