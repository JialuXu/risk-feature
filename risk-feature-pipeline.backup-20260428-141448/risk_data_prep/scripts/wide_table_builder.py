# -*- coding: utf-8 -*-
import numpy as np
import pandas as pd

from .config import (
    COL_CUSTOMER_ID, COL_TARGET, COL_CHANGE_DATE, COL_AMOUNT_COLS,
    FINANCE_MERGE_DUP_COLS, WAIST_MIN, WAIST_MAX, WAIST_HIGH_RATINGS,
)


def build_wide_table(data):
    """
    合并客户信息、工商变更、财务、产业侧表，生成 is_bad 及授信分层相关标记。

    总样本以客户信息行为准；侧表按主键去重后左连接。
    """
    print("\n" + "=" * 60)
    print("Step 1: 数据准备与宽表构建")
    print("=" * 60)

    cid = COL_CUSTOMER_ID
    tgt = COL_TARGET

    df = data['客户信息'].copy()
    df[cid] = df[cid].astype(str).str.strip()
    print(f"[INFO] 客户信息样本量: {len(df)}")

    if data.get('工商变更') is not None:
        df_change = data['工商变更'].copy()
        df_change[cid] = df_change[cid].astype(str).str.strip()
        if COL_CHANGE_DATE in df_change.columns:
            df_change[COL_CHANGE_DATE] = pd.to_datetime(
                df_change[COL_CHANGE_DATE], errors='coerce'
            )
            df_change = df_change.sort_values(COL_CHANGE_DATE, ascending=False)
            df_change = df_change.drop_duplicates(subset=[cid], keep='first')
        df = df.merge(df_change, on=cid, how='left')
        print(f"[INFO] 合并工商变更后样本量: {len(df)}")

    if data.get('财务数据') is not None:
        df_finance = data['财务数据'].copy()
        df_finance[cid] = df_finance[cid].astype(str).str.strip()
        df_finance = df_finance.drop_duplicates(subset=[cid], keep='first')
        exclude_cols = [
            c for c in df_finance.columns
            if '_来源' in c or c == '客户名称'
        ]
        dup_set = set(FINANCE_MERGE_DUP_COLS)
        exclude_cols.extend([c for c in df_finance.columns if c in dup_set])
        finance_cols = (
            [cid]
            + [c for c in df_finance.columns if c not in exclude_cols and c != cid]
        )
        df_finance = df_finance[finance_cols]
        df = df.merge(df_finance, on=cid, how='left')
        print(f"[INFO] 合并财务数据后样本量: {len(df)}")

    if data.get('产业数据') is not None:
        df_industry = data['产业数据'].copy()
        df_industry[cid] = df_industry[cid].astype(str).str.strip()
        df_industry[cid] = df_industry[cid].str.replace(
            r'\.0$', '', regex=True
        )
        df_industry = df_industry.drop_duplicates(subset=[cid], keep='first')
        if '赛道' in df_industry.columns:
            df_industry = df_industry[[cid, '赛道']]
            df = df.merge(df_industry, on=cid, how='left')
            print(f"[INFO] 合并产业数据后样本量: {len(df)}")

    if data.get('坏客户标记') is not None:
        df_bad = data['坏客户标记'].copy()
        df_bad[cid] = df_bad[cid].astype(str).str.strip()
        bad_set = set(df_bad[cid].unique())
        df[tgt] = df[cid].isin(bad_set).astype(int)
        print(f"[INFO] 坏客户标记数量: {len(bad_set)}")
        print(f"[INFO] 匹配到的坏客户数: {df[tgt].sum()}")
    else:
        df[tgt] = 0
        print("[WARN] 未找到坏客户标记文件，所有客户标记为好客户")

    amt_col = COL_AMOUNT_COLS[0] if COL_AMOUNT_COLS else '授信总金额'
    if amt_col in df.columns:
        df[amt_col] = pd.to_numeric(df[amt_col], errors='coerce').fillna(0)
        _amt = df[amt_col]
        if '内部评级' in df.columns:
            _is_hr = df['内部评级'].isin(WAIST_HIGH_RATINGS)
        else:
            _is_hr = pd.Series(False, index=df.index)
        _is_mid = (_amt >= WAIST_MIN) & (_amt <= WAIST_MAX)

        def _fmt(v):
            if v >= 1e8:
                return f'{v / 1e8:g}亿'
            if v >= 1e4:
                return f'{v / 1e4:g}万'
            return f'{v:g}元'

        _lo, _hi = _fmt(WAIST_MIN), _fmt(WAIST_MAX)

        df['授信分层'] = np.select(
            [
                _amt <= 0,
                _amt < WAIST_MIN,
                _is_mid & _is_hr,
                _is_mid & ~_is_hr,
                _amt > WAIST_MAX,
            ],
            [
                '无授信',
                f'授信<{_lo}',
                f'授信{_lo}-{_hi}(高评级)',
                f'授信{_lo}-{_hi}(非高评级)',
                f'授信>{_hi}',
            ],
            default='无授信',
        )
        df['是否腰部企业'] = (_is_mid & _is_hr).astype(int)
        df['是否中等授信非高评级'] = (_is_mid & ~_is_hr).astype(int)
        print(f"[INFO] 腰部企业(中等授信+高评级)数量: {df['是否腰部企业'].sum()}")
        print(
            f"[INFO] 中等授信非高评级数量: "
            f"{df['是否中等授信非高评级'].sum()}"
        )

    print(f"\n[INFO] 最终宽表样本量: {len(df)}")
    print(f"[INFO] 总坏客户率: {df[tgt].mean() * 100:.2f}%")

    return df
