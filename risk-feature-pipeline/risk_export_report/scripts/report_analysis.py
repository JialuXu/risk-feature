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

from .config import (
    CREDIT_CONFIG,
    pipeline_paths,
    CREDIT_LLM_REPORT_GOAL_TEMPLATE,
    SAMPLE_THRESHOLDS,
    COL_TARGET,
)
from .io_utils import ensure_dir
from risk_core.column_mapper import ColumnMapper

_mapper = ColumnMapper()
from risk_mining.analysis.iv_core import iv_power_label
from .report_insights import rate_feature

warnings.filterwarnings('ignore')

# 从配置中提取阈值常量
_T = SAMPLE_THRESHOLDS


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

def export_results(project_root, results, project_name=None, output_subdir=None,
                   results_base=None, output_base=None):
    """
    导出全部分析结果到CSV

    参数:
        project_root:  项目根目录
        results:       dict，包含各步骤分析结果
        project_name:  可选的项目名称前缀，默认使用 CREDIT_CONFIG['project_name']
        output_subdir: 结果目录下的子目录名称，默认使用 timestamp
        results_base:  data/results 级别的相对路径，None → pipeline_paths('credit')['results_rel']
        output_base:   output 级别的相对路径，       None → pipeline_paths('credit')['output_rel']

    返回:
        exported: 导出的文件列表
    """
    from datetime import datetime

    pname = project_name or results.get('project_name') or CREDIT_CONFIG['project_name']
    subdir = output_subdir or results.get('output_subdir') or datetime.now().strftime('%Y%m%d_%H%M')

    _results_base = results_base or pipeline_paths('credit')['results_rel']
    _output_base  = output_base  or pipeline_paths('credit')['output_rel']

    out_dir = os.path.join(project_root, _output_base, subdir)
    res_dir = os.path.join(project_root, _results_base, subdir)
    ensure_dir(out_dir)
    ensure_dir(res_dir)

    exported = []

    # 列名归一化（统一对外列名：特征 / 分群维度 / 分群名称；详见 docs/SCHEMA.md）
    _EXPORT_COLUMN_RENAMES = {
        '特征名称': '特征',
        '分群值': '分群名称',
    }

    def _normalize_export_cols(df):
        if df is None or df.empty:
            return df
        cols_to_rename = {old: new for old, new in _EXPORT_COLUMN_RENAMES.items() if old in df.columns}
        if cols_to_rename:
            df = df.rename(columns=cols_to_rename)
        return df

    def _save(df, filename, directory=res_dir):
        if df is not None and not df.empty:
            df = _normalize_export_cols(df)
            path = os.path.join(directory, filename)
            df.to_csv(path, index=False, encoding='utf-8-sig')
            exported.append(filename)
            print(f"  -> {filename} ({len(df)} 行)")

    # 1. 全量IV分析结果（A5：拆分为「_全量」+「_分群」两份；旧文件名 `_IV分析结果.csv`/`_IV值分析.csv` 仍写一份兼容副本）
    iv_full = results.get('iv_full')
    if iv_full is not None and not iv_full.empty:
        if '分群' in iv_full.columns:
            iv_full_export = iv_full[iv_full['分群'] == '全量'].copy()
        else:
            iv_full_export = iv_full
        _save(iv_full_export, f'{pname}_IV分析结果_全量.csv')
        # 兼容副本（一个版本后移除）
        _save(iv_full_export.copy(), f'{pname}_IV分析结果.csv')

    # 2. 特征风险相关性（分群相关系数 + 元信息）
    corr_exports = results.get('corr_exports')
    if corr_exports is not None:
        _save(corr_exports, f'{pname}_特征风险相关性.csv')

    # 3. 逻辑回归系数
    lr_exports = results.get('lr_exports')
    if lr_exports is not None:
        _save(lr_exports, f'{pname}_逻辑回归系数.csv')

    # 4. 分群IV值明细（A5：新名 _IV分析结果_分群.csv；旧名 _IV值分析.csv 保留兼容副本）
    iv_group = results.get('iv_group_all')
    _save(iv_group, f'{pname}_IV分析结果_分群.csv')
    if iv_group is not None and not iv_group.empty:
        _save(iv_group.copy(), f'{pname}_IV值分析.csv')

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
        except Exception as e:
            print(f"  [警告] IV 透视表导出失败: {e}")

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

    # 衍生预测能力标签（口径见 iv_core.iv_power_label）
    if '预测能力' not in df.columns:
        df['预测能力'] = df['iv_all'].apply(iv_power_label)

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
            iv_full_df['预测能力'] = iv_full_df['IV值'].apply(iv_power_label)

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
    # 综合评级：强度 + 跨分群稳定性（唯一实现见 report_insights.rate_feature）
    def _rate_feature(iv_val, corr_mean, corr_range, sign_consistent):
        return rate_feature(iv_val, corr_mean, sign_consistent)

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
        _base = output_base or pipeline_paths('credit')['output_rel']
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
