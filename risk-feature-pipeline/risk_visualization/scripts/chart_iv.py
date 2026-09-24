# -*- coding: utf-8 -*-
"""IV 可视化：全量 IV 横向条形图 + 分群 IV 热力图（每维度一张）。"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

from . import style  # noqa: F401  触发字体配置
from .config import IV_LEVEL_BINS, IV_SUSPECT_THRESHOLD
from .style import (
    IV_LEVEL_COLORS, FIGSIZE_BAR_TALL, FIGSIZE_HEATMAP, GRID_COLOR,
)


def _safe(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', '_', str(name).strip()) or 'x'


def _iv_level(iv: float) -> str:
    if iv is None or pd.isna(iv):
        return '无'
    for label, lo, hi in IV_LEVEL_BINS:
        if lo <= iv < hi:
            return label
    return '疑似数据穿越'


def chart_iv_full(
    iv_full: pd.DataFrame,
    out_dir: Path,
    top_n: int = 15,
    dpi: int = 300,
) -> List[Path]:
    """全量 IV 横向条形图（top-N，按预测能力着色）。"""
    import matplotlib.pyplot as plt

    if iv_full is None or iv_full.empty or '特征' not in iv_full.columns or 'IV值' not in iv_full.columns:
        return []

    df = iv_full[['特征', 'IV值']].dropna().copy()
    df['IV值'] = pd.to_numeric(df['IV值'], errors='coerce')
    df = df.dropna(subset=['IV值']).sort_values('IV值', ascending=False).head(top_n)
    if df.empty:
        return []
    df = df.iloc[::-1]  # 横向条形从下往上看，反转让最大值在最上

    df['等级'] = df['IV值'].apply(_iv_level)
    colors = [IV_LEVEL_COLORS.get(lv, '#7F8C8D') for lv in df['等级']]

    fig, ax = plt.subplots(figsize=FIGSIZE_BAR_TALL)
    bars = ax.barh(df['特征'], df['IV值'], color=colors, edgecolor='white')

    # 疑似数据穿越（IV 过高）用斜线标注
    for bar, lv in zip(bars, df['等级']):
        if lv == '疑似数据穿越':
            bar.set_hatch('//')

    # 数值标注
    for bar, val in zip(bars, df['IV值']):
        ax.text(bar.get_width() + max(df['IV值']) * 0.005,
                bar.get_y() + bar.get_height() / 2,
                f'{val:.3f}', va='center', fontsize=9, color='#2C3E50')

    ax.axvline(IV_SUSPECT_THRESHOLD, color='#7B241C', linestyle='--', linewidth=1, alpha=0.5,
               label=f'疑似数据穿越线 ({IV_SUSPECT_THRESHOLD})')
    ax.set_xlabel('IV 值')
    ax.set_title(f'全量 IV Top-{top_n}（按预测能力着色，斜线=疑似数据穿越）')
    ax.grid(axis='x', color=GRID_COLOR, linewidth=0.6)
    ax.set_axisbelow(True)

    # 图例（按等级）
    seen = []
    handles = []
    for lv in df['等级']:
        if lv in seen:
            continue
        seen.append(lv)
        handles.append(plt.Rectangle((0, 0), 1, 1, color=IV_LEVEL_COLORS.get(lv, '#7F8C8D'),
                                      label=lv))
    if handles:
        ax.legend(handles=handles, loc='lower right', fontsize=9, framealpha=0.9)

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f'iv_full_top{top_n}.png'
    fig.tight_layout()
    fig.savefig(path, dpi=dpi, bbox_inches='tight')
    plt.close(fig)
    return [path]


def chart_iv_heatmap(
    iv_group_all: pd.DataFrame,
    iv_full: Optional[pd.DataFrame],
    out_dir: Path,
    top_n: int = 15,
    dpi: int = 300,
) -> List[Path]:
    """分群 × 特征 IV 热力图（**每个分群维度一张**）。

    与 corr_heatmap / lr_heatmap 同口径：
    - **横轴（列）= 特征指标**（取全量 IV top-N，跨维度统一顺序）
    - **纵轴（行）= 同一维度下的各分群**（如 `企业规模` → 大型/中型/小型/微型企业）
    - 每个 `分群维度` 单独出一张图，避免不同维度的分群混排在一张表里
    - 可信度为「不可信」的单元用 `X` 覆盖（取自 `IV可信度` 列）
    """
    import matplotlib.pyplot as plt

    if iv_group_all is None or iv_group_all.empty:
        return []
    needed = {'分群维度', '分群名称', '特征', 'IV值'}
    if not needed.issubset(iv_group_all.columns):
        return []

    df = iv_group_all.copy()
    df['IV值'] = pd.to_numeric(df['IV值'], errors='coerce')
    df = df.dropna(subset=['IV值'])
    if df.empty:
        return []

    # 特征列顺序：优先按全量 IV 降序（跨维度统一），否则各维度内按平均 IV
    feat_order: Optional[List[str]] = None
    if iv_full is not None and not iv_full.empty and {'特征', 'IV值'}.issubset(iv_full.columns):
        ivf = iv_full[['特征', 'IV值']].copy()
        ivf['IV值'] = pd.to_numeric(ivf['IV值'], errors='coerce')
        feat_order = (ivf.dropna(subset=['IV值'])
                      .sort_values('IV值', ascending=False)['特征'].astype(str).tolist())

    has_rel = 'IV可信度' in df.columns
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []

    for d, sub in df.groupby('分群维度'):
        feats_here = set(sub['特征'].astype(str))
        if feat_order:
            keep = [f for f in feat_order if f in feats_here][:top_n]
        else:
            keep = (sub.groupby('特征')['IV值'].mean()
                    .sort_values(ascending=False).head(top_n).index.astype(str).tolist())
        if not keep:
            continue

        sub2 = sub[sub['特征'].astype(str).isin(keep)]
        pivot = sub2.pivot_table(
            index='分群名称', columns='特征', values='IV值', aggfunc='mean',
        )
        pivot = pivot.reindex(columns=keep)
        pivot = pivot.reindex(index=sorted(pivot.index, key=lambda x: str(x)))
        if pivot.empty:
            continue

        rel_pivot = None
        if has_rel:
            rel_pivot = (sub2.pivot_table(
                index='分群名称', columns='特征', values='IV可信度', aggfunc='first')
                .reindex(index=pivot.index, columns=pivot.columns))

        n_rows, n_cols = pivot.shape
        base_w, base_h = FIGSIZE_HEATMAP
        height = max(3.0, min(base_h, 0.55 * n_rows + 2.0))
        width = max(base_w, 0.55 * n_cols + 4.0)

        fig, ax = plt.subplots(figsize=(width, height))
        data = pivot.values.astype(float)

        vmax = float(np.nanmax(data)) if not np.all(np.isnan(data)) else 1.0
        vmax = min(max(vmax, 0.3), IV_SUSPECT_THRESHOLD)  # 疑似数据穿越的高 IV 值不主导色阶
        im = ax.imshow(data, aspect='auto', cmap='RdBu_r', vmin=0, vmax=vmax)

        ax.set_xticks(range(n_cols))
        ax.set_xticklabels(pivot.columns, rotation=30, ha='right', fontsize=9)
        ax.set_yticks(range(n_rows))
        ax.set_yticklabels(pivot.index, fontsize=9)
        ax.set_xlabel('特征指标')
        ax.set_ylabel(f'分群（{d}）')
        ax.set_title(f'分群 × 特征 IV 热力图 | {d}（top-{top_n}；X = 不可信）')

        for i in range(n_rows):
            for j in range(n_cols):
                v = data[i, j]
                if np.isnan(v):
                    continue
                color = 'white' if v > vmax * 0.6 else '#2C3E50'
                ax.text(j, i, f'{v:.2f}', ha='center', va='center', fontsize=8, color=color)
                if rel_pivot is not None:
                    rv = rel_pivot.iloc[i, j]
                    if isinstance(rv, str) and rv.startswith('不可信'):
                        ax.text(j, i + 0.28, 'X', ha='center', va='center',
                                fontsize=10, color='#7B241C', fontweight='bold')

        fig.colorbar(im, ax=ax, label='IV 值', shrink=0.8)

        path = out_dir / f'iv_heatmap_{_safe(d)}_top{top_n}.png'
        fig.tight_layout()
        fig.savefig(path, dpi=dpi, bbox_inches='tight')
        plt.close(fig)
        paths.append(path)

    return paths
