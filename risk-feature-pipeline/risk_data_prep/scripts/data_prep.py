# -*- coding: utf-8 -*-
"""
企业信贷场景下的征信宽表数据准备。

职责：按客户基准表合并征信/产业侧表、主键清洗、目标列打标、金额与缺失处理。
不包含 IV、逻辑回归、单变量等下游分析（见各专项 Skill）。
"""

import os

import numpy as np
import pandas as pd

from .config import (
    CREDIT_CONFIG,
    COL_CUSTOMER_ID, COL_CUSTOMER_ID_STR, COL_TARGET, COL_REPORT_DATE,
    COL_QUAL_PREFIX, COL_INDUSTRY_DATA_COLS, COL_AMOUNT_COLS,
)
from .io_utils import get_project_root, read_csv_auto_encoding


def load_credit_data(project_root=None):
    """
    加载征信宽表构建所需的全部数据表。

    参数:
        project_root: 项目根目录；为 None 时由 get_project_root() 自动检测。

    返回:
        data: 表名字符串到 DataFrame 的字典（缺失文件时该键不出现或见实现约定）。
    """
    if project_root is None:
        project_root = get_project_root()

    data = {}
    data_config = CREDIT_CONFIG['data']
    for name, rel_path in data_config.items():
        full_path = os.path.join(project_root, rel_path)
        if os.path.exists(full_path):
            # §5.1 主键 str 契约：与 risk_core.io_utils.load_data:49（gsfc 链路）对称。
            # 不锁则 '00123' 被推断成 int，_clean_id 无法找回前导零；若各表推断
            # 形态不一（如坏客户表混入字母数字 ID 而保留 str），isin 静默漏标。
            data[name] = read_csv_auto_encoding(full_path, dtype={COL_CUSTOMER_ID: str})
            print(f"  {name}: {data[name].shape}")
        else:
            print(f"  [警告] {name} 文件不存在: {full_path}")
    return data


def _clean_id(series):
    """主键统一为去空格、去掉".0"后缀的字符串，便于多表关联。"""
    return series.astype(str).str.replace('.0', '', regex=False).str.strip()


def prepare_credit_wide_table(data):
    """
    构建征信分析宽表。

    流程概要：
    1. 以客户信息为总样本基准（去重后定义分析总体）
    2. 依据坏客户标记打 is_bad
    3. 征信按报告日期取最新一条后左连接
    4. 合并产业属性与资质标签列
    5. 数值列缺失填 0（无该主题暴露等业务口径）

    参数:
        data: load_credit_data() 返回的字典。

    返回:
        df: 宽表；summary: 合并过程关键统计字典。
    """
    cid = COL_CUSTOMER_ID
    cid_str = COL_CUSTOMER_ID_STR
    tgt = COL_TARGET
    rdate = COL_REPORT_DATE

    df_cust = data['客户信息'].copy()
    df_bad = data['坏客户标记'].copy()

    df_cust[cid_str] = _clean_id(df_cust[cid])
    df_cust = df_cust.drop_duplicates(
        subset=[cid_str], keep='first'
    ).reset_index(drop=True)

    bad_set = set(_clean_id(df_bad[cid]))
    df_cust[tgt] = df_cust[cid_str].isin(bad_set).astype(int)

    amt_cols = CREDIT_CONFIG['credit_prep_amount_cols']
    if all(c in df_cust.columns for c in amt_cols):
        for c in amt_cols:
            df_cust[c] = df_cust[c].replace('-', np.nan)
            df_cust[c] = (
                df_cust[c].astype(str)
                .str.replace(',', '', regex=False)
            )
            df_cust[c] = pd.to_numeric(df_cust[c], errors='coerce')

        sub_cols = [c for c in COL_AMOUNT_COLS[1:]
                    if c in df_cust.columns]
        if sub_cols:
            _sub_sum = df_cust[sub_cols].sum(axis=1, min_count=1)
            _fix_mask = df_cust[amt_cols[0]].isna() & _sub_sum.notna()
            n_fixed = int(_fix_mask.sum())
            if n_fixed > 0:
                df_cust.loc[_fix_mask, amt_cols[0]] = _sub_sum[_fix_mask]
                print(
                    f"  [修复] {amt_cols[0]}为空但有余额子项的 {n_fixed} 行，"
                    f"已用余额子项加总回补"
                )

    n_total = len(df_cust)
    n_bad = int(df_cust[tgt].sum())

    summary = {
        '客户总数(总样本)': n_total,
        '坏客户数': n_bad,
        '坏客户率': float(df_cust[tgt].mean()),
    }

    print(
        f"  总样本基准(客户信息): {n_total} 户, "
        f"坏客户 {n_bad}, 坏客户率 {summary['坏客户率']:.4f}"
    )

    df_base = df_cust
    if '征信数据' in data:
        df_credit_raw = data['征信数据'].copy()

        if rdate in df_credit_raw.columns:
            df_credit_raw[rdate] = pd.to_datetime(
                df_credit_raw[rdate], errors='coerce'
            )
            df_credit = (
                df_credit_raw
                .sort_values(rdate, ascending=False)
                .drop_duplicates(subset=[cid], keep='first')
                .reset_index(drop=True)
            )
        else:
            df_credit = df_credit_raw.drop_duplicates(
                subset=[cid], keep='first'
            ).reset_index(drop=True)

        df_credit[cid_str] = _clean_id(df_credit[cid])

        cust_set = set(df_cust[cid_str])
        n_credit_dedup = len(df_credit)
        credit_in_scope = df_credit[cid_str].isin(cust_set)
        n_in_scope = int(credit_in_scope.sum())
        n_out_scope = n_credit_dedup - n_in_scope

        print(f"  征信数据去重后: {n_credit_dedup} 条")
        print(f"    - 匹配客户范围: {n_in_scope} 条")
        print(f"    - 超出客户范围(已排除): {n_out_scope} 条")

        credit_feature_cols = [
            c for c in df_credit.columns
            if c not in (cid, cid_str, rdate)
        ]
        merge_cols = [cid_str] + credit_feature_cols

        df_base = df_cust.merge(
            df_credit[merge_cols], on=cid_str, how='left'
        )

        credit_id_set = set(df_credit[cid_str])
        n_matched = int(df_base[cid_str].isin(credit_id_set).sum())
        n_no_credit = n_total - n_matched
        summary['匹配征信数据'] = n_matched
        summary['无征信数据客户'] = n_no_credit
        print(
            f"    - 有征信数据的客户: {n_matched} "
            f"({n_matched / n_total * 100:.1f}%)"
        )
        print(
            f"    - 无征信数据的客户: {n_no_credit} "
            f"({n_no_credit / n_total * 100:.1f}%)"
        )

    if '产业数据' in data:
        df_ind = data['产业数据'].copy()
        df_ind[cid_str] = _clean_id(df_ind[cid])
        ind_cols = [cid_str]
        for c in COL_INDUSTRY_DATA_COLS:
            if c in df_ind.columns:
                ind_cols.append(c)
        qual_cols = [c for c in df_ind.columns if c.startswith(COL_QUAL_PREFIX)]
        ind_cols.extend(qual_cols)
        ind_cols = list(dict.fromkeys(ind_cols))
        df_base = df_base.merge(
            df_ind[ind_cols], on=cid_str, how='left'
        )
        n_matched_ind = (
            df_base['客户分层'].notna().sum()
            if '客户分层' in df_base.columns else 0
        )
        summary['匹配产业信息'] = n_matched_ind

    object_keep = frozenset(CREDIT_CONFIG['credit_prep_object_keep_cols'])

    for col in df_base.columns:
        if df_base[col].dtype == object and col not in object_keep:
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

    numeric_cols = df_base.select_dtypes(include=[np.number]).columns
    cols_to_fill = [c for c in numeric_cols if c not in (cid, tgt)]

    missing_counts = df_base[cols_to_fill].isna().sum()
    cols_with_missing = missing_counts[missing_counts > 0].index

    fill_count = 0
    if len(cols_with_missing) > 0:
        fill_count = int(missing_counts[cols_with_missing].sum())
        df_base[cols_with_missing] = df_base[cols_with_missing].fillna(0)

    summary['填充缺失值数'] = fill_count

    print(f"\n合并后数据形状: {df_base.shape}")
    print(
        f"总样本: {summary['客户总数(总样本)']}, "
        f"坏客户: {summary['坏客户数']}"
        f" (坏客户率: {summary['坏客户率']:.4f})"
    )

    return df_base, summary
