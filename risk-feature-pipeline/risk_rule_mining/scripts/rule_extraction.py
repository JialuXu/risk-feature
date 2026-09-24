# -*- coding: utf-8 -*-
"""
规则提取：拟合决策树 → 遍历路径 → 转为可读规则

核心函数：
    mine_rules(df, feature_cols, target, ...) -> pd.DataFrame
        返回字段：rule_id, conditions, feature_list, depth, leaf_n, leaf_bad
"""
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Union
import numpy as np
import pandas as pd
from sklearn.tree import DecisionTreeClassifier, _tree

from risk_core.missing import fit_fill_values, impute_median

from .config import (
    RULE_MINING_CONFIG,
    SAMPLE_THRESHOLDS,
    THRESHOLD_DECIMALS,
    OPERATOR_CN,
)


def fit_rule_tree(
    X: pd.DataFrame,
    y: pd.Series,
    max_depth: Optional[int] = None,
    min_samples_leaf: Optional[int] = None,
) -> DecisionTreeClassifier:
    """拟合受约束的决策树，用于规则提取。"""
    cfg = RULE_MINING_CONFIG
    if max_depth is None:
        max_depth = cfg['max_depth']
    if min_samples_leaf is None:
        # 以占比推导绝对值，至少 10
        min_samples_leaf = max(10, int(len(X) * cfg['min_samples_leaf_ratio']))

    tree = DecisionTreeClassifier(
        criterion=cfg['tree_criterion'],
        max_depth=max_depth,
        min_samples_leaf=min_samples_leaf,
        class_weight=cfg['class_weight'],
        random_state=42,
    )
    tree.fit(X, y)
    return tree


def _extract_leaf_paths(
    tree: DecisionTreeClassifier,
    feature_names: List[str],
    X: Optional[pd.DataFrame] = None,
    y: Optional[pd.Series] = None,
) -> List[Dict]:
    """遍历 sklearn 树，返回所有叶节点的完整路径与真实样本统计。

    注意：当 class_weight='balanced' 时 tree_.value 为加权计数，不能直接用。
    若传入 X/y，则用 tree.apply(X) 得到真实样本归属并据此计算叶子统计。
    """
    t = tree.tree_
    paths: List[Dict] = []
    leaf_nodes: List[int] = []

    def recurse(node_id: int, conditions: List[Tuple[str, str, float]]):
        if t.children_left[node_id] == _tree.TREE_LEAF:
            paths.append({
                'node_id': node_id,
                'conditions': list(conditions),
                'leaf_n': 0, 'leaf_bad': 0, 'leaf_good': 0,
            })
            leaf_nodes.append(node_id)
            return
        feat = feature_names[t.feature[node_id]]
        thr = float(t.threshold[node_id])
        recurse(t.children_left[node_id], conditions + [(feat, '<=', thr)])
        recurse(t.children_right[node_id], conditions + [(feat, '>', thr)])

    recurse(0, [])

    # 用真实数据计算叶子统计（规避 class_weight 导致的加权计数问题）
    if X is not None and y is not None:
        leaf_ids = tree.apply(X)
        y_arr = y.values if hasattr(y, 'values') else np.asarray(y)
        for p in paths:
            mask = leaf_ids == p['node_id']
            n = int(mask.sum())
            bad = int(y_arr[mask].sum()) if n > 0 else 0
            p['leaf_n'] = n
            p['leaf_bad'] = bad
            p['leaf_good'] = n - bad

    return paths


def _simplify_conditions(
    conditions: List[Tuple[str, str, float]],
) -> List[Tuple[str, str, float]]:
    """合并同一特征的多次分裂：保留最紧的上下界。

    例：`x <= 0.8` 与 `x <= 0.6` → 仅保留 `x <= 0.6`
        `x > 0.3` 与 `x > 0.5`  → 仅保留 `x > 0.5`
    """
    by_feat: Dict[str, Dict[str, float]] = {}
    for feat, op, thr in conditions:
        d = by_feat.setdefault(feat, {})
        if op == '<=':
            d['<='] = min(d.get('<=', np.inf), thr)
        elif op == '>':
            d['>'] = max(d.get('>', -np.inf), thr)
        else:
            d[op] = thr

    out: List[Tuple[str, str, float]] = []
    for feat, ops in by_feat.items():
        for op, thr in ops.items():
            out.append((feat, op, round(float(thr), THRESHOLD_DECIMALS)))
    return sorted(out, key=lambda x: (x[0], x[1]))


# C11 阈值精度启发式 token 顺序：
# 比率类先判断（资产负债率含"资产"但本质是比率，须走 2 位小数分支）
_RATIO_TOKENS = ('占比', '比率', '率', '系数')
_AMOUNT_TOKENS = ('金额', '余额', '资产', '收入', '负债', '现金', '存款', '贷款')


def _format_threshold(thr: float, feature_name: str) -> str:
    """C11: 按特征名启发式选阈值精度，便于业务宣贯。

    优先级：比率类 > 金额类 > 默认。
    - 比率/占比/率/系数类：保留 2 位小数（如 `0.12`、`0.75`）
    - 金额/余额/资产/收入/负债/现金/存款/贷款类：取整 + 千分位（如 `21,120,000`）
    - 其它：现有 `:.4g`（小数与科学计数法兜底）
    """
    if not feature_name:
        return f"{thr:.4g}"
    if any(tok in feature_name for tok in _RATIO_TOKENS):
        return f"{thr:.2f}"
    if any(tok in feature_name for tok in _AMOUNT_TOKENS):
        if abs(thr) >= 10000:
            return f"{thr:,.0f}"
        return f"{thr:.0f}"
    return f"{thr:.4g}"


def _conditions_to_text(conditions: List[Tuple[str, str, float]]) -> str:
    """规则条件转中文业务语言（阈值精度按特征名自适应，C11）。"""
    parts = [
        f"{feat} {OPERATOR_CN.get(op, op)} {_format_threshold(thr, feat)}"
        for feat, op, thr in conditions
    ]
    return " 且 ".join(parts)


def _conditions_to_mask(
    df: pd.DataFrame,
    conditions: List[Tuple[str, str, float]],
    fill_values: Optional[Dict[str, float]] = None,
) -> pd.Series:
    """规则条件 → 布尔掩码。

    fill_values：挖掘时拟合的中位数填补值（缺失口径：训练与评估同一套填补）。
    传入时缺失值先按其填补再判定；未传或该特征无填补值时，缺失视为不命中。
    """
    mask = pd.Series(True, index=df.index)
    for feat, op, thr in conditions:
        col = df[feat]
        if fill_values and feat in fill_values:
            col = col.fillna(fill_values[feat])
        if op == '<=':
            mask &= (col <= thr)
        elif op == '>':
            mask &= (col > thr)
        elif op == '<':
            mask &= (col < thr)
        elif op == '>=':
            mask &= (col >= thr)
        elif op == '==':
            mask &= (col == thr)
        else:
            raise ValueError(f"未知运算符：{op}")
    return mask.fillna(False)


def _dedupe_rules(rules: List[Dict]) -> List[Dict]:
    """按条件集合去重（同一树可能生成等价叶子）。"""
    seen = set()
    kept = []
    for r in rules:
        key = tuple(sorted((f, o, round(t, THRESHOLD_DECIMALS))
                           for f, o, t in r['conditions']))
        if key in seen:
            continue
        seen.add(key)
        kept.append(r)
    return kept


def mine_rules(
    df: pd.DataFrame,
    feature_cols: List[str],
    target: str = 'is_bad',
    max_depth: Optional[int] = None,
    verbose: bool = True,
    persist_tree_path: Optional[Union[str, Path]] = None,
) -> pd.DataFrame:
    """从宽表挖掘风险规则。

    流程：准入检查 → 拟合树 → 提取叶路径 → 过滤"坏富集"路径 → 去重 → 返回 DataFrame。
    返回 DataFrame 列：rule_id, conditions, fill_values, conditions_text, feature_list,
                      depth, leaf_n, leaf_bad, leaf_good。

    Args:
        persist_tree_path: 若给定，则把拟合好的 DecisionTreeClassifier 与特征列名
            一起 joblib.dump 到该路径，供 risk_visualization 用 sklearn.tree.plot_tree
            渲染真树形图。默认 None = 不持久化（向后兼容）。
    """
    # 准入：样本量阈值与 LR 对齐（挖规则与建模对坏样本的要求相当）
    df_clean = df.dropna(subset=[target]).copy()
    n_total = len(df_clean)
    n_bad = int(df_clean[target].sum())
    n_good = n_total - n_bad

    if n_bad < SAMPLE_THRESHOLDS['MIN_BAD_LR']:
        if verbose:
            print(f"[跳过] 坏客户数 {n_bad} < MIN_BAD_LR={SAMPLE_THRESHOLDS['MIN_BAD_LR']}，无法挖掘规则")
        return pd.DataFrame()
    if n_good < SAMPLE_THRESHOLDS['MIN_GOOD_LR']:
        if verbose:
            print(f"[跳过] 好客户数 {n_good} < MIN_GOOD_LR={SAMPLE_THRESHOLDS['MIN_GOOD_LR']}，无法挖掘规则")
        return pd.DataFrame()

    # 只保留数值列（树需要数值输入）；缺失口径：中位数填补，填补值随规则一并返回，
    # 评估 / 打分时按同一套填补值判定命中（见 _conditions_to_mask）
    X_raw = df_clean[feature_cols].select_dtypes(include=[np.number])
    if X_raw.shape[1] == 0:
        if verbose:
            print("[跳过] 无数值特征可用于树分裂")
        return pd.DataFrame()
    fill_values = fit_fill_values(X_raw)
    X = impute_median(X_raw, fill_values)
    y = df_clean[target].astype(int)

    tree = fit_rule_tree(X, y, max_depth=max_depth)
    paths = _extract_leaf_paths(tree, list(X.columns), X=X, y=y)

    if persist_tree_path is not None:
        try:
            import joblib
            persist_tree_path = Path(persist_tree_path)
            persist_tree_path.parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(
                {
                    'tree': tree,
                    'feature_names': list(X.columns),
                    'target': target,
                    'overall_bad_rate': n_bad / n_total,
                },
                persist_tree_path,
            )
            if verbose:
                print(f"[规则挖掘] 树对象已落盘 → {persist_tree_path}")
        except Exception as e:
            if verbose:
                print(f"[规则挖掘] 树对象落盘失败（不影响规则导出）：{e}")

    # 过滤："坏富集"叶子 + 最少坏客户数
    overall_bad_rate = n_bad / n_total
    min_bad_in_leaf = RULE_MINING_CONFIG['min_bad_in_leaf']

    rules = []
    for p in paths:
        if p['leaf_n'] == 0 or p['leaf_bad'] < min_bad_in_leaf:
            continue
        leaf_bad_rate = p['leaf_bad'] / p['leaf_n']
        if leaf_bad_rate <= overall_bad_rate:
            continue
        p['conditions'] = _simplify_conditions(p['conditions'])
        rules.append(p)

    rules = _dedupe_rules(rules)

    if not rules:
        if verbose:
            print(f"[提示] 未挖掘到满足条件的规则（整体坏账率 {overall_bad_rate:.2%}）")
        return pd.DataFrame()

    records = []
    for i, r in enumerate(rules, start=1):
        feats = sorted({c[0] for c in r['conditions']})
        records.append({
            'rule_id': i,
            'conditions': r['conditions'],
            'fill_values': {f: fill_values[f] for f in feats if f in fill_values},
            'conditions_text': _conditions_to_text(r['conditions']),
            'feature_list': feats,
            'depth': len(feats),
            'leaf_n': r['leaf_n'],
            'leaf_bad': r['leaf_bad'],
            'leaf_good': r['leaf_good'],
        })
    return pd.DataFrame(records)
