# -*- coding: utf-8 -*-
"""指标组合可视化：

- chart_combo_lift: 按 feature_list 聚合，max(lift) 横向条形图（柱色=合计覆盖率）

注：原"特征共现网络"图已移除——它自述用途是"反向辅助特征工程"，属分析师/建模阶段
工具，对最终业务报告无意义。
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

from . import style  # 字体配置
from .style import (
    NEUTRAL_COLOR, ANNO_COLOR, FIGSIZE_BAR_TALL, GRID_COLOR,
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
