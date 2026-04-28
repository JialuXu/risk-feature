# -*- coding: utf-8 -*-
"""指标组合可视化：

- chart_combo_lift: 按 feature_list 聚合，max(lift) 横向条形图（柱色=合计覆盖率）
- chart_combo_network: 特征共现网络（节点=特征，边=共现规则数；圆形布局，无 networkx 依赖）
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from . import style  # 字体配置
from .style import (
    POS_COLOR, NEUTRAL_COLOR, ANNO_COLOR, FIGSIZE_BAR_TALL, FIGSIZE_NETWORK,
    GRID_COLOR,
)


def _split_feature_list(s) -> List[str]:
    """规则 CSV 里 feature_list 落盘时被 '、' 连接（见 rule_mining_pipeline.export_rules）。"""
    if isinstance(s, list):
        return [str(x).strip() for x in s if str(x).strip()]
    if not isinstance(s, str):
        return []
    return [x.strip() for x in s.replace('，', '、').split('、') if x.strip()]


def chart_combo_lift(
    rules_df: Optional[pd.DataFrame],
    out_dir: Path,
    top_n: int = 15,
    dpi: int = 300,
) -> List[Path]:
    """按 feature_list 聚合的 max-lift 条形图。"""
    import matplotlib.pyplot as plt

    if rules_df is None or rules_df.empty:
        return []
    if '涉及特征' not in rules_df.columns or 'Lift' not in rules_df.columns:
        return []

    df = rules_df.copy()
    df['Lift'] = pd.to_numeric(df['Lift'], errors='coerce')
    df['覆盖率'] = pd.to_numeric(df.get('覆盖率', 0), errors='coerce').fillna(0)
    df['_feats'] = df['涉及特征'].apply(_split_feature_list)
    df['_combo'] = df['_feats'].apply(lambda xs: ' + '.join(sorted(xs)) if xs else '')
    df = df[df['_combo'] != ''].dropna(subset=['Lift'])
    if df.empty:
        return []

    agg = df.groupby('_combo').agg(
        max_lift=('Lift', 'max'),
        total_cov=('覆盖率', 'sum'),
        n_rules=('Lift', 'count'),
        n_feats=('_feats', lambda xs: len(xs.iloc[0])),
    ).reset_index()
    agg = agg.sort_values('max_lift', ascending=False).head(top_n)
    if agg.empty:
        return []

    agg = agg.iloc[::-1]  # 横向反转，高 lift 在最上

    # 颜色按合计覆盖率（log）映射
    cov = agg['total_cov'].clip(lower=1e-4)
    norm = (np.log10(cov) - np.log10(cov.min())) / max(
        np.log10(cov.max()) - np.log10(cov.min()), 1e-9,
    )
    cmap = plt.cm.Blues
    colors = [cmap(0.3 + 0.6 * v) for v in norm]

    fig, ax = plt.subplots(figsize=FIGSIZE_BAR_TALL)
    bars = ax.barh(agg['_combo'], agg['max_lift'], color=colors, edgecolor='white')
    ax.set_xlabel('该组合下规则的最高 Lift')
    ax.set_title(f'指标组合 max-Lift Top-{top_n}（柱色=合计覆盖率，文末=命中规则数）')
    ax.grid(axis='x', color=GRID_COLOR, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.axvline(1.0, color=NEUTRAL_COLOR, linestyle=':', linewidth=1, alpha=0.7,
               label='Lift=1 基线')
    ax.legend(loc='lower right', fontsize=9, framealpha=0.9)

    for bar, lift, n_rules, total_cov in zip(
        bars, agg['max_lift'], agg['n_rules'], agg['total_cov']
    ):
        ax.text(bar.get_width() + 0.02,
                bar.get_y() + bar.get_height() / 2,
                f'lift={lift:.2f}  n={int(n_rules)}  cov={total_cov:.1%}',
                va='center', fontsize=8, color=ANNO_COLOR)

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f'combo_lift_top{top_n}.png'
    fig.tight_layout()
    fig.savefig(path, dpi=dpi, bbox_inches='tight')
    plt.close(fig)
    return [path]


def chart_combo_network(
    rules_df: Optional[pd.DataFrame],
    out_dir: Path,
    top_features: int = 25,
    dpi: int = 300,
) -> List[Path]:
    """特征共现网络（圆形布局自绘）。

    节点 = 特征；节点大小 = 该特征出现的规则数
    边 = 任两特征在同一条规则共现；边粗 = 共现规则数（log）
    """
    import matplotlib.pyplot as plt

    if rules_df is None or rules_df.empty:
        return []
    if '涉及特征' not in rules_df.columns:
        return []

    feat_lists = rules_df['涉及特征'].apply(_split_feature_list).tolist()
    feat_lists = [fs for fs in feat_lists if fs]
    if not feat_lists:
        return []

    feat_count: Counter[str] = Counter()
    cooc: Dict[Tuple[str, str], int] = defaultdict(int)

    for fs in feat_lists:
        unique = sorted(set(fs))
        for f in unique:
            feat_count[f] += 1
        for a, b in combinations(unique, 2):
            cooc[(a, b)] += 1

    if not cooc:
        # 单特征规则，没有共现，画一张极简的"特征出现频次"作为兜底
        feats = [f for f, _ in feat_count.most_common(top_features)]
        sizes = [feat_count[f] for f in feats]
        fig, ax = plt.subplots(figsize=FIGSIZE_NETWORK)
        ax.barh(feats[::-1], sizes[::-1], color=POS_COLOR, edgecolor='white')
        ax.set_xlabel('在规则中出现次数')
        ax.set_title('特征出现频次（无共现 → 单特征规则）')
        ax.grid(axis='x', color=GRID_COLOR, linewidth=0.6)
        ax.set_axisbelow(True)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / 'combo_network.png'
        fig.tight_layout()
        fig.savefig(path, dpi=dpi, bbox_inches='tight')
        plt.close(fig)
        return [path]

    # 取出现频次最高的 top_features
    feats = [f for f, _ in feat_count.most_common(top_features)]
    feat_set = set(feats)
    edges = [((a, b), w) for (a, b), w in cooc.items() if a in feat_set and b in feat_set]

    n = len(feats)
    # 圆形布局
    angles = np.linspace(0.5 * np.pi, 0.5 * np.pi - 2 * np.pi, n, endpoint=False)
    pos = {f: (math.cos(a), math.sin(a)) for f, a in zip(feats, angles)}

    max_node = max(feat_count[f] for f in feats)
    max_edge = max(w for _, w in edges) if edges else 1

    fig, ax = plt.subplots(figsize=FIGSIZE_NETWORK)

    # 边
    for (a, b), w in edges:
        x1, y1 = pos[a]
        x2, y2 = pos[b]
        lw = 0.5 + 3.0 * (math.log1p(w) / math.log1p(max_edge))
        alpha = 0.25 + 0.6 * (w / max_edge)
        ax.plot([x1, x2], [y1, y2], color=POS_COLOR, linewidth=lw, alpha=alpha, zorder=1)

    # 节点
    for f in feats:
        x, y = pos[f]
        size = 200 + 1500 * (feat_count[f] / max_node)
        ax.scatter(x, y, s=size, color=POS_COLOR, edgecolors='white',
                   linewidths=1.5, zorder=2, alpha=0.9)

    # 标签（沿圆放外侧）
    for f, a in zip(feats, angles):
        x, y = math.cos(a) * 1.18, math.sin(a) * 1.18
        ha = 'left' if math.cos(a) > 0.05 else ('right' if math.cos(a) < -0.05 else 'center')
        va = 'bottom' if math.sin(a) > 0.05 else ('top' if math.sin(a) < -0.05 else 'center')
        ax.text(x, y, f, ha=ha, va=va, fontsize=9, color=ANNO_COLOR)

    ax.set_xlim(-1.5, 1.5)
    ax.set_ylim(-1.4, 1.4)
    ax.set_aspect('equal')
    ax.axis('off')
    ax.set_title(f'特征共现网络（top-{n} 特征；节点大小=出现规则数，边粗=共现规则数）')

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / 'combo_network.png'
    fig.tight_layout()
    fig.savefig(path, dpi=dpi, bbox_inches='tight')
    plt.close(fig)
    return [path]
