# -*- coding: utf-8 -*-
"""LR 系数条形图（每分群一张）+ 跨分群 AUC 条形图。"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

import pandas as pd

from . import style  # 字体配置
from .style import (
    POS_COLOR, NEG_COLOR, AUC_TYPE_COLORS, FIGSIZE_BAR_TALL, FIGSIZE_BAR_WIDE,
    GRID_COLOR, NEUTRAL_COLOR,
)


def _safe(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', '_', str(name).strip()) or 'x'


def chart_lr_coef(
    lr_coef_long: pd.DataFrame,
    out_dir: Path,
    top_n: int = 15,
    dim: Optional[str] = None,
    dpi: int = 300,
) -> List[Path]:
    """LR 系数条形图：每个分群一张，按 |系数| 排序。"""
    import matplotlib.pyplot as plt

    if lr_coef_long is None or lr_coef_long.empty:
        return []
    needed = {'分群维度', '分群名称', '特征', '系数'}
    if not needed.issubset(lr_coef_long.columns):
        return []

    df = lr_coef_long.copy()
    df['系数'] = pd.to_numeric(df['系数'], errors='coerce')
    df = df.dropna(subset=['系数'])
    if dim:
        df = df[df['分群维度'] == dim]
    if df.empty:
        return []

    out_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []

    for (d, g), sub in df.groupby(['分群维度', '分群名称']):
        sub = sub.assign(_abs=sub['系数'].abs())
        sub = sub.sort_values('_abs', ascending=False).head(top_n)
        if sub.empty:
            continue
        sub = sub.sort_values('系数')
        colors = [POS_COLOR if v >= 0 else NEG_COLOR for v in sub['系数']]

        fig, ax = plt.subplots(figsize=FIGSIZE_BAR_TALL)
        ax.barh(sub['特征'], sub['系数'], color=colors, edgecolor='white')
        ax.axvline(0, color='#2C3E50', linewidth=0.8)
        ax.set_xlabel('标准化系数（正=与坏客户正相关）')
        ax.set_title(f'LR 标准化系数 Top-{top_n} | {d} = {g}')
        ax.grid(axis='x', color=GRID_COLOR, linewidth=0.6)
        ax.set_axisbelow(True)

        max_abs = float(sub['_abs'].max() or 1.0)
        for i, v in enumerate(sub['系数']):
            ax.text(v + (0.01 if v >= 0 else -0.01) * max_abs,
                    i, f'{v:.3f}',
                    va='center',
                    ha='left' if v >= 0 else 'right',
                    fontsize=9, color='#2C3E50')

        path = out_dir / f'lr_{_safe(d)}__{_safe(g)}_top{top_n}.png'
        fig.tight_layout()
        fig.savefig(path, dpi=dpi, bbox_inches='tight')
        plt.close(fig)
        paths.append(path)

    return paths


def chart_lr_auc(
    lr_auc_long: pd.DataFrame,
    out_dir: Path,
    dim: Optional[str] = None,
    dpi: int = 300,
) -> List[Path]:
    """跨分群 AUC 条形图（一张），按 AUC 类型着色。"""
    import matplotlib.pyplot as plt

    if lr_auc_long is None or lr_auc_long.empty:
        return []
    needed = {'分群维度', '分群名称', 'AUC'}
    if not needed.issubset(lr_auc_long.columns):
        return []

    df = lr_auc_long.copy()
    df['AUC'] = pd.to_numeric(df['AUC'], errors='coerce')
    df = df.dropna(subset=['AUC'])
    if dim:
        df = df[df['分群维度'] == dim]
    if df.empty:
        return []

    df = df.sort_values('AUC', ascending=True)
    df['_label'] = df['分群维度'].astype(str) + ' = ' + df['分群名称'].astype(str)
    auc_types = df.get('AUC类型', pd.Series([''] * len(df), index=df.index))
    colors = [AUC_TYPE_COLORS.get(str(t), NEUTRAL_COLOR) for t in auc_types]

    fig, ax = plt.subplots(figsize=FIGSIZE_BAR_WIDE)
    bars = ax.barh(df['_label'], df['AUC'], color=colors, edgecolor='white')
    ax.axvline(0.5, color=NEUTRAL_COLOR, linestyle=':', linewidth=1, alpha=0.7,
               label='AUC=0.5（随机）')
    ax.axvline(0.7, color='#2E86C1', linestyle=':', linewidth=1, alpha=0.5,
               label='AUC=0.7（可用）')
    ax.set_xlim(0, 1)
    ax.set_xlabel('AUC')
    ax.set_title('跨分群模型 AUC 对比（按 AUC 类型着色）')
    ax.grid(axis='x', color=GRID_COLOR, linewidth=0.6)
    ax.set_axisbelow(True)

    for bar, val, t in zip(bars, df['AUC'], auc_types):
        ax.text(bar.get_width() + 0.01, bar.get_y() + bar.get_height() / 2,
                f'{val:.3f}', va='center', fontsize=9, color='#2C3E50')

    # AUC 类型图例
    seen = []
    handles = [plt.Line2D([0], [0], marker='|', color='black', linestyle='None')]  # placeholder
    handles = []
    for t in auc_types:
        ts = str(t)
        if ts in seen or not ts:
            continue
        seen.append(ts)
        handles.append(plt.Rectangle((0, 0), 1, 1,
                                      color=AUC_TYPE_COLORS.get(ts, NEUTRAL_COLOR),
                                      label=ts))
    if handles:
        ax.legend(handles=handles, loc='lower right', fontsize=9, framealpha=0.9)

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / 'lr_auc_by_segment.png'
    fig.tight_layout()
    fig.savefig(path, dpi=dpi, bbox_inches='tight')
    plt.close(fig)
    return [path]
