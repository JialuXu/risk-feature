# -*- coding: utf-8 -*-
import json
import os
from datetime import datetime

import numpy as np
import pandas as pd

from .config import (
    OUTPUT_DIR,
    FINAL_OUTPUT_DIR,
    IV_SUSPECT_THRESHOLD,
    GSFC_RESULTS_EXPORT_PREFIX,
    GSFC_COMPREHENSIVE_CSV_BASENAME,
    GSFC_IV_COMPARE_CSV_BASENAME,
    GSFC_LLM_PROJECT_NAME,
    COL_TARGET,
)
from .report_insights import build_segment_summary
from .io_utils import ensure_dir


# =============================================================================
# 特征分类与IV评估工具函数
# =============================================================================

def get_feature_category(feature_name):
    """根据特征名称自动分类（工商变更/财务各维度）"""
    if '最近30天_' in feature_name or '近30天' in feature_name:
        return '工商变更-近30天'
    if '最近90天_' in feature_name or '近90天' in feature_name:
        return '工商变更-近90天'
    if '最近180天_' in feature_name or '近180天' in feature_name:
        return '工商变更-近180天'
    if '最近365天_' in feature_name or '近365天' in feature_name:
        return '工商变更-近365天'
    if '累计_' in feature_name:
        return '工商变更-累计'

    change_keywords = ['变更', '标记', '资本相关']
    if any(kw in feature_name for kw in change_keywords):
        return '工商变更-基础'

    credit_keywords = ['授信', '类信贷', '表内', '表外']
    if any(kw in feature_name for kw in credit_keywords):
        return '授信匹配度'

    balance_sheet = ['资产总计', '负债合计', '股东权益', '流动资产', '流动负债',
                     '非流动资产', '非流动负债', '货币资金', '应收账款', '存货',
                     '短期借款', '长期借款', '应付账款', '应付票据', '固定资产',
                     '无形资产', '长期股权投资', '实收资本', '资本公积', '盈余公积',
                     '未分配利润', '有息负债']
    if any(kw in feature_name for kw in balance_sheet):
        if not ('占比' in feature_name or '比率' in feature_name or '周转' in feature_name):
            return '财务-资产负债表'

    income_stmt = ['营业收入', '营业成本', '营业利润', '利润总额', '净利润',
                   '财务费用', '管理费用', '销售费用', '研发费用', '利息收入',
                   '利息支出', '税金及附加', '三项费用']
    if any(kw in feature_name for kw in income_stmt):
        if not ('率' in feature_name or '比' in feature_name):
            return '财务-利润表'

    cashflow = ['现金流', '经营活动', '投资活动', '筹资活动', '劳务收到', '劳务支付', '借款收到']
    if any(kw in feature_name for kw in cashflow):
        if '比' in feature_name or '率' in feature_name or '覆盖' in feature_name:
            return '财务-现金流安全'
        return '财务-现金流量表'

    solvency = ['流动比率', '速动比率', '现金比率', '资产负债率', '营运资金',
                '借款压力', '借款依赖', '权益乘数', '负债权益', '产权比率',
                '利息保障', '长期负债比率', '短期借款占']
    if any(kw in feature_name for kw in solvency):
        return '财务-偿债能力'

    asset_quality = ['占收入比', '占流动资产', '占资产比', '资产占比', '无形资产占',
                     '长期股权投资占', '非流动资产占', '流动资产占', '固定资产占',
                     '应收存货占', '流动负债占', '非流动负债占']
    if any(kw in feature_name for kw in asset_quality):
        return '财务-资产质量'

    efficiency = ['周转率', '周转', '资产收益质量', '应付账款占成本']
    if any(kw in feature_name for kw in efficiency):
        return '财务-经营效率'

    profitability = ['净利率', '毛利率', 'ROA', 'ROE', '利润率', '费用率',
                     '成本费用利润', '营业成本率', '研发投入', '管理费用率',
                     '销售费用率', '财务费用率', '现金含量', '净利润现金',
                     '占权益比', '盈余公积占', '经营现金净利润', '是否盈利']
    if any(kw in feature_name for kw in profitability):
        return '财务-盈利质量'

    cash_safety = ['现金储备', '货币资金短期', '筹资依赖', '投资现金流占',
                   '现金流借款', '现金流利息']
    if any(kw in feature_name for kw in cash_safety):
        return '财务-现金流安全'

    capital_structure = ['股东权益比', '实收资本占', '资本公积占', '实收资本借款']
    if any(kw in feature_name for kw in capital_structure):
        return '财务-资本结构'

    data_quality = ['数据完整', '核心指标完整', '资产负债异常']
    if any(kw in feature_name for kw in data_quality):
        return '数据质量'

    return '其他'


def _iv_prediction_level(iv):
    """IV值 -> 预测力等级（LLM报告用简短标签）"""
    if pd.isna(iv):
        return '无法计算'
    if iv > IV_SUSPECT_THRESHOLD:
        return '过高-需审查'
    if iv < 0.02:
        return '无预测能力'
    if iv < 0.1:
        return '弱'
    if iv < 0.3:
        return '中等'
    if iv < 0.5:
        return '强'
    return '极强-需审查'


_GROUP_PREFIX_MAP = {
    '行业_': '行业',
    '性质_': '性质',
    '控股_': '控股',
    '分行_': '分行',
}


def _parse_group_name(group_name):
    """从工商财务分析的分群名称中提取 (维度, 显示名称)"""
    for prefix, dim in _GROUP_PREFIX_MAP.items():
        if group_name.startswith(prefix):
            return dim, group_name
    if group_name == '全量':
        return '全量', '全量'
    if group_name in ('腰部企业', '非腰部企业', '中等授信非高评级'):
        return '授信规模', group_name
    return '其他', group_name


# =============================================================================
# 原有导出函数
# =============================================================================

def export_results(project_root, df_segment, df_univariate, df_lr, df_iv):
    """
    导出所有分析结果
    """
    print("\n" + "="*60)
    print("结果导出")
    print("="*60)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # 确保输出目录存在
    results_dir = os.path.join(project_root, OUTPUT_DIR)
    output_dir = os.path.join(project_root, FINAL_OUTPUT_DIR)
    ensure_dir(results_dir)
    ensure_dir(output_dir)

    exported_files = []

    # 1. 分群基础统计
    if df_segment is not None:
        path = os.path.join(
            results_dir, f'{GSFC_RESULTS_EXPORT_PREFIX}_分群基础统计_{timestamp}.csv')
        df_segment.to_csv(path, index=False, encoding='utf-8-sig')
        exported_files.append(path)
        print(f"[INFO] 导出: {path}")

    # 2. 单变量分析结果
    if df_univariate is not None:
        path = os.path.join(
            results_dir, f'{GSFC_RESULTS_EXPORT_PREFIX}_单变量分析_{timestamp}.csv')
        df_univariate.to_csv(path, index=False, encoding='utf-8-sig')
        exported_files.append(path)
        print(f"[INFO] 导出: {path}")

    # 3. 逻辑回归系数
    if df_lr is not None:
        path = os.path.join(
            results_dir, f'{GSFC_RESULTS_EXPORT_PREFIX}_逻辑回归系数_{timestamp}.csv')
        df_lr.to_csv(path, index=False, encoding='utf-8-sig')
        exported_files.append(path)
        print(f"[INFO] 导出: {path}")

    # 4. IV 值分析
    if df_iv is not None:
        path = os.path.join(
            results_dir, f'{GSFC_RESULTS_EXPORT_PREFIX}_IV值分析_{timestamp}.csv')
        df_iv.to_csv(path, index=False, encoding='utf-8-sig')
        exported_files.append(path)
        print(f"[INFO] 导出: {path}")

        # 透视表格式的 IV 结果（便于查看）
        iv_pivot = df_iv.pivot_table(index='特征', columns='分群', values='IV值', aggfunc='first')
        path_pivot = os.path.join(
            results_dir, f'{GSFC_RESULTS_EXPORT_PREFIX}_IV值透视表_{timestamp}.csv')
        iv_pivot.to_csv(path_pivot, encoding='utf-8-sig')
        exported_files.append(path_pivot)
        print(f"[INFO] 导出: {path_pivot}")

        # 导出 IV 可信度透视表（如有可信度列）
        if 'IV可信度' in df_iv.columns:
            iv_rel_pivot = df_iv.pivot_table(
                index='特征', columns='分群', values='IV可信度', aggfunc='first'
            )
            path_rel = os.path.join(
                results_dir, f'{GSFC_RESULTS_EXPORT_PREFIX}_IV可信度透视表_{timestamp}.csv')
            iv_rel_pivot.to_csv(path_rel, encoding='utf-8-sig')
            exported_files.append(path_rel)
            print(f"[INFO] 导出: {path_rel}")

            # 导出分群样本量汇总
            seg_cols = ['分群', '分群总样本数', '分群坏客户数', '分群坏客户率']
            if all(c in df_iv.columns for c in seg_cols):
                seg_summary = df_iv[seg_cols].drop_duplicates(subset='分群')
                seg_summary = seg_summary.sort_values('分群坏客户率', ascending=False)
                path_seg = os.path.join(
                    results_dir, f'{GSFC_RESULTS_EXPORT_PREFIX}_分群样本概况_{timestamp}.csv')
                seg_summary.to_csv(path_seg, index=False, encoding='utf-8-sig')
                exported_files.append(path_seg)
                print(f"[INFO] 导出: {path_seg}")

    # 5. 综合汇总表（输出到 output 目录）- 增强版
    if df_univariate is not None and df_iv is not None:
        print("[INFO] 生成综合汇总表...")

        # ===== 5.1 全量综合结果 =====
        univar_all = df_univariate[df_univariate['分群'] == '全量'][
            ['特征', '样本数', '相关系数', '相关P值', '好客户均值', '坏客户均值', '均值差异']
        ].copy()
        # 提取IV值及可信度（如有）
        iv_cols = ['特征', 'IV值']
        if 'IV可信度' in df_iv.columns:
            iv_cols.append('IV可信度')
        iv_all = df_iv[df_iv['分群'] == '全量'][iv_cols].copy()

        summary = univar_all.merge(iv_all, on='特征', how='outer')

        summary['特征类别'] = summary['特征'].apply(get_feature_category)

        # 添加腰部企业对比数据
        if '腰部企业' in df_univariate['分群'].values:
            univar_waist = df_univariate[df_univariate['分群'] == '腰部企业'][
                ['特征', '相关系数', '均值差异']
            ].copy()
            univar_waist.columns = ['特征', '腰部企业_相关系数', '腰部企业_均值差异']
            summary = summary.merge(univar_waist, on='特征', how='left')

        if '腰部企业' in df_iv['分群'].values:
            iv_waist = df_iv[df_iv['分群'] == '腰部企业'][['特征', 'IV值']].copy()
            iv_waist.columns = ['特征', '腰部企业_IV值']
            summary = summary.merge(iv_waist, on='特征', how='left')

        # 添加逻辑回归系数（如果有）
        if df_lr is not None and len(df_lr) > 0:
            lr_all = df_lr[df_lr['分群'] == '全量']
            if len(lr_all) > 0:
                coef_cols = [c for c in lr_all.columns if c not in ['分群', '样本数', '坏样本数', 'AUC']]
                if coef_cols:
                    lr_coef = lr_all[coef_cols].T.reset_index()
                    lr_coef.columns = ['特征', 'LR系数_全量']
                    summary = summary.merge(lr_coef, on='特征', how='left')

        # IV 预测能力等级（增强版：识别过拟合嫌疑）
        condlist = [
            summary['IV值'].isna(),
            summary['IV值'] > IV_SUSPECT_THRESHOLD,
            summary['IV值'] < 0.02,
            summary['IV值'] < 0.1,
            summary['IV值'] < 0.3,
            summary['IV值'] < 0.5
        ]
        choicelist = [
            '无法计算', '过高-需审查', '无预测能力', 
            '弱预测能力', '中等预测能力', '强预测能力'
        ]
        summary['预测能力等级'] = np.select(condlist, choicelist, default='极强-需审查')

        condlist_sig = [
            summary['相关P值'].isna(),
            summary['相关P值'] < 0.01,
            summary['相关P值'] < 0.05,
            summary['相关P值'] < 0.1
        ]
        choicelist_sig = ['', '***', '**', '*']
        summary['显著性'] = np.select(condlist_sig, choicelist_sig, default='')

        condlist_risk = [
            summary['相关系数'].isna(),
            summary['相关系数'] > 0,
            summary['相关系数'] < 0
        ]
        choicelist_risk = ['', '正向风险', '负向风险']
        summary['风险方向'] = np.select(condlist_risk, choicelist_risk, default='无关')

        col_order = ['特征类别', '特征', '风险方向', '显著性', '相关系数', '相关P值',
                     '好客户均值', '坏客户均值', '均值差异', 'IV值', '预测能力等级', 'IV可信度']

        if '腰部企业_相关系数' in summary.columns:
            col_order.extend(['腰部企业_相关系数', '腰部企业_均值差异'])
        if '腰部企业_IV值' in summary.columns:
            col_order.append('腰部企业_IV值')
        if 'LR系数_全量' in summary.columns:
            col_order.append('LR系数_全量')

        col_order = [c for c in col_order if c in summary.columns]
        summary = summary[col_order]

        summary = summary.sort_values(['特征类别', 'IV值'], ascending=[True, False])

        path = os.path.join(
            output_dir, f'{GSFC_COMPREHENSIVE_CSV_BASENAME}_{timestamp}.csv')
        summary.to_csv(path, index=False, encoding='utf-8-sig')
        exported_files.append(path)
        print(f"[INFO] 导出综合结果: {path}")

        # ===== 5.2 分群对比汇总表 =====
        key_groups = ['全量', '腰部企业']
        industry_groups = [g for g in df_iv['分群'].unique() if g.startswith('行业_')][:5]
        key_groups.extend(industry_groups)

        iv_compare = df_iv[df_iv['分群'].isin(key_groups)].pivot_table(
            index='特征', columns='分群', values='IV值', aggfunc='first'
        )

        if len(iv_compare) > 0:
            iv_compare = iv_compare.reset_index()
            iv_compare['特征类别'] = iv_compare['特征'].apply(get_feature_category)

            cols = ['特征类别', '特征'] + [c for c in iv_compare.columns if c not in ['特征类别', '特征']]
            iv_compare = iv_compare[cols]
            iv_compare = iv_compare.sort_values(['特征类别', '全量'] if '全量' in iv_compare.columns else ['特征类别'],
                                                ascending=[True, False])

            path_compare = os.path.join(
                output_dir, f'{GSFC_IV_COMPARE_CSV_BASENAME}_{timestamp}.csv')
            iv_compare.to_csv(path_compare, index=False, encoding='utf-8-sig')
            exported_files.append(path_compare)
            print(f"[INFO] 导出分群IV对比: {path_compare}")

    print(f"\n[INFO] 共导出 {len(exported_files)} 个文件")
    return exported_files


# =============================================================================
# LLM报告数据构建与导出（工商财务版）
# =============================================================================

def build_llm_report_data_gsfc(df, df_univariate, df_lr, df_iv, feature_cols):
    """
    构建面向LLM报告生成的三层结构化数据（工商财务版）

    将工商财务分析的扁平DataFrame结果提炼为：
      第1层 - 分析概览（overview）：全局元信息
      第2层 - 特征有效性汇总（feature_summary）：每个特征一行，集成IV/相关性/LR/稳定性
      第3层 - 分群画像（segment_profiles）：每个分群一行，含样本概况+模型表现+关键特征

    参数:
        df: 宽表原始数据
        df_univariate: 单变量分析结果 DataFrame (分群/特征/相关系数/...)
        df_lr: 逻辑回归结果 DataFrame (分群/样本数/坏样本数/AUC/各特征系数)
        df_iv: IV分析结果 DataFrame (分群/特征/IV值/IV可信度/分群总样本数/...)
        feature_cols: 当前使用的特征列表

    返回:
        dict: {overview, feature_summary, segment_profiles}
    """
    total = len(df)
    bad = int(df[COL_TARGET].sum())
    bad_rate = round(bad / total, 4) if total > 0 else 0

    # ===================== 分群信息预处理 =====================
    all_groups = set()
    if df_univariate is not None:
        all_groups.update(df_univariate['分群'].unique())
    if df_iv is not None:
        all_groups.update(df_iv['分群'].unique())
    if df_lr is not None:
        all_groups.update(df_lr['分群'].unique())

    dims_found = set()
    for g in all_groups:
        dim, _ = _parse_group_name(g)
        if dim not in ('全量', '其他'):
            dims_found.add(dim)

    # IV 可信度统计
    seg_summary_df = None
    n_segments = 0
    n_reliable = 0
    rel_warnings = []
    if df_iv is not None and 'IV可信度' in df_iv.columns:
        seg_summary_df = build_segment_summary(df_iv)
        if seg_summary_df is not None:
            n_segments = len(seg_summary_df)
            n_reliable = int((seg_summary_df['可信率'] >= 50).sum())
            for _, row in seg_summary_df.iterrows():
                if row['可信率'] < 50:
                    rel_warnings.append(
                        f"[告警] {row['分群']}: IV可信率仅 {row['可信率']}% "
                        f"(样本数={int(row['分群总样本数'])}, "
                        f"坏客户数={int(row['分群坏客户数'])})"
                    )

    # ===================== 第1层：分析概览 =====================
    feature_category_counts = {}
    for feat in feature_cols:
        cat = get_feature_category(feat)
        feature_category_counts[cat] = feature_category_counts.get(cat, 0) + 1
    feature_category_counts = dict(sorted(feature_category_counts.items(), key=lambda x: x[0]))

    overview = {
        '数据概况': {
            '总样本数': total,
            '坏客户数': bad,
            '坏客户率': bad_rate,
        },
        '分群维度': {
            '分群维度列表': sorted(dims_found),
            '分群维度数量': len(dims_found),
        },
        '特征集': {
            '特征数量': len(feature_cols),
            '特征类别统计': feature_category_counts,
            '有效特征数': 0,
        },
        '分析范围': {
            '参与分析的分群总数': n_segments,
            'IV可信率>=50%的分群数': n_reliable,
            'IV可信率<50%的分群数': n_segments - n_reliable,
        },
        '可信度告警': rel_warnings,
    }

    # ===================== 全量数据提取 =====================
    iv_all_map = {}
    iv_rel_map = {}
    iv_missing_map = {}
    if df_iv is not None:
        iv_all = df_iv[df_iv['分群'] == '全量']
        for _, r in iv_all.iterrows():
            iv_all_map[r['特征']] = r['IV值']
            iv_rel_map[r['特征']] = r.get('IV可信度', '')
            iv_miss = r.get('IV_缺失贡献', 0.0)
            iv_total = r['IV值']
            if pd.notna(iv_total) and iv_total > 0.02 and pd.notna(iv_miss):
                iv_missing_map[r['特征']] = round(iv_miss / iv_total, 4)
            else:
                iv_missing_map[r['特征']] = 0.0

    corr_all_map = {}
    pval_all_map = {}
    if df_univariate is not None:
        uv_all = df_univariate[df_univariate['分群'] == '全量']
        for _, r in uv_all.iterrows():
            corr_all_map[r['特征']] = r['相关系数']
            pval_all_map[r['特征']] = r['相关P值']

    # ===================== 可信分群集合 =====================
    reliable_groups = set()
    if seg_summary_df is not None:
        reliable_groups = set(
            seg_summary_df[seg_summary_df['可信率'] >= 50]['分群']
        )
    # 若可信分群为空，回退到全部非全量分群，避免测试/小样本环境下统计全空
    fallback_groups = set()
    for g in all_groups:
        if g != '全量':
            fallback_groups.add(g)
    corr_group_scope = reliable_groups if len(reliable_groups) > 0 else fallback_groups
    corr_scope_label = '可信分群(IV可信率>=50%)' if len(reliable_groups) > 0 else '降级口径: 全部非全量分群'

    # ===================== 跨分群相关系数统计（可信分群优先，必要时降级口径） =====================
    corr_stats = {}
    if df_univariate is not None:
        uv_non_all = df_univariate[
            (df_univariate['分群'] != '全量') &
            (df_univariate['分群'].isin(corr_group_scope))
        ]
        for feat in feature_cols:
            vals = uv_non_all[uv_non_all['特征'] == feat]['相关系数'].dropna().values
            if len(vals) > 0:
                corr_stats[feat] = {
                    'mean': float(np.mean(vals)),
                    'std': float(np.std(vals)),
                    'range': float(np.max(vals) - np.min(vals)),
                    'n_groups': len(vals),
                    'sign_consistent': bool(np.all(vals > 0) or np.all(vals < 0)),
                }

    # ===================== 跨分群LR系数统计（可信分群优先，必要时降级口径） =====================
    lr_stats = {}
    if df_lr is not None:
        lr_meta_cols = {'分群', '样本数', '坏样本数', 'AUC'}
        lr_feat_cols = [c for c in df_lr.columns if c not in lr_meta_cols]
        lr_non_all = df_lr[
            (df_lr['分群'] != '全量') &
            (df_lr['分群'].isin(corr_group_scope))
        ]
        for feat in lr_feat_cols:
            if feat in feature_cols:
                vals = lr_non_all[feat].dropna().values
                if len(vals) > 0:
                    lr_stats[feat] = {
                        'mean': float(np.mean(vals)),
                        'std': float(np.std(vals)),
                    }

    # ===================== 综合评级逻辑 =====================
    def _rate_feature(iv_val, corr_mean, sign_consistent):
        if iv_val >= 0.2 and sign_consistent:
            return '核心特征'
        if iv_val >= 0.1:
            return '重要特征'
        if iv_val >= 0.02 or (corr_mean is not None and abs(corr_mean) >= 0.05):
            return '辅助特征'
        return '无效特征'

    def _consistency_level(corr_range, sign_consistent):
        if sign_consistent:
            return '高'
        if corr_range is not None and corr_range < 0.15:
            return '高'
        if corr_range is not None and corr_range < 0.3:
            return '中'
        return '低'

    # ===================== 第2层：特征有效性汇总 =====================
    feat_rows = []
    all_features = list(iv_all_map.keys()) if iv_all_map else list(feature_cols)

    for feat in all_features:
        iv_val = iv_all_map.get(feat, 0)
        cs = corr_stats.get(feat, {})
        ls = lr_stats.get(feat, {})

        corr_mean = cs.get('mean')
        corr_range = cs.get('range')
        sign_consistent = cs.get('sign_consistent', False)

        miss_ratio = iv_missing_map.get(feat, 0.0)
        feat_rows.append({
            '特征名称': feat,
            '特征类别': get_feature_category(feat),
            '全局IV': round(iv_val, 4),
            'IV预测力': _iv_prediction_level(iv_val),
            'IV可信度': iv_rel_map.get(feat, ''),
            'IV缺失贡献占比': miss_ratio,
            '全局相关系数': round(corr_all_map[feat], 4) if feat in corr_all_map and pd.notna(corr_all_map[feat]) else None,
            '全局相关P值': round(pval_all_map[feat], 6) if feat in pval_all_map and pd.notna(pval_all_map[feat]) else None,
            '可信分群平均相关系数': round(corr_mean, 4) if corr_mean is not None else None,
            '可信分群相关系数极差': round(corr_range, 4) if corr_range is not None else None,
            '可信分群分析数': cs.get('n_groups', 0),
            '跨分群方向一致': sign_consistent,
            '跨分群一致性': _consistency_level(corr_range, sign_consistent),
            '可信分群平均LR系数': round(ls['mean'], 4) if ls else None,
            '综合评级': _rate_feature(iv_val, corr_mean, sign_consistent),
        })

    feature_summary = pd.DataFrame(feat_rows)
    if not feature_summary.empty:
        rating_order = {'核心特征': 0, '重要特征': 1, '辅助特征': 2, '无效特征': 3}
        feature_summary['_sort'] = feature_summary['综合评级'].map(rating_order)
        feature_summary = feature_summary.sort_values(
            ['_sort', '全局IV'], ascending=[True, False]
        ).drop(columns='_sort').reset_index(drop=True)

        # LLM上下文瘦身：移除无效特征与全空字段，仅保留核心信息
        feature_summary = feature_summary[feature_summary['综合评级'] != '无效特征'].copy()
        drop_cols = [
            '可信分群平均相关系数',
            '可信分群相关系数极差',
            '可信分群平均LR系数',
        ]
        feature_summary = feature_summary.drop(
            columns=[c for c in drop_cols if c in feature_summary.columns]
        ).reset_index(drop=True)

    overview['特征集']['有效特征数'] = int(len(feature_summary))
    corr_covered_features = int(len(corr_stats))
    lr_covered_features = int(len(lr_stats))
    feat_total = int(len(feature_cols)) if feature_cols is not None else 0
    overview['跨分群统计覆盖情况'] = {
        '相关性统计分群口径': corr_scope_label,
        '可信分群数量': int(len(reliable_groups)),
        '统计使用分群数量': int(len(corr_group_scope)),
        '相关性覆盖特征数': corr_covered_features,
        '相关性覆盖率': round(corr_covered_features / feat_total, 4) if feat_total > 0 else 0,
        'LR系数覆盖特征数': lr_covered_features,
        'LR系数覆盖率': round(lr_covered_features / feat_total, 4) if feat_total > 0 else 0,
    }

    # ===================== 第3层：分群画像 =====================
    seg_rows = []

    for group_name in sorted(all_groups):
        dim, display_name = _parse_group_name(group_name)

        # -- 样本元信息（优先从 df_iv 的分群元信息列获取）
        n_samples, n_bad, grp_bad_rate = 0, 0, 0.0
        if df_iv is not None:
            iv_grp = df_iv[df_iv['分群'] == group_name]
            if len(iv_grp) > 0 and '分群总样本数' in iv_grp.columns:
                n_samples = int(iv_grp['分群总样本数'].iloc[0])
                n_bad = int(iv_grp['分群坏客户数'].iloc[0])
                grp_bad_rate = round(float(iv_grp['分群坏客户率'].iloc[0]), 4)
        if n_samples == 0 and df_lr is not None:
            lr_row = df_lr[df_lr['分群'] == group_name]
            if len(lr_row) > 0:
                n_samples = int(lr_row['样本数'].iloc[0])
                n_bad = int(lr_row['坏样本数'].iloc[0])
                grp_bad_rate = round(n_bad / n_samples, 4) if n_samples > 0 else 0

        # -- 模型 AUC
        auc_val, auc_type = None, ''
        if df_lr is not None:
            lr_row = df_lr[df_lr['分群'] == group_name]
            if len(lr_row) > 0 and 'AUC' in lr_row.columns:
                auc_val = round(float(lr_row['AUC'].iloc[0]), 4)
                auc_type = '训练集'

        # -- IV 可信率
        iv_rel_rate = None
        if seg_summary_df is not None:
            seg_row = seg_summary_df[seg_summary_df['分群'] == group_name]
            if len(seg_row) > 0:
                iv_rel_rate = float(seg_row['可信率'].iloc[0])

        # -- Top3 相关性特征
        top3_corr_text = ''
        if df_univariate is not None:
            uv_grp = df_univariate[df_univariate['分群'] == group_name].copy()
            uv_grp = uv_grp[pd.notna(uv_grp['相关系数'])]
            if len(uv_grp) > 0:
                uv_grp = uv_grp.copy()
                uv_grp['_abs'] = uv_grp['相关系数'].abs()
                top3 = uv_grp.nlargest(3, '_abs')
                parts = []
                for _, r in top3.iterrows():
                    sign = '+' if r['相关系数'] > 0 else '-'
                    parts.append(f"{r['特征']}({sign}{abs(r['相关系数']):.3f})")
                top3_corr_text = ', '.join(parts)

        # -- Top3 IV 特征（优先可信级别）
        top3_iv_text = ''
        if df_iv is not None:
            iv_grp = df_iv[df_iv['分群'] == group_name]
            if len(iv_grp) > 0:
                iv_reliable = iv_grp[iv_grp['IV可信度'] == '可信'] if 'IV可信度' in iv_grp.columns else iv_grp
                top3_src = iv_reliable if len(iv_reliable) >= 3 else iv_grp
                top3_iv = top3_src.nlargest(3, 'IV值')
                parts = [f"{r['特征']}({r['IV值']:.3f})" for _, r in top3_iv.iterrows()]
                top3_iv_text = ', '.join(parts)

        # -- 风险特征概要（自动生成的一句话描述）
        risk_parts = []
        if n_samples > 0 and grp_bad_rate > 0:
            if grp_bad_rate > bad_rate * 2:
                risk_parts.append(
                    f"坏客户率({grp_bad_rate:.1%})显著高于整体({bad_rate:.1%})")
            elif grp_bad_rate < bad_rate * 0.5:
                risk_parts.append(
                    f"坏客户率({grp_bad_rate:.1%})显著低于整体({bad_rate:.1%})")

        if auc_val is not None:
            if auc_val < 0.6:
                risk_parts.append("模型区分力有限")
            elif auc_val >= 0.75:
                risk_parts.append(f"模型区分力较好(AUC={auc_val:.3f})")

        has_corr = False
        if df_univariate is not None:
            uv_grp = df_univariate[df_univariate['分群'] == group_name]
            uv_grp = uv_grp[pd.notna(uv_grp['相关系数'])]
            if len(uv_grp) > 0:
                has_corr = True
                uv_grp = uv_grp.copy()
                uv_grp['_abs'] = uv_grp['相关系数'].abs()
                top2 = uv_grp.nlargest(2, '_abs')
                corr_added = False
                for _, r in top2.iterrows():
                    cval = r['相关系数']
                    if abs(cval) >= 0.08:
                        direction = '越高风险越高' if cval > 0 else '越高风险越低'
                        stable = ''
                        if df_lr is not None:
                            lr_row = df_lr[df_lr['分群'] == group_name]
                            if len(lr_row) > 0 and r['特征'] in lr_row.columns:
                                lr_val = lr_row[r['特征']].iloc[0]
                                if pd.notna(lr_val) and (cval > 0) == (lr_val > 0):
                                    stable = '(稳健)'
                        risk_parts.append(f"{r['特征']}{direction}{stable}")
                        corr_added = True
                if not corr_added:
                    max_abs = uv_grp['_abs'].max()
                    risk_parts.append(f"特征相关性均较弱（最大|r|={max_abs:.3f}<0.08），无显著线性风险特征")
        if not has_corr and n_samples > 0:
            risk_parts.append("样本不足，未进行相关性分析")

        risk_text = '; '.join(risk_parts) if risk_parts else '数据不足，无法分析'

        seg_rows.append({
            '分群维度': dim,
            '分群名称': display_name,
            '样本数': n_samples,
            '坏客户数': n_bad,
            '坏客户率': grp_bad_rate,
            '模型AUC': auc_val,
            'AUC类型': auc_type,
            'IV可信率%': iv_rel_rate,
            'Top3风险特征_相关性': top3_corr_text,
            'Top3预测特征_IV': top3_iv_text,
            '风险特征概要': risk_text,
        })

    segment_profiles = pd.DataFrame(seg_rows)

    return {
        'overview': overview,
        'feature_summary': feature_summary,
        'segment_profiles': segment_profiles,
    }


def _df_to_json_records(df):
    """将 DataFrame 转为 JSON 可序列化的记录列表"""
    records = []
    if df is None or df.empty:
        return records
    for _, row in df.iterrows():
        item = {}
        for col in df.columns:
            val = row[col]
            if pd.isna(val):
                continue
            elif isinstance(val, (np.integer,)):
                item[col] = int(val)
            elif isinstance(val, (np.floating,)):
                item[col] = round(float(val), 4)
            elif isinstance(val, (np.bool_,)):
                item[col] = bool(val)
            else:
                item[col] = val
        records.append(item)
    return records


def export_llm_results_gsfc(project_root, llm_data):
    """
    导出工商财务LLM报告数据（JSON + CSV）

    参数:
        project_root: 项目根目录
        llm_data: build_llm_report_data_gsfc() 的返回值

    返回:
        exported: 导出的文件路径列表
    """
    pname = GSFC_LLM_PROJECT_NAME
    out_dir = os.path.join(project_root, FINAL_OUTPUT_DIR)
    ensure_dir(out_dir)

    exported = []

    # 1. JSON - 完整三层结构
    output = {
        '分析概览': llm_data['overview'],
        '特征有效性汇总': _df_to_json_records(llm_data['feature_summary']),
        '分群画像': _df_to_json_records(llm_data['segment_profiles']),
    }

    json_path = os.path.join(out_dir, f'{pname}_LLM报告数据.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    exported.append(json_path)
    print(f"  -> {pname}_LLM报告数据.json")

    # 2. 特征有效性汇总 CSV
    feat_df = llm_data.get('feature_summary')
    if feat_df is not None and not feat_df.empty:
        csv_path = os.path.join(out_dir, f'{pname}_LLM_特征有效性汇总.csv')
        feat_df.to_csv(csv_path, index=False, encoding='utf-8-sig')
        exported.append(csv_path)
        print(f"  -> {pname}_LLM_特征有效性汇总.csv ({len(feat_df)} 行)")

    # 3. 分群画像 CSV
    seg_df = llm_data.get('segment_profiles')
    if seg_df is not None and not seg_df.empty:
        csv_path = os.path.join(out_dir, f'{pname}_LLM_分群画像.csv')
        seg_df.to_csv(csv_path, index=False, encoding='utf-8-sig')
        exported.append(csv_path)
        print(f"  -> {pname}_LLM_分群画像.csv ({len(seg_df)} 行)")

    return exported
