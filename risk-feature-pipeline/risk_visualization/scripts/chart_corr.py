# -*- coding: utf-8 -*-
"""分群相关系数：横向条形图（每分群一张）+ 跨分群×特征热力图。"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

from . import style  # 字体配置
from .style import POS_COLOR, NEG_COLOR, FIGSIZE_BAR_TALL, FIGSIZE_HEATMAP, GRID_COLOR


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


def chart_corr_heatmap(
    corr_long: pd.DataFrame,
    out_dir: Path,
    top_n: int = 15,
    dim: Optional[str] = None,
    dpi: int = 300,
) -> List[Path]:
    """分群 × 特征 相关系数热力图（行=分群、列=特征 top-N、发散色以 0 为中心）。

    业务用法：一图就能看出"特征 X 在小型企业为正、在大型企业为负"这种符号冲突。
    每个 `分群维度` 出一张图（避免行维度混在一起）；可用 `dim` 过滤到单一维度。
    """
    import matplotlib.pyplot as plt

    if corr_long is None or corr_long.empty:
        return []

    needed = {'分群维度', '分群名称', '特征', '相关系数'}
    if not needed.issubset(corr_long.columns):
        return []

    df = corr_long.copy()
    df['相关系数'] = pd.to_numeric(df['相关系数'], errors='coerce')
    df = df.dropna(subset=['相关系数'])
    if dim:
        df = df[df['分群维度'] == dim]
    if df.empty:
        return []

    out_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []

    for d, sub in df.groupby('分群维度'):
        # top-N 特征：按"该维度内 |corr| 的最大值"全局排序
        feat_rank = (sub.assign(_abs=sub['相关系数'].abs())
                     .groupby('特征')['_abs'].max()
                     .sort_values(ascending=False))
        keep = feat_rank.head(top_n).index.tolist()
        if not keep:
            continue

        sub2 = sub[sub['特征'].isin(keep)]
        pivot = sub2.pivot_table(
            index='分群名称', columns='特征', values='相关系数', aggfunc='mean',
        )
        # 列按全局排名重排，行按各分群的样本量大小（如有）或字典序
        pivot = pivot.reindex(columns=keep)
        pivot = pivot.reindex(index=sorted(pivot.index, key=lambda x: str(x)))
        if pivot.empty:
            continue

        n_rows, n_cols = pivot.shape
        base_w, base_h = FIGSIZE_HEATMAP
        height = max(3.0, min(base_h, 0.55 * n_rows + 2.0))
        width = max(base_w, 0.55 * n_cols + 4.0)

        fig, ax = plt.subplots(figsize=(width, height))
        data = pivot.values.astype(float)

        # 发散色阶以 0 为中心；取数据绝对值最大值作为对称范围
        vabs = float(np.nanmax(np.abs(data))) if not np.all(np.isnan(data)) else 1.0
        vabs = max(vabs, 0.05)
        im = ax.imshow(data, aspect='auto', cmap='RdBu_r', vmin=-vabs, vmax=vabs)

        ax.set_xticks(range(n_cols))
        ax.set_xticklabels(pivot.columns, rotation=30, ha='right', fontsize=9)
        ax.set_yticks(range(n_rows))
        ax.set_yticklabels(pivot.index, fontsize=9)
        ax.set_xlabel('特征指标')
        ax.set_ylabel(f'分群（{d}）')
        ax.set_title(f'分群 × 特征 相关系数热力图 | {d}（top-{top_n}，红=负向 / 蓝=正向）')

        for i in range(n_rows):
            for j in range(n_cols):
                v = data[i, j]
                if np.isnan(v):
                    continue
                color = 'white' if abs(v) > vabs * 0.55 else '#2C3E50'
                ax.text(j, i, f'{v:.2f}', ha='center', va='center', fontsize=8, color=color)

        fig.colorbar(im, ax=ax, label='相关系数', shrink=0.8)

        path = out_dir / f'corr_heatmap_{_safe(d)}_top{top_n}.png'
        fig.tight_layout()
        fig.savefig(path, dpi=dpi, bbox_inches='tight')
        plt.close(fig)
        paths.append(path)

    return paths
