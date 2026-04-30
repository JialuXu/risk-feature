# -*- coding: utf-8 -*-
"""
风险特征触碰提取

核心函数：
    extract_triggers(df, features, target_col, id_col, project_name, output_dir, verbose)
        -> (df_wide, df_long, df_threshold)

    compute_thresholds(df, features, target_col)  -> dict
    evaluate_triggers(df, features, thresholds, id_col, target_col)  -> (df_wide, df_long)
    build_threshold_table(features, thresholds)  -> pd.DataFrame
"""
import os
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from .config import (
    RISK_FEATURES,
    RISK_FEATURES_GSFC,
    MIN_DEFAULT_FEATURE_MATCH_RATE,
)


def _resolve_scope_mask(df: pd.DataFrame, scope: Union[str, Dict, None]) -> pd.Series:
    """解析 feature 的 scope 字段，返回布尔掩码（True=该客户落入触发范围）。

    支持 4 种形态：
        'full' / None                          → 全量
        'waist'                                → 等价 {"dim": "是否腰部企业", "value": 1}
        {"dim": "X", "value": "Y"}             → df[X] == Y
        {"dim": "X", "values": ["Y1","Y2"]}    → df[X].isin([...])
    若 dim 不在宽表列中，返回全 True 并不阻断（与现状一致：当前 waist 写法在缺列时也是放行）。
    """
    if scope is None or scope == 'full':
        return pd.Series(True, index=df.index)

    if scope == 'waist':
        scope = {'dim': '是否腰部企业', 'value': 1}

    if isinstance(scope, dict):
        dim = scope.get('dim')
        if not dim or dim not in df.columns:
            return pd.Series(True, index=df.index)
        if 'values' in scope:
            return df[dim].isin(scope['values'])
        if 'value' in scope:
            return df[dim] == scope['value']

    return pd.Series(True, index=df.index)


def _format_scope_label(scope: Union[str, Dict, None]) -> str:
    """把 scope 字段格式化成人类可读的「适用范围」字符串。"""
    if scope is None or scope == 'full':
        return '全量'
    if scope == 'waist':
        return '腰部企业'
    if isinstance(scope, dict):
        dim = scope.get('dim', '?')
        if 'values' in scope:
            return f"{dim}∈{list(scope['values'])}"
        if 'value' in scope:
            return f"{dim}={scope['value']}"
    return str(scope)


def _get_feature_iv(feat: Dict[str, Any]) -> float:
    """根据 scope 选择应使用的 IV 值。仅 scope='waist' 走 iv_waist 兼容分支。"""
    if feat.get('scope') == 'waist':
        return feat.get('iv_waist', feat['iv'])
    return feat['iv']


def _check_feature_match_rate(
    features: List[Dict],
    df: pd.DataFrame,
    is_using_default: bool,
    verbose: bool = True,
) -> None:
    """检查 features 与宽表的列匹配率；用默认值且匹配率过低时抛 RuntimeError。"""
    n_total = len(features)
    if n_total == 0:
        return
    matched = [f for f in features if f['source_col'] in df.columns]
    missing = [f for f in features if f['source_col'] not in df.columns]
    rate = len(matched) / n_total

    if verbose:
        prefix = '[默认特征]' if is_using_default else '[自定义特征]'
        print(f"{prefix} 共 {n_total} 个，宽表匹配 {len(matched)} 个 ({rate*100:.1f}%)")
        if missing:
            sample = [f['source_col'] for f in missing[:5]]
            print(f"    缺失列示例: {sample}{'...' if len(missing) > 5 else ''}")

    if is_using_default and rate < MIN_DEFAULT_FEATURE_MATCH_RATE:
        sample = [f['source_col'] for f in missing[:5]]
        raise RuntimeError(
            f"默认特征 RISK_FEATURES_GSFC 与当前宽表不匹配："
            f"{len(matched)}/{n_total} 列匹配 ({rate*100:.1f}%)，"
            f"低于阈值 {MIN_DEFAULT_FEATURE_MATCH_RATE*100:.0f}%。\n"
            f"  缺失列示例: {sample}\n"
            f"  → 请通过 extract_triggers(features=...) 或 CLI --features-file 注入项目专属特征。"
        )


def compute_thresholds(
    df: pd.DataFrame,
    features: List[Dict],
    target_col: str = 'is_bad',
) -> Dict:
    """
    为每个特征计算触碰阈值。

    优先级：
    1. explicit_threshold（报告中明确给出）
    2. 坏客户均值——positive 方向取 >=, negative 方向取 <=
    3. 兜底：全量中位数（好/坏有效样本不足时）
    """
    thresholds = {}
    for feat in features:
        col = feat['source_col']
        name = feat['report_name']

        if col not in df.columns:
            thresholds[name] = None
            continue

        if 'explicit_threshold' in feat:
            op, val = feat['explicit_threshold']
            thresholds[name] = {'operator': op, 'value': val, 'source': '报告明确阈值'}
            continue

        series = pd.to_numeric(df[col], errors='coerce')
        good_vals = series[df[target_col] == 0].dropna()
        bad_vals = series[df[target_col] == 1].dropna()

        if len(good_vals) < 10 or len(bad_vals) < 5:
            median_val = series.dropna().median()
            op = '>=' if feat['risk_direction'] == 'positive' else '<='
            thresholds[name] = {
                'operator': op,
                'value': median_val,
                'source': '全量中位数(好/坏样本不足)',
            }
            continue

        good_mean = good_vals.mean()
        bad_mean = bad_vals.mean()
        op = '>=' if feat['risk_direction'] == 'positive' else '<='
        thresholds[name] = {
            'operator': op,
            'value': bad_mean,
            'source': f'坏客户均值(好:{good_mean:.4g}, 坏:{bad_mean:.4g})',
            'good_mean': good_mean,
            'bad_mean': bad_mean,
        }

    return thresholds


def evaluate_triggers(
    df: pd.DataFrame,
    features: List[Dict],
    thresholds: Dict,
    id_col: str = '客户编号',
    target_col: str = 'is_bad',
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    对每个客户、每个特征评估是否触碰风险阈值。

    返回:
      df_wide : 宽表（每行一客户）含特征值列、触碰标记列、汇总统计
      df_long : 长表（仅保留触碰记录，每行一条 客户-特征 记录）
    """
    info_cols = [
        c for c in ['所属分行', '客户性质', '控股类型', '所属行业', '行业大类',
                    '企业规模', '客户分层', '赛道', '是否腰部企业']
        if c in df.columns
    ]

    result = df[[id_col] + info_cols + [target_col]].copy()

    trigger_count = pd.Series(0, index=df.index)
    trigger_names = pd.Series('', index=df.index, dtype=str)
    category_counts: Dict[str, pd.Series] = {}

    _OPS = {'>': lambda s, v: s > v, '>=': lambda s, v: s >= v,
            '<': lambda s, v: s < v, '<=': lambda s, v: s <= v}

    for feat in features:
        col = feat['source_col']
        name = feat['report_name']
        threshold_info = thresholds.get(name)

        values = pd.to_numeric(df.get(col), errors='coerce') if col in df.columns else pd.Series(np.nan, index=df.index)
        result[f'{name}_值'] = values

        if col not in df.columns or threshold_info is None:
            result[f'{name}_触碰'] = np.nan
            continue

        op_fn = _OPS.get(threshold_info['operator'])
        triggered = op_fn(values, threshold_info['value']) & values.notna() if op_fn else pd.Series(False, index=df.index)

        # 应用 scope 维度筛选（'full' 全量 / 'waist' 腰部 / dict 通用维度）
        triggered = triggered & _resolve_scope_mask(df, feat.get('scope', 'full'))

        result[f'{name}_触碰'] = triggered.astype(int).where(values.notna(), np.nan)

        trigger_count += triggered.astype(int)

        cat = feat['category']
        category_counts.setdefault(cat, pd.Series(0, index=df.index))
        category_counts[cat] += triggered.astype(int)

        for idx in triggered[triggered].index:
            sep = '; ' if trigger_names.at[idx] else ''
            trigger_names.at[idx] += sep + name

    result['触碰特征总数'] = trigger_count

    # IV 加权风险得分
    iv_score = pd.Series(0.0, index=df.index)
    total_iv = 0.0
    for feat in features:
        name = feat['report_name']
        tc = f'{name}_触碰'
        if tc not in result.columns:
            continue
        iv_val = _get_feature_iv(feat)
        iv_score += result[tc].fillna(0) * iv_val
        total_iv += iv_val
    result['IV加权风险得分'] = (iv_score / total_iv * 100).round(2) if total_iv > 0 else 0.0

    # 各类别触碰数（合并同前缀）
    seen_short: Dict[str, str] = {}
    for cat, counts in category_counts.items():
        short = cat.split('-')[0] if '-' in cat else cat
        col_name = f'触碰数_{short}'
        if col_name not in result.columns:
            result[col_name] = counts
            seen_short[col_name] = cat
        else:
            result[col_name] = result[col_name] + counts

    result['触碰特征清单'] = trigger_names
    result = result.sort_values('IV加权风险得分', ascending=False)

    # 构建长表
    long_records = []
    for feat in features:
        name = feat['report_name']
        val_col = f'{name}_值'
        trigger_col = f'{name}_触碰'
        if val_col not in result.columns:
            continue

        mask = result[trigger_col] == 1
        if mask.sum() == 0:
            continue

        sub = result.loc[mask, [id_col] + info_cols + [target_col, val_col]].copy()
        sub = sub.rename(columns={val_col: '特征值'})
        sub['特征名称'] = name
        sub['特征类别'] = feat['category']
        sub['全量IV'] = feat['iv']
        sub['风险方向'] = '正向(值越大风险越高)' if feat['risk_direction'] == 'positive' else '负向(值越小风险越高)'
        sub['适用范围'] = _format_scope_label(feat.get('scope', 'full'))
        t = thresholds.get(name, {})
        sub['触碰阈值'] = f"{t.get('operator', '')}{t.get('value', '')}"
        sub['阈值来源'] = t.get('source', '')
        long_records.append(sub)

    df_long = pd.concat(long_records, ignore_index=True) if long_records else pd.DataFrame()
    return result, df_long


def build_threshold_table(features: List[Dict], thresholds: Dict) -> pd.DataFrame:
    """构建阈值说明表，供审计与业务解读使用。"""
    rows = []
    for feat in features:
        name = feat['report_name']
        t = thresholds.get(name)
        base = {
            '特征名称': name,
            '源数据列': feat['source_col'],
            '特征类别': feat['category'],
            '全量IV': feat['iv'],
            '风险方向': '正向' if feat['risk_direction'] == 'positive' else '负向',
            '适用范围': _format_scope_label(feat.get('scope', 'full')),
        }
        if t is None:
            base.update({'触碰条件': '(列不存在)', '阈值来源': '-', '好客户均值': '-', '坏客户均值': '-'})
        else:
            val_str = f"{t['value']:.6g}" if isinstance(t['value'], (int, float)) else str(t['value'])
            base.update({
                '触碰条件': f"{t['operator']} {val_str}",
                '阈值来源': t.get('source', ''),
                '好客户均值': f"{t['good_mean']:.4g}" if isinstance(t.get('good_mean'), (int, float)) else '-',
                '坏客户均值': f"{t['bad_mean']:.4g}" if isinstance(t.get('bad_mean'), (int, float)) else '-',
            })
        rows.append(base)
    return pd.DataFrame(rows)


def extract_triggers(
    df: pd.DataFrame,
    features: Optional[List[Dict]] = None,
    target_col: str = 'is_bad',
    id_col: str = '客户编号',
    project_name: str = '风险触碰分析',
    output_dir: Optional[str] = None,
    verbose: bool = True,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    主入口：对宽表执行风险特征触碰提取，并将结果落盘。

    参数:
        df          : 已合并特征工程后的宽表（需含 target_col）
        features    : 风险特征配置列表，None 则使用 RISK_FEATURES 默认值
        target_col  : 坏客户标记列名
        id_col      : 主键列名
        project_name: 输出文件名前缀
        output_dir  : 输出目录，None 时自动定位到 risk-feature-pipeline/output/
        verbose     : 是否打印过程日志

    返回:
        df_wide      : 宽表（每行一客户）
        df_long      : 长表（仅触碰记录）
        df_threshold : 阈值说明表
    """
    is_using_default = features is None
    if features is None:
        features = RISK_FEATURES_GSFC

    if output_dir is None:
        from risk_pipeline.paths import output_dir as _output_dir_for
        output_dir = _output_dir_for(project_name)
    from risk_pipeline.paths import ensure_writable_dir
    ensure_writable_dir(output_dir)

    if verbose:
        print(f"\n{'=' * 70}")
        print(f"风险特征触碰提取 — {project_name}")
        print(f"{'=' * 70}")
        n_bad = int(df[target_col].sum()) if target_col in df.columns else 0
        print(f"[INFO] 宽表: {len(df)} 行, {len(df.columns)} 列  坏客户: {n_bad} ({n_bad/len(df)*100:.2f}%)")

    # 检查特征匹配率：默认特征 + 匹配率 < MIN_DEFAULT_FEATURE_MATCH_RATE → 抛 RuntimeError
    _check_feature_match_rate(features, df, is_using_default=is_using_default, verbose=verbose)

    # 计算阈值
    thresholds = compute_thresholds(df, features, target_col=target_col)

    # 评估触碰
    df_wide, df_long = evaluate_triggers(df, features, thresholds, id_col=id_col, target_col=target_col)

    # 构建阈值说明表
    df_threshold = build_threshold_table(features, thresholds)

    # 落盘
    wide_path = os.path.join(output_dir, f'{project_name}_风险触碰明细_宽表.csv')
    long_path = os.path.join(output_dir, f'{project_name}_风险触碰明细_长表.csv')
    thr_path = os.path.join(output_dir, f'{project_name}_触碰阈值说明.csv')

    df_wide.to_csv(wide_path, index=False, encoding='utf-8-sig')
    df_long.to_csv(long_path, index=False, encoding='utf-8-sig')
    df_threshold.to_csv(thr_path, index=False, encoding='utf-8-sig')

    if verbose:
        print(f"\n[OUTPUT] 宽表: {wide_path}  ({len(df_wide)} 客户)")
        n_triggered = (df_wide['触碰特征总数'] > 0).sum()
        print(f"         至少触碰1个特征: {n_triggered} 户 ({n_triggered/len(df_wide)*100:.1f}%)")
        print(f"[OUTPUT] 长表: {long_path}  ({len(df_long)} 条触碰记录)")
        print(f"[OUTPUT] 阈值说明: {thr_path}")

        _print_summary(df_wide, features, target_col)

    return df_wide, df_long, df_threshold


def _print_summary(df_wide: pd.DataFrame, features: List[Dict], target_col: str) -> None:
    """打印触碰统计摘要。"""
    print(f"\n{'=' * 70}")
    print("触碰统计摘要")
    print(f"{'=' * 70}")

    # 各特征触碰率
    print(f"\n{'特征名称':<25s} {'触碰客户数':>8s} {'触碰率':>7s} {'坏客户触碰率':>10s}")
    print('-' * 55)
    for feat in features:
        name = feat['report_name']
        tc = f'{name}_触碰'
        if tc not in df_wide.columns:
            continue
        n_total = df_wide[tc].notna().sum()
        n_hit = (df_wide[tc] == 1).sum()
        n_bad_hit = ((df_wide[tc] == 1) & (df_wide[target_col] == 1)).sum()
        n_bad_total = (df_wide[tc].notna() & (df_wide[target_col] == 1)).sum()
        hit_rate = n_hit / n_total * 100 if n_total > 0 else 0
        bad_rate = n_bad_hit / n_bad_total * 100 if n_bad_total > 0 else 0
        print(f"{name:<25s} {n_hit:>8d} {hit_rate:>6.1f}% {bad_rate:>9.1f}%")

    # 好/坏客户平均触碰数与得分
    good_avg = df_wide.loc[df_wide[target_col] == 0, '触碰特征总数'].mean()
    bad_avg = df_wide.loc[df_wide[target_col] == 1, '触碰特征总数'].mean()
    good_score = df_wide.loc[df_wide[target_col] == 0, 'IV加权风险得分'].mean()
    bad_score = df_wide.loc[df_wide[target_col] == 1, 'IV加权风险得分'].mean()

    print(f"\n  好客户 — 平均触碰数: {good_avg:.1f}  平均IV得分: {good_score:.2f}")
    print(f"  坏客户 — 平均触碰数: {bad_avg:.1f}  平均IV得分: {bad_score:.2f}")
    if good_score > 0:
        print(f"  得分差异: {bad_score/good_score:.2f}x")

    # 按IV加权得分分段
    print("\n[按IV加权风险得分分段]")
    bins = [0, 5, 10, 15, 20, 30, 50, 100]
    labels = ['0-5', '5-10', '10-15', '15-20', '20-30', '30-50', '50+']
    segments = pd.cut(df_wide['IV加权风险得分'], bins=bins, labels=labels, right=True)
    for label in labels:
        mask = segments == label
        n = mask.sum()
        if n == 0:
            continue
        n_bad = (mask & (df_wide[target_col] == 1)).sum()
        print(f"  得分 {label:>5s}: {n:>5d} 户  坏客户率 {n_bad/n*100:>5.1f}%")
