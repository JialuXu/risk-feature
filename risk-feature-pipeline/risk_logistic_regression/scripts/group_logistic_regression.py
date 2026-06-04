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

from .base_modeling import eval_lr_roc_auc
from .config import (
    CREDIT_CONFIG, SAMPLE_THRESHOLDS,
    MIN_SAMPLES, MIN_BAD_SAMPLES,
    COL_CUSTOMER_ID, COL_CUSTOMER_ID_STR, COL_TARGET,
    COL_REPORT_DATE, COL_QUAL_PREFIX,
    COL_INDUSTRY_DATA_COLS, COL_AMOUNT_COLS, COL_SEGMENT_DIMS,
    RESULTS_DIR_CREDIT, OUTPUT_DIR_CREDIT,
)
from .io_utils import get_project_root, read_csv_auto_encoding, ensure_dir

import sys as _sys
from pathlib import Path as _Path
_MY_SKILLS_ROOT = str(_Path(__file__).resolve().parent.parent.parent)
if _MY_SKILLS_ROOT not in _sys.path:
    _sys.path.insert(0, _MY_SKILLS_ROOT)
from risk_pipeline.column_mapper import ColumnMapper

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


# =============================================================================
# Section 2: 特征工程
# =============================================================================


# =============================================================================
# Section 3: 分群基础分析
# =============================================================================


# =============================================================================
# Section 4: 单变量风险分析
# =============================================================================


# =============================================================================
# Section 5: 多变量逻辑回归分析
# =============================================================================

def _fit_lr_single(X_scaled, y, feature_names, n_samples, n_bad):
    """
    拟合单个逻辑回归模型并计算AUC

    关键合规项：
    - 总样本与坏客户数同时满足 SAMPLE_THRESHOLDS 中 CV 门槛时用 5 折分层 CV
    - 否则为训练集 AUC，且 AUC类型 显式标注（与 base_modeling.eval_lr_roc_auc 一致）
    """
    model = LogisticRegression(
        penalty='l2', C=1.0, solver='lbfgs', max_iter=1000, random_state=42
    )
    model.fit(X_scaled, y)

    coef_dict = dict(zip(feature_names, model.coef_[0]))
    auc_val, auc_type = eval_lr_roc_auc(
        model, X_scaled, y, n_samples, n_bad, _T
    )
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


# =============================================================================
# Section 6: IV值分析
# =============================================================================


# =============================================================================
# Section 7: 特征集对比
# =============================================================================


# =============================================================================
# Section 8: 可信度诊断
# =============================================================================


# =============================================================================
# Section 9: 结果导出
# =============================================================================

