# -*- coding: utf-8 -*-
import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype

from .config import (
    MIN_SAMPLES,
    MIN_BAD_SAMPLES,
    WOE_CAP,
    COL_TARGET,
)
from risk_mining.analysis.iv_core import _adaptive_bins as _adaptive_bins_for_woe, _quantile_bins


def rate_feature(iv_val, corr_mean, sign_consistent):
    """特征综合评级（强度 + 跨分群稳定性）。

    本 Skill 服务于贷前业务建议 / 贷后预警规则，而非评分卡建模：除单变量 IV
    强度外，**跨分群方向一致的中等信号同样值得纳入**——一个在各客群里方向都
    一致的特征，比孤立的高 IV 更可信、更能落成对全组合生效的规则。

    - 核心特征：全局 IV >= 0.2 且跨分群方向一致（又强又稳，可直接写建议/做规则）
    - 重要特征：全局 IV >= 0.1，或（跨分群方向一致 且 |相关系数均值| >= 0.05）
    - 辅助特征：全局 IV >= 0.02，或 |相关系数均值| >= 0.05
    - 无效特征：以上均不满足

    收敛说明：此前 report_analysis / report_export 各有一份逐字相近的内联实现
    （且都漏掉了"方向一致的中等信号提升为重要特征"这条），现统一到这里，避免再次漂移。
    """
    if iv_val >= 0.2 and sign_consistent:
        return '核心特征'
    if iv_val >= 0.1 or (sign_consistent and corr_mean is not None and abs(corr_mean) >= 0.05):
        return '重要特征'
    if iv_val >= 0.02 or (corr_mean is not None and abs(corr_mean) >= 0.05):
        return '辅助特征'
    return '无效特征'


def build_group_iv_pivot(df_iv, group_prefixes=None, max_groups=12, top_n=20, base_group='全量'):
    """
    构建分群IV透视表，便于绘制热力图。

    当 df_iv 中包含 'IV可信度' 列时，会额外返回一个与透视表同形的可信度矩阵，
    便于在热力图中标注不可信的单元格。
    """
    if df_iv is None or df_iv.empty:
        return None, [], []

    df = df_iv.copy()
    df = df[pd.notna(df['IV值'])]
    if df.empty:
        return None, [], []

    if group_prefixes:
        mask = pd.Series(False, index=df.index)
        for p in group_prefixes:
            mask |= (df['分群'] == p) | df['分群'].astype(str).str.startswith(p)
        df = df[mask]

    if df.empty:
        return None, [], []

    group_order = (
        df.groupby('分群')['IV值']
        .mean()
        .sort_values(ascending=False)
        .index
        .tolist()
    )
    if max_groups:
        group_order = group_order[:max_groups]

    df = df[df['分群'].isin(group_order)]

    if base_group in df['分群'].values:
        feat_order = (
            df[df['分群'] == base_group]
            .sort_values('IV值', ascending=False)['特征']
            .tolist()
        )
    else:
        feat_order = (
            df.groupby('特征')['IV值']
            .mean()
            .sort_values(ascending=False)
            .index
            .tolist()
        )

    if top_n:
        feat_order = feat_order[:top_n]

    pivot = (
        df[df['特征'].isin(feat_order)]
        .pivot_table(index='特征', columns='分群', values='IV值', aggfunc='first')
        .reindex(index=feat_order, columns=group_order)
    )
    return pivot, feat_order, group_order


def build_iv_reliability_pivot(df_iv, group_prefixes=None, max_groups=12, top_n=20, base_group='全量'):
    """
    构建 IV 可信度透视表（与 IV 数值透视表同形）。
    返回一个字符串矩阵，每个单元格为 IV 可信度等级。
    """
    if df_iv is None or df_iv.empty or 'IV可信度' not in df_iv.columns:
        return None

    df = df_iv.copy()
    df = df[pd.notna(df['IV值'])]

    if group_prefixes:
        mask = pd.Series(False, index=df.index)
        for p in group_prefixes:
            mask |= (df['分群'] == p) | df['分群'].astype(str).str.startswith(p)
        df = df[mask]

    if df.empty:
        return None

    group_order = (
        df.groupby('分群')['IV值'].mean()
        .sort_values(ascending=False).index.tolist()
    )
    if max_groups:
        group_order = group_order[:max_groups]
    df = df[df['分群'].isin(group_order)]

    if base_group in df['分群'].values:
        feat_order = (
            df[df['分群'] == base_group]
            .sort_values('IV值', ascending=False)['特征'].tolist()
        )
    else:
        feat_order = (
            df.groupby('特征')['IV值'].mean()
            .sort_values(ascending=False).index.tolist()
        )
    if top_n:
        feat_order = feat_order[:top_n]

    pivot = (
        df[df['特征'].isin(feat_order)]
        .pivot_table(index='特征', columns='分群', values='IV可信度', aggfunc='first')
        .reindex(index=feat_order, columns=group_order)
    )
    return pivot


def build_segment_summary(df_iv):
    """
    构建分群样本量汇总表，便于快速查看各分群的数据基础。
    每个分群只保留一条记录（因为分群总样本数/坏客户数是分群级别的）。
    """
    if df_iv is None or df_iv.empty:
        return None

    needed_cols = ['分群', '分群总样本数', '分群坏客户数', '分群坏客户率']
    if not all(c in df_iv.columns for c in needed_cols):
        return None

    summary = (
        df_iv.groupby('分群')
        .agg({
            '分群总样本数': 'first',
            '分群坏客户数': 'first',
            '分群坏客户率': 'first',
            'IV可信度': lambda x: (x == '可信').sum(),
            '特征': 'count',
        })
        .rename(columns={
            'IV可信度': '可信IV数',
            '特征': '总特征数',
        })
    )
    summary['可信率'] = (summary['可信IV数'] / summary['总特征数'] * 100).round(1)

    # 统计不可信的数量
    suspect = (
        df_iv[df_iv['IV可信度'].str.contains('不可信', na=False)]
        .groupby('分群')['特征'].count()
        .rename('不可信IV数')
    )
    summary = summary.join(suspect, how='left')
    summary['不可信IV数'] = summary['不可信IV数'].fillna(0).astype(int)

    summary = summary.sort_values('分群坏客户率', ascending=False)
    return summary.reset_index()


def get_group_iv_recommendations(df_iv, group_name, top_n=10, min_iv=0.02, base_group='全量'):
    """
    获取指定分群下的高IV特征列表（用于风险提示）。
    增强：仅推荐可信度为"可信"或"参考"的特征，过滤掉"不可信"结论。
    """
    if df_iv is None or df_iv.empty:
        return None

    df_group = df_iv[(df_iv['分群'] == group_name) & pd.notna(df_iv['IV值'])].copy()
    if df_group.empty:
        return None

    # 过滤不可信结果（如有可信度列）
    if 'IV可信度' in df_group.columns:
        df_group = df_group[~df_group['IV可信度'].str.contains('不可信', na=False)]

    if min_iv is not None:
        df_group = df_group[df_group['IV值'] >= min_iv]

    df_group = df_group.sort_values('IV值', ascending=False).head(top_n)

    if base_group in df_iv['分群'].values:
        base = df_iv[df_iv['分群'] == base_group][['特征', 'IV值']].copy()
        base.columns = ['特征', f'{base_group}_IV值']
        df_group = df_group.merge(base, on='特征', how='left')
        df_group['IV差异'] = df_group['IV值'] - df_group[f'{base_group}_IV值']

    return df_group.reset_index(drop=True)


def calc_woe_table(df, feature, target=COL_TARGET, bins=10):
    """
    计算单个特征的 WOE 分箱表（增强版）。
    与 calc_iv 同口径：自适应分箱 + 零膨胀兜底 + WOE 截断，缺失值单独成「缺失」箱，
    占比分母为全部有目标的样本——各箱 iv 之和与 calc_iv 的 IV 一致。
    """
    df_temp = df.loc[df[target].notna(), [feature, target]]
    series = df_temp[feature]
    notna = series.notna()
    if notna.sum() < MIN_SAMPLES:
        return None

    total_good = (df_temp[target] == 0).sum()
    total_bad = (df_temp[target] == 1).sum()
    if total_good == 0 or total_bad == 0:
        return None

    if series[notna].nunique() <= 1:
        return None

    # 自适应分箱（按非缺失样本计）
    n_bad_notna = int((df_temp.loc[notna, target] == 1).sum())
    actual_bins = _adaptive_bins_for_woe(int(notna.sum()), n_bad_notna, default_bins=bins)

    if is_numeric_dtype(series):
        bin_series = _quantile_bins(series[notna], actual_bins).astype(str)
    else:
        bin_series = series[notna].astype(str)
    bin_series = bin_series.reindex(df_temp.index).fillna('缺失')

    grouped = df_temp.groupby(bin_series, sort=False)[target].agg(['count', 'sum'])
    if is_numeric_dtype(series):
        # 分箱标签是字符串，按箱内最小值排序，「缺失」箱排最后
        order = series.groupby(bin_series).min().sort_values(na_position='last').index
        grouped = grouped.loc[order]
    grouped.columns = ['total', 'bad']
    grouped['good'] = grouped['total'] - grouped['bad']

    # 防止除零
    grouped['good'] = grouped['good'].replace(0, 0.5)
    grouped['bad'] = grouped['bad'].replace(0, 0.5)

    grouped['pct_good'] = grouped['good'] / total_good
    grouped['pct_bad'] = grouped['bad'] / total_bad
    grouped['woe'] = np.log(grouped['pct_good'] / grouped['pct_bad'])

    # WOE 截断
    grouped['woe'] = grouped['woe'].clip(lower=-WOE_CAP, upper=WOE_CAP)

    grouped['iv'] = (grouped['pct_good'] - grouped['pct_bad']) * grouped['woe']
    grouped['bad_rate'] = grouped['bad'] / grouped['total']

    result = grouped.reset_index()
    # reset_index 后分箱列名在不同 pandas 版本下可能不是 "index"，
    # 统一将第一列重命名为 "bin"，避免 KeyError: ['bin'] not in index
    result = result.rename(columns={result.columns[0]: 'bin'})
    return result[['bin', 'total', 'bad', 'bad_rate', 'woe', 'iv']]


def calc_group_woe_table(df, feature, group_col, group_value, target=COL_TARGET, bins=10):
    """
    计算指定分群下某特征的 WOE 分箱表
    """
    if group_col not in df.columns:
        return None

    df_sub = df[df[group_col] == group_value]
    if len(df_sub) < MIN_SAMPLES or df_sub[target].sum() < MIN_BAD_SAMPLES:
        return None

    return calc_woe_table(df_sub, feature, target=target, bins=bins)
