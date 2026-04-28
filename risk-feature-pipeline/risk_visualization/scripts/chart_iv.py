# -*- coding: utf-8 -*-
"""IV 可视化：全量 IV 横向条形图 + 分群 IV 热力图。"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

from . import style  # 触发字体配置
from .config import IV_LEVEL_BINS, IV_SUSPECT_THRESHOLD
from .style import (
    IV_LEVEL_COLORS, FIGSIZE_BAR_TALL, FIGSIZE_HEATMAP, GRID_COLOR,
)


def _iv_level(iv: float) -> str:
    if iv is None or pd.isna(iv):
        return '无'
    for label, lo, hi in IV_LEVEL_BINS:
        if lo <= iv < hi:
            return label
    return '过拟合嫌疑'


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

    # 过拟合嫌疑用斜线标注
    for bar, lv in zip(bars, df['等级']):
        if lv == '过拟合嫌疑':
            bar.set_hatch('//')

    # 数值标注
    for bar, val in zip(bars, df['IV值']):
        ax.text(bar.get_width() + max(df['IV值']) * 0.005,
                bar.get_y() + bar.get_height() / 2,
                f'{val:.3f}', va='center', fontsize=9, color='#2C3E50')

    ax.axvline(IV_SUSPECT_THRESHOLD, color='#7B241C', linestyle='--', linewidth=1, alpha=0.5,
               label=f'过拟合嫌疑线 ({IV_SUSPECT_THRESHOLD})')
    ax.set_xlabel('IV 值')
    ax.set_title(f'全量 IV Top-{top_n}（按预测能力着色，斜线=过拟合嫌疑）')
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
    iv_pivot: pd.DataFrame,
    reliability_pivot: Optional[pd.DataFrame],
    iv_full: Optional[pd.DataFrame],
    out_dir: Path,
    top_n: int = 15,
    dpi: int = 300,
) -> List[Path]:
    """分群 IV 热力图（行=特征 top-N，列=分群）。可信度不足单元用 ✗ 叠加。"""
    import matplotlib.pyplot as plt

    if iv_pivot is None or iv_pivot.empty:
        return []

    df = iv_pivot.copy()
    # 透视表两种合法朝向：
    #   A. index=特征, columns=分群 (set_index('特征') 后)
    #   B. index=分群, columns=特征 (CSV 第一列 '分群名称' / '分群')
    # 用 iv_full.特征 与两轴的交集大小判断
    feat_universe = set()
    if iv_full is not None and not iv_full.empty and '特征' in iv_full.columns:
        feat_universe = set(iv_full['特征'].dropna().astype(str))

    for col_name in ('特征', '分群名称', '分群'):
        if col_name in df.columns:
            df = df.set_index(col_name)
            break
    df = df.apply(pd.to_numeric, errors='coerce')

    overlap_index = len(feat_universe & set(map(str, df.index))) if feat_universe else 0
    overlap_cols = len(feat_universe & set(map(str, df.columns))) if feat_universe else 0
    if overlap_cols > overlap_index and overlap_cols > 0:
        # 朝向 B：转置成「特征=行，分群=列」
        df = df.T

    # 选 top-N 特征：优先按全量 IV 排，否则按行均值
    if feat_universe:
        order = (iv_full[['特征', 'IV值']].dropna()
                 .sort_values('IV值', ascending=False)['特征'].astype(str).tolist())
        keep = [f for f in order if f in df.index][:top_n]
    else:
        keep = df.mean(axis=1).sort_values(ascending=False).head(top_n).index.tolist()
    df = df.loc[keep]
    if df.empty:
        return []

    # 可信度 mask（同样自适应朝向）
    rel = None
    if reliability_pivot is not None and not reliability_pivot.empty:
        rel = reliability_pivot.copy()
        for col_name in ('特征', '分群名称', '分群'):
            if col_name in rel.columns:
                rel = rel.set_index(col_name)
                break
        # 与 df 对齐朝向
        if not set(df.index).issubset(set(rel.index)):
            rel = rel.T
        rel = rel.reindex(index=df.index, columns=df.columns)

    fig, ax = plt.subplots(figsize=FIGSIZE_HEATMAP)
    data = df.values.astype(float)

    vmax = float(np.nanmax(data)) if not np.all(np.isnan(data)) else 1.0
    vmax = min(max(vmax, 0.3), IV_SUSPECT_THRESHOLD)  # 过拟合嫌疑值不主导色阶
    im = ax.imshow(data, aspect='auto', cmap='RdBu_r', vmin=0, vmax=vmax)

    ax.set_xticks(range(len(df.columns)))
    ax.set_xticklabels(df.columns, rotation=30, ha='right', fontsize=9)
    ax.set_yticks(range(len(df.index)))
    ax.set_yticklabels(df.index, fontsize=9)

    # 文本叠加：IV 值 + 可信度 ✗
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            v = data[i, j]
            if np.isnan(v):
                continue
            txt = f'{v:.2f}'
            color = 'white' if v > vmax * 0.6 else '#2C3E50'
            ax.text(j, i, txt, ha='center', va='center', fontsize=8, color=color)

            if rel is not None:
                rv = rel.iloc[i, j] if (i < rel.shape[0] and j < rel.shape[1]) else None
                if isinstance(rv, str) and rv.startswith('不可信'):
                    ax.text(j, i + 0.28, 'X', ha='center', va='center',
                            fontsize=10, color='#7B241C', fontweight='bold')

    ax.set_title(f'分群 IV 热力图（top-{top_n} 特征；X = 不可信）')
    fig.colorbar(im, ax=ax, label='IV 值', shrink=0.8)

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f'iv_heatmap_top{top_n}.png'
    fig.tight_layout()
    fig.savefig(path, dpi=dpi, bbox_inches='tight')
    plt.close(fig)
    return [path]
