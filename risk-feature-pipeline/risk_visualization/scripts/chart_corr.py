# -*- coding: utf-8 -*-
"""分群相关系数横向条形图（每分群一张）。"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

import pandas as pd

from . import style  # 字体配置
from .style import POS_COLOR, NEG_COLOR, FIGSIZE_BAR_TALL, GRID_COLOR


def _safe(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', '_', str(name).strip()) or 'x'


def chart_corr(
    corr_long: pd.DataFrame,
    out_dir: Path,
    top_n: int = 15,
    dim: Optional[str] = None,
    dpi: int = 300,
) -> List[Path]:
    """每个分群（dim/group）出一张横向条形图，按 |相关系数| 排序，取 top-N。"""
    import matplotlib.pyplot as plt

    if corr_long is None or corr_long.empty:
        return []

    df = corr_long.copy()
    needed = {'分群维度', '分群名称', '特征', '相关系数'}
    if not needed.issubset(df.columns):
        return []
    df['相关系数'] = pd.to_numeric(df['相关系数'], errors='coerce')
    df = df.dropna(subset=['相关系数'])
    if dim:
        df = df[df['分群维度'] == dim]
    if df.empty:
        return []

    out_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []

    for (d, g), sub in df.groupby(['分群维度', '分群名称']):
        sub = sub.assign(_abs=sub['相关系数'].abs())
        sub = sub.sort_values('_abs', ascending=False).head(top_n)
        if sub.empty:
            continue
        sub = sub.sort_values('相关系数')  # 横向条形从下往上递增
        colors = [POS_COLOR if v >= 0 else NEG_COLOR for v in sub['相关系数']]

        fig, ax = plt.subplots(figsize=FIGSIZE_BAR_TALL)
        ax.barh(sub['特征'], sub['相关系数'], color=colors, edgecolor='white')
        ax.axvline(0, color='#2C3E50', linewidth=0.8)
        ax.set_xlabel('相关系数（与坏客户）')
        ax.set_title(f'相关系数 Top-{top_n} | {d} = {g}')
        ax.grid(axis='x', color=GRID_COLOR, linewidth=0.6)
        ax.set_axisbelow(True)

        for i, v in enumerate(sub['相关系数']):
            ax.text(v + (0.005 if v >= 0 else -0.005),
                    i, f'{v:.3f}',
                    va='center',
                    ha='left' if v >= 0 else 'right',
                    fontsize=9, color='#2C3E50')

        path = out_dir / f'corr_{_safe(d)}__{_safe(g)}_top{top_n}.png'
        fig.tight_layout()
        fig.savefig(path, dpi=dpi, bbox_inches='tight')
        plt.close(fig)
        paths.append(path)

    return paths
