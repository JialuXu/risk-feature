# -*- coding: utf-8 -*-
"""
规则挖掘编排：分群挖掘 + 导出 CSV + LLM JSON 节点构建

核心函数：
    mine_rules_full(df, feature_cols, target)          # 全样本 + 评估 + 稳定性
    rules_by_group(df, segment_col, feature_cols, target)  # 分群挖掘
    export_rules(rules_df, project_name, output_dir)        # CSV 导出
    build_llm_rules_payload(rules_df)                       # LLM JSON 节点
"""
import re
from pathlib import Path
from typing import List, Optional, Dict, Union
import pandas as pd

from .config import (
    SAMPLE_THRESHOLDS,
    FINAL_OUTPUT_DIR,
)
from .rule_extraction import mine_rules
from .rule_evaluation import evaluate_rules, attach_suggestion
from .rule_stability import assess_rule_stability


def _safe_scope_name(scope: str) -> str:
    """把分群值变成可作文件名的字符串。"""
    s = re.sub(r'[\\/:*?"<>|\s]+', '_', scope.strip()) or 'scope'
    return s[:60]


def mine_rules_full(
    df: pd.DataFrame,
    feature_cols: List[str],
    target: str = 'is_bad',
    verbose: bool = True,
    persist_tree_path: Optional[Union[str, Path]] = None,
) -> pd.DataFrame:
    """全流程：挖掘 → 评估闸门 → 稳定性 → 业务建议。

    persist_tree_path: 若给定，把全量拟合的决策树持久化（供可视化）。
    """
    raw = mine_rules(
        df, feature_cols, target=target, verbose=verbose,
        persist_tree_path=persist_tree_path,
    )
    if raw.empty:
        return raw
    evaluated = evaluate_rules(df, raw, target=target)
    if evaluated.empty:
        return evaluated
    with_stability = assess_rule_stability(df, evaluated, target=target, verbose=verbose)
    return attach_suggestion(with_stability)


def rules_by_group(
    df: pd.DataFrame,
    segment_col: str,
    feature_cols: List[str],
    target: str = 'is_bad',
    verbose: bool = True,
    persist_tree_dir: Optional[Union[str, Path]] = None,
) -> pd.DataFrame:
    """按分群列分别挖掘规则，合并为长表。

    每个分群独立跑 mine_rules_full。未满足 MIN_SAMPLES 的群组跳过并打印原因。

    persist_tree_dir: 若给定，每个分群拟合的树落到
        `<persist_tree_dir>/rule_tree_<segment_col>__<segment_value>.pkl`。
    """
    if segment_col not in df.columns:
        raise KeyError(f"分群列不存在：{segment_col}")

    min_samples = SAMPLE_THRESHOLDS['MIN_SAMPLES']
    all_rules = []

    persist_dir: Optional[Path] = None
    if persist_tree_dir is not None:
        persist_dir = Path(persist_tree_dir)
        persist_dir.mkdir(parents=True, exist_ok=True)

    for seg_val, sub in df.groupby(segment_col, dropna=False):
        label = '(缺失)' if pd.isna(seg_val) else str(seg_val)
        if len(sub) < min_samples:
            if verbose:
                print(f"[跳过分群] {segment_col}={label} 样本数 {len(sub)} < MIN_SAMPLES={min_samples}")
            continue

        if verbose:
            print(f"\n=== 挖掘分群规则：{segment_col}={label} (n={len(sub)}) ===")

        seg_pkl = None
        if persist_dir is not None:
            seg_pkl = persist_dir / (
                f"rule_tree_{_safe_scope_name(segment_col)}__{_safe_scope_name(label)}.pkl"
            )

        rules = mine_rules_full(
            sub, feature_cols, target=target, verbose=verbose,
            persist_tree_path=seg_pkl,
        )
        if rules.empty:
            continue
        rules.insert(0, 'segment_dim', segment_col)
        rules.insert(1, 'segment_value', label)
        all_rules.append(rules)

    if not all_rules:
        return pd.DataFrame()
    return pd.concat(all_rules, ignore_index=True)


# =============================================================================
# 导出
# =============================================================================

_EXPORT_COL_MAP = {
    'segment_dim': '分群维度',
    'segment_value': '分群值',
    'rule_id': '规则编号',
    'conditions_text': '规则条件',
    'feature_list': '涉及特征',
    'depth': '特征数量',
    'coverage_n': '覆盖样本数',
    'coverage_pct': '覆盖率',
    'bad_n': '覆盖坏客户数',
    'bad_rate': '规则坏账率',
    'overall_bad_rate': '整体坏账率',
    'lift': 'Lift',
    'bad_rate_ci_low': '坏账率下界',
    'bad_rate_ci_high': '坏账率上界',
    'cv_bad_rate_mean': 'CV坏账率均值',
    'cv_bad_rate_std': 'CV坏账率标准差',
    'cv_valid_folds': 'CV有效折数',
    'stability': '稳定性等级',
    'suggestion': '建议用途',
}


def export_rules(
    rules_df: pd.DataFrame,
    project_name: str,
    output_dir: Optional[str] = None,
) -> Path:
    """导出规则表为 CSV（UTF-8 BOM）。

    文件名：`{project_name}_风险规则表.csv`
    """
    if output_dir is None:
        output_dir = FINAL_OUTPUT_DIR
    out_path = Path(output_dir) / f"{project_name}_风险规则表.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if rules_df.empty:
        print(f"[导出] 无规则可导出 → {out_path}")
        pd.DataFrame(columns=list(_EXPORT_COL_MAP.values())).to_csv(
            out_path, index=False, encoding='utf-8-sig'
        )
        return out_path

    df_export = rules_df.copy()
    # feature_list 转字符串，避免 CSV 存列表字面量
    if 'feature_list' in df_export.columns:
        df_export['feature_list'] = df_export['feature_list'].apply(
            lambda xs: '、'.join(xs) if isinstance(xs, (list, tuple)) else xs
        )
    # 丢弃不需要导出的内部列（conditions 为结构化，不导出）
    df_export = df_export.drop(columns=['conditions'], errors='ignore')

    # 重排 + 改中文列名
    cols = [c for c in _EXPORT_COL_MAP if c in df_export.columns]
    df_export = df_export[cols].rename(columns=_EXPORT_COL_MAP)

    df_export.to_csv(out_path, index=False, encoding='utf-8-sig')
    print(f"[导出] 规则表 → {out_path} ({len(df_export)} 条)")
    return out_path


def build_llm_rules_payload(rules_df: pd.DataFrame) -> List[Dict]:
    """构建供 risk_export_report 合并的 LLM JSON 节点。

    返回形如：
    [
        {"segment": "制造业", "rule": "资产负债率 大于 0.75 且 ...",
         "coverage": 0.08, "bad_rate": 0.32, "lift": 3.4,
         "stability": "稳定", "suggestion": "审批红线"},
        ...
    ]
    """
    if rules_df.empty:
        return []
    out = []
    for _, r in rules_df.iterrows():
        seg = r.get('segment_value', '全样本')
        out.append({
            'segment': str(seg),
            'rule': r['conditions_text'],
            'coverage': round(float(r['coverage_pct']), 4),
            'bad_rate': round(float(r['bad_rate']), 4),
            'lift': round(float(r['lift']), 2),
            'stability': r.get('stability', ''),
            'suggestion': r.get('suggestion', '参考'),
        })
    return out
