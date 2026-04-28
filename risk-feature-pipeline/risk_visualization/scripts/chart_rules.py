# -*- coding: utf-8 -*-
"""规则散点图：lift × coverage（按稳定性着色，气泡=坏客户数）。"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

from . import style  # 字体配置
from .style import STABILITY_COLORS, NEUTRAL_COLOR, FIGSIZE_SCATTER, GRID_COLOR


def chart_rules_scatter(
    rules_df: Optional[pd.DataFrame],
    out_dir: Path,
    dpi: int = 300,
) -> List[Path]:
    """所有规则的 lift × coverage 散点图。"""
    import matplotlib.pyplot as plt

    if rules_df is None or rules_df.empty:
        return []

    needed = {'覆盖率', 'Lift'}
    if not needed.issubset(rules_df.columns):
        return []

    df = rules_df.copy()
    df['覆盖率'] = pd.to_numeric(df['覆盖率'], errors='coerce')
    df['Lift'] = pd.to_numeric(df['Lift'], errors='coerce')
    df = df.dropna(subset=['覆盖率', 'Lift'])
    if df.empty:
        return []

    bad_n = pd.to_numeric(df.get('覆盖坏客户数', pd.Series([10] * len(df))), errors='coerce').fillna(10)
    sizes = 30 + (bad_n / max(bad_n.max(), 1)) * 300

    stabilities = df.get('稳定性等级', pd.Series([''] * len(df))).astype(str)
    colors = [STABILITY_COLORS.get(s, NEUTRAL_COLOR) for s in stabilities]

    fig, ax = plt.subplots(figsize=FIGSIZE_SCATTER)
    ax.scatter(df['覆盖率'], df['Lift'], s=sizes, c=colors,
               alpha=0.75, edgecolors='white', linewidths=0.8)
    ax.set_xscale('log')
    ax.set_yscale('log')
    ax.set_xlabel('覆盖率（log scale）')
    ax.set_ylabel('Lift（log scale）')
    ax.set_title('规则 lift × coverage 散点（右上=高 lift+高覆盖；气泡大小=覆盖坏客户数）')
    ax.grid(True, which='both', color=GRID_COLOR, linewidth=0.5, alpha=0.7)
    ax.set_axisbelow(True)

    # lift=1 基准线（lift=1 即与整体坏账率持平）
    ax.axhline(1.0, color=NEUTRAL_COLOR, linestyle=':', linewidth=1, alpha=0.7,
               label='Lift=1 基线')

    # 稳定性图例
    seen = []
    handles = []
    for s in stabilities:
        if s in seen or not s:
            continue
        seen.append(s)
        handles.append(plt.Line2D(
            [0], [0], marker='o', color='white',
            markerfacecolor=STABILITY_COLORS.get(s, NEUTRAL_COLOR),
            markersize=10, label=f'稳定性: {s}',
        ))
    if handles:
        ax.legend(handles=handles + [
            plt.Line2D([0], [0], color=NEUTRAL_COLOR, linestyle=':', label='Lift=1 基线'),
        ], loc='best', fontsize=9, framealpha=0.9)

    # 标注 top-3 最高 lift
    top3 = df.nlargest(3, 'Lift')
    for _, row in top3.iterrows():
        rid = row.get('规则编号', '')
        ax.annotate(f'r{rid}', (row['覆盖率'], row['Lift']),
                    xytext=(8, 4), textcoords='offset points',
                    fontsize=8, color='#2C3E50')

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / 'rules_lift_coverage.png'
    fig.tight_layout()
    fig.savefig(path, dpi=dpi, bbox_inches='tight')
    plt.close(fig)
    return [path]
