# -*- coding: utf-8 -*-
"""分群画像图：坏客户率柱图 + 样本数标注 + 整体基准线。"""
from __future__ import annotations

from pathlib import Path
from typing import List

import pandas as pd

from .style import POS_COLOR, NEUTRAL_COLOR, FIGSIZE_BAR_WIDE, GRID_COLOR


_BAD_RATE_CANDIDATES = ['坏客户率', 'bad_rate', '违约率', 'default_rate']
_N_CANDIDATES = ['样本数', 'n', 'size', 'count']
_NAME_CANDIDATES = ['分群', '分群名称', 'segment', 'group']
_DIM_CANDIDATES = ['分群维度', 'dim', 'dimension']


def _pick_col(df: pd.DataFrame, candidates) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def chart_segment_profile(
    segment_profiles: pd.DataFrame,
    out_dir: Path,
    dpi: int = 300,
) -> List[Path]:
    """读 _LLM_分群画像.csv 出坏客户率柱图。"""
    import matplotlib.pyplot as plt

    if segment_profiles is None or segment_profiles.empty:
        return []

    rate_col = _pick_col(segment_profiles, _BAD_RATE_CANDIDATES)
    name_col = _pick_col(segment_profiles, _NAME_CANDIDATES)
    n_col = _pick_col(segment_profiles, _N_CANDIDATES)
    dim_col = _pick_col(segment_profiles, _DIM_CANDIDATES)

    if rate_col is None or name_col is None:
        return []

    df = segment_profiles.copy()
    df[rate_col] = pd.to_numeric(df[rate_col], errors='coerce')
    df = df.dropna(subset=[rate_col])
    if df.empty:
        return []

    if dim_col is not None:
        df['_label'] = df[dim_col].astype(str) + ' = ' + df[name_col].astype(str)
    else:
        df['_label'] = df[name_col].astype(str)

    df = df.sort_values(rate_col, ascending=False)

    overall = df[rate_col].mean()  # 兜底基准；首选用 _LLM_分群画像.csv 的全局列（如有）
    if '整体坏客户率' in df.columns and not df['整体坏客户率'].isna().all():
        overall = float(pd.to_numeric(df['整体坏客户率'], errors='coerce').mean())

    fig, ax = plt.subplots(figsize=FIGSIZE_BAR_WIDE)
    bars = ax.bar(df['_label'], df[rate_col], color=POS_COLOR, edgecolor='white')
    ax.axhline(overall, color='#C0392B', linestyle='--', linewidth=1.2,
               label=f'整体坏客户率 ≈ {overall:.2%}')
    ax.set_ylabel('坏客户率')
    ax.set_title('分群画像：坏客户率（柱顶=样本数）')
    ax.grid(axis='y', color=GRID_COLOR, linewidth=0.6)
    ax.set_axisbelow(True)
    plt.setp(ax.get_xticklabels(), rotation=30, ha='right', fontsize=9)

    for bar, val in zip(bars, df[rate_col]):
        ax.text(bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
                f'{val:.2%}',
                ha='center', va='bottom', fontsize=8, color='#2C3E50')

    if n_col is not None:
        for bar, n in zip(bars, df[n_col]):
            try:
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + (df[rate_col].max() * 0.04),
                        f'n={int(n)}',
                        ha='center', va='bottom', fontsize=8, color=NEUTRAL_COLOR)
            except (ValueError, TypeError):
                continue

    ax.legend(loc='upper right', fontsize=9, framealpha=0.9)

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / 'segment_profile.png'
    fig.tight_layout()
    fig.savefig(path, dpi=dpi, bbox_inches='tight')
    plt.close(fig)
    return [path]
