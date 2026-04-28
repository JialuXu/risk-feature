# -*- coding: utf-8 -*-
import numpy as np
import pandas as pd

from .config import (
    MIN_SAMPLES, MIN_BAD_SAMPLES,
    IV_SUSPECT_THRESHOLD,
    IV_CREDIBILITY_MIN_BAD_STRICT,
    IV_CREDIBILITY_UNRELIABLE_IV_IF_LOW_BAD,
    IV_CREDIBILITY_LOW_SAMPLE_N,
    IV_CREDIBILITY_REFERENCE_IV,
    ADAPTIVE_BINS_SAMPLE_THRESHOLD, ADAPTIVE_BINS_BAD_THRESHOLD,
    ADAPTIVE_BINS_MIN, WOE_CAP,
    COL_TARGET, COL_SEGMENT_DIMS_DICT, COL_SEGMENT_IV_LIMITS,
)


def _adaptive_bins(n_samples, n_bad, default_bins=10):
    """
    自适应分箱数：根据样本量和坏客户数动态调整分箱数量。

    当样本量或坏客户数较少时，使用过多分箱会导致：
    1. 部分箱内坏客户数为 0，0.5 替代引入偏差
    2. WOE 出现极端值，IV 虚高（如 7~8）
    3. 结果不具统计稳健性

    自适应规则：
    - 确保每箱平均至少有 2~3 个坏客户
    - 确保每箱平均至少有 20 个样本
    - 取上述两个约束中更严格的那个
    """
    if n_samples >= ADAPTIVE_BINS_SAMPLE_THRESHOLD and n_bad >= ADAPTIVE_BINS_BAD_THRESHOLD:
        return default_bins

    # 按坏客户数约束：每箱至少 3 个坏客户
    bins_by_bad = max(ADAPTIVE_BINS_MIN, n_bad // 3)
    # 按总样本数约束：每箱至少 20 个样本
    bins_by_sample = max(ADAPTIVE_BINS_MIN, n_samples // 20)
    # 取最严格（最小）的分箱数，但不超过默认值
    adaptive = min(bins_by_bad, bins_by_sample, default_bins)

    return max(ADAPTIVE_BINS_MIN, adaptive)


def _assess_iv_reliability(iv_value, n_samples, n_bad, n_bins_actual):
    """
    评估 IV 值的可信度等级。

    可信度等级说明：
    - '可信': 样本量充足，IV 值处于合理范围
    - '参考': 样本量偏少或 IV 偏高，结论需谨慎
    - '不可信-样本不足': 坏客户过少，统计结论不稳定
    - '不可信-过拟合嫌疑': IV 超过阈值，大概率是分箱不稳定导致

    参数 n_bins_actual 保留与调用方一致，便于后续扩展分箱稳定性诊断（当前未参与判定）。
    """
    if pd.isna(iv_value):
        return '无法计算'

    # IV 超过可疑阈值 -> 过拟合嫌疑
    if iv_value > IV_SUSPECT_THRESHOLD:
        return '不可信-过拟合嫌疑'

    # 坏客户数不足 -> 样本不足
    if n_bad < IV_CREDIBILITY_MIN_BAD_STRICT:
        if iv_value > IV_CREDIBILITY_UNRELIABLE_IV_IF_LOW_BAD:
            return '不可信-样本不足'
        return '参考'

    # 有效样本量偏低：小样本下 IV 波动大，统一标记为参考
    if n_samples < IV_CREDIBILITY_LOW_SAMPLE_N:
        return '参考'

    if iv_value > IV_CREDIBILITY_REFERENCE_IV:
        return '参考'

    return '可信'


def calc_iv(df, feature, target, bins=10):
    """
    计算单个特征的 Information Value (IV)，并分离缺失值贡献

    原理：IV 衡量特征对目标变量的区分能力
    IV < 0.02: 无预测能力
    0.02 <= IV < 0.1: 弱预测能力
    0.1 <= IV < 0.3: 中等预测能力
    IV >= 0.3: 强预测能力
    IV > 2.0: 过高，需审查（通常是小样本分箱不稳定导致）

    改进点：
    1. 自适应分箱：根据样本量和坏客户数自动减少分箱数
    2. WOE 截断：限制极端 WOE 值，避免 IV 虚高
    3. 缺失值分离：将"是否缺失"的区分力与"数值大小"的区分力分开计算，
       避免缺失模式与违约的相关性污染 IV 结果
    4. 返回额外元信息：样本数、坏客户数、实际分箱数、IV 分解
    """
    meta = {'n_samples': 0, 'n_bad': 0, 'n_bins_actual': 0,
            'iv_missing': 0.0, 'iv_nonmissing': 0.0, 'n_missing': 0}
    try:
        # 先基于 target 非缺失的样本计算总体好/坏数
        df_with_target = df[df[target].notna()].copy()
        total_good_all = (df_with_target[target] == 0).sum()
        total_bad_all = (df_with_target[target] == 1).sum()

        if total_good_all == 0 or total_bad_all == 0:
            return np.nan, meta

        # 分离缺失值样本和非缺失样本
        mask_feat_notna = df_with_target[feature].notna()
        df_notna = df_with_target[mask_feat_notna].copy()
        df_na = df_with_target[~mask_feat_notna].copy()

        n_missing = len(df_na)
        n_nonmissing = len(df_notna)
        meta['n_missing'] = n_missing
        meta['n_samples'] = n_nonmissing  # 有效样本数（非缺失）

        if n_nonmissing < MIN_SAMPLES:
            return np.nan, meta

        total_bad_notna = int((df_notna[target] == 1).sum())
        meta['n_bad'] = total_bad_notna

        if total_bad_notna == 0 or (n_nonmissing - total_bad_notna) == 0:
            return np.nan, meta

        # --- 第1部分：缺失值箱的 IV 贡献 ---
        # 将缺失值作为单独一箱，计算其对总体 IV 的贡献
        iv_missing = 0.0
        if n_missing > 0:
            bad_na = (df_na[target] == 1).sum()
            good_na = n_missing - bad_na
            # 用 Laplace 平滑防止除零
            pct_good_na = max(good_na, 0.5) / total_good_all
            pct_bad_na = max(bad_na, 0.5) / total_bad_all
            woe_na = np.log(pct_good_na / pct_bad_na)
            woe_na = np.clip(woe_na, -WOE_CAP, WOE_CAP)
            iv_missing = (pct_good_na - pct_bad_na) * woe_na
            if np.isinf(iv_missing) or np.isnan(iv_missing):
                iv_missing = 0.0
        meta['iv_missing'] = round(iv_missing, 6)

        # --- 第2部分：非缺失样本的分箱 IV ---
        actual_bins = _adaptive_bins(n_nonmissing, total_bad_notna, default_bins=bins)

        if df_notna[feature].nunique() > actual_bins:
            df_notna['bin'] = pd.qcut(df_notna[feature], q=actual_bins, duplicates='drop')
        else:
            df_notna['bin'] = df_notna[feature]

        meta['n_bins_actual'] = df_notna['bin'].nunique()

        grouped = df_notna.groupby('bin', observed=False)[target].agg(['count', 'sum'])
        grouped.columns = ['total', 'bad']
        grouped['good'] = grouped['total'] - grouped['bad']

        grouped['good'] = np.where(grouped['good'] == 0, 0.5, grouped['good'])
        grouped['bad'] = np.where(grouped['bad'] == 0, 0.5, grouped['bad'])

        # 非缺失样本的好/坏占比以全体为分母（保持与缺失箱的可加性）
        grouped['pct_good'] = grouped['good'] / total_good_all
        grouped['pct_bad'] = grouped['bad'] / total_bad_all
        grouped['woe'] = np.log(grouped['pct_good'] / grouped['pct_bad'])
        grouped['woe'] = grouped['woe'].clip(lower=-WOE_CAP, upper=WOE_CAP)
        grouped['iv'] = (grouped['pct_good'] - grouped['pct_bad']) * grouped['woe']

        iv_nonmissing = grouped['iv'].sum()
        if np.isinf(iv_nonmissing):
            iv_nonmissing = 0.0
        meta['iv_nonmissing'] = round(iv_nonmissing, 6)

        iv_total = iv_missing + iv_nonmissing
        if np.isinf(iv_total):
            return np.nan, meta
        return iv_total, meta
    except Exception:
        return np.nan, meta


def _run_segment_iv(df_sub, feature_cols, group_name, results, target=COL_TARGET):
    """
    对指定子集计算所有特征的 IV 值，并附带样本元信息和可信度评估。
    内部辅助函数，避免重复代码。
    """
    n_total = len(df_sub)
    n_bad_total = int(df_sub[target].sum())
    bad_rate = n_bad_total / n_total if n_total > 0 else 0.0

    for feat in feature_cols:
        iv, meta = calc_iv(df_sub, feat, target)
        reliability = _assess_iv_reliability(
            iv, meta['n_samples'], meta['n_bad'], meta['n_bins_actual']
        )
        results.append({
            '分群': group_name,
            '特征': feat,
            'IV值': iv,
            'IV_缺失贡献': meta.get('iv_missing', 0.0),
            'IV_非缺失贡献': meta.get('iv_nonmissing', 0.0),
            '缺失样本数': meta.get('n_missing', 0),
            '分群总样本数': n_total,
            '分群坏客户数': n_bad_total,
            '分群坏客户率': round(bad_rate, 4),
            '特征有效样本数': meta['n_samples'],
            '特征坏客户数': meta['n_bad'],
            '实际分箱数': meta['n_bins_actual'],
            'IV可信度': reliability,
        })


def run_iv_analysis(df, feature_cols, target=COL_TARGET):
    """
    计算全量及分群 IV 值（增强版）

    改进点：
    1. 自适应分箱 - 小样本分群自动减少分箱数
    2. WOE 截断 - 防止极端 WOE 导致 IV 虚高
    3. 可信度评估 - 每条记录标注 IV 可信度等级
    4. 样本元信息 - 输出每个分群的总样本数/坏客户数/坏客户率
    """
    print("\n" + "=" * 60)
    print("IV 计算（增强版 - 含自适应分箱与可信度评估）")
    print("=" * 60)
    print(f"[CONFIG] 自适应分箱阈值: 总样本<{ADAPTIVE_BINS_SAMPLE_THRESHOLD} "
          f"或 坏客户<{ADAPTIVE_BINS_BAD_THRESHOLD} 时触发")
    print(f"[CONFIG] WOE 截断范围: [-{WOE_CAP}, +{WOE_CAP}]")
    print(f"[CONFIG] IV 可疑阈值: >{IV_SUSPECT_THRESHOLD}")

    results = []

    # 全量 IV
    print("[INFO] 计算全量 IV...")
    _run_segment_iv(df, feature_cols, '全量', results, target=target)

    # 按配置驱动的分群维度计算 IV
    _dim_display = {
        'industry': '行业', 'nature': '性质',
        'holding_type': '控股', 'branch': '分行', 'scale': '规模',
    }
    for dim_key, dim_col in COL_SEGMENT_DIMS_DICT.items():
        if dim_col not in df.columns:
            continue
        display = _dim_display.get(dim_key, dim_key)
        limit = COL_SEGMENT_IV_LIMITS.get(dim_key)
        print(f"[INFO] 按{dim_col}计算 IV...")
        unique_vals = df[dim_col].dropna().unique()
        if limit is not None:
            unique_vals = unique_vals[:limit]
        for val in unique_vals:
            df_sub = df[df[dim_col] == val]
            if len(df_sub) >= MIN_SAMPLES and df_sub[target].sum() >= MIN_BAD_SAMPLES:
                _run_segment_iv(df_sub, feature_cols, f'{display}_{val}', results, target=target)

    # 腰部企业（中等授信+高内评等级）
    if '是否腰部企业' in df.columns:
        print("[INFO] 腰部企业 IV 计算...")
        df_waist = df[df['是否腰部企业'] == 1]
        if len(df_waist) >= MIN_SAMPLES and df_waist[target].sum() >= MIN_BAD_SAMPLES:
            _run_segment_iv(df_waist, feature_cols, '腰部企业', results, target=target)

    # 中等授信非高评级
    if '是否中等授信非高评级' in df.columns:
        print("[INFO] 中等授信非高评级 IV 计算...")
        df_mid_nonhigh = df[df['是否中等授信非高评级'] == 1]
        if len(df_mid_nonhigh) >= MIN_SAMPLES and df_mid_nonhigh[target].sum() >= MIN_BAD_SAMPLES:
            _run_segment_iv(df_mid_nonhigh, feature_cols, '中等授信非高评级', results, target=target)

    if results:
        df_iv = pd.DataFrame(results)

        # 统计可信度分布
        reliability_counts = df_iv['IV可信度'].value_counts()
        print(f"\n[INFO] IV 计算完成，共 {len(df_iv)} 条记录")
        print("[INFO] IV 可信度分布:")
        for level, cnt in reliability_counts.items():
            print(f"       {level}: {cnt} 条 ({cnt/len(df_iv)*100:.1f}%)")

        # 列出可信度异常的分群
        suspect_groups = (
            df_iv[df_iv['IV可信度'].str.contains('不可信', na=False)]
            .groupby('分群')
            .agg({'特征': 'count', '分群坏客户数': 'first', '分群总样本数': 'first'})
            .rename(columns={'特征': '不可信特征数'})
        )
        if len(suspect_groups) > 0:
            print("\n[WARN] 以下分群的 IV 结果存在可信度问题:")
            for grp, row in suspect_groups.iterrows():
                print(f"       {grp}: 总样本={row['分群总样本数']}, "
                      f"坏客户={row['分群坏客户数']}, "
                      f"不可信特征数={row['不可信特征数']}")

        return df_iv
    return None
