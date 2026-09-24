# -*- coding: utf-8 -*-
"""LR 系数：跨分群×特征系数热力图 + 跨分群 AUC 条形图。

注：不出「每分群一张」的 LR 系数条形图——与系数热力图信息重复、且随分群数量爆炸。
分群系数对比看热力图、模型判别力看 AUC 图即可。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

from .style import (
    AUC_TYPE_COLORS, FIGSIZE_BAR_WIDE, FIGSIZE_HEATMAP, GRID_COLOR, NEUTRAL_COLOR,
)


def _safe(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', '_', str(name).strip()) or 'x'


def chart_lr_heatmap(
    lr_coef_long: pd.DataFrame,
    out_dir: Path,
    top_n: int = 15,
    dim: Optional[str] = None,
    dpi: int = 300,
) -> List[Path]:
    """分群 × 特征 LR 标准化系数热力图（行=分群、列=特征 top-N、发散色以 0 为中心）。

    业务用法：一图判断"同一指标在不同分群里是否方向一致"——同列里出现红蓝
    切换就是符号冲突信号，往往意味着该特征不应作为通用规则。
    每个 `分群维度` 出一张图；可用 `dim` 限制到单一维度。
    """
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

    for d, sub in df.groupby('分群维度'):
        feat_rank = (sub.assign(_abs=sub['系数'].abs())
                     .groupby('特征')['_abs'].max()
                     .sort_values(ascending=False))
        keep = feat_rank.head(top_n).index.tolist()
        if not keep:
            continue

        sub2 = sub[sub['特征'].isin(keep)]
        pivot = sub2.pivot_table(
            index='分群名称', columns='特征', values='系数', aggfunc='mean',
        )
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

        vabs = float(np.nanmax(np.abs(data))) if not np.all(np.isnan(data)) else 1.0
        vabs = max(vabs, 0.05)
        im = ax.imshow(data, aspect='auto', cmap='RdBu_r', vmin=-vabs, vmax=vabs)

        ax.set_xticks(range(n_cols))
        ax.set_xticklabels(pivot.columns, rotation=30, ha='right', fontsize=9)
        ax.set_yticks(range(n_rows))
        ax.set_yticklabels(pivot.index, fontsize=9)
        ax.set_xlabel('特征指标')
        ax.set_ylabel(f'分群（{d}）')
        ax.set_title(f'分群 × 特征 LR 系数热力图 | {d}（top-{top_n}，红=负向 / 蓝=正向）')

        for i in range(n_rows):
            for j in range(n_cols):
                v = data[i, j]
                if np.isnan(v):
                    continue
                color = 'white' if abs(v) > vabs * 0.55 else '#2C3E50'
                ax.text(j, i, f'{v:.2f}', ha='center', va='center', fontsize=8, color=color)

        fig.colorbar(im, ax=ax, label='标准化系数', shrink=0.8)

        path = out_dir / f'lr_heatmap_{_safe(d)}_top{top_n}.png'
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

    def _auc_color(t: object) -> str:
        ts = str(t)
        # 子串匹配以兼容多种命名（如 "5折交叉验证" / "训练集(样本不足)"）
        if 'CV失败' in ts or 'cv失败' in ts.lower():
            return AUC_TYPE_COLORS['训练集-CV失败']
        if '训练集' in ts:
            return AUC_TYPE_COLORS['训练集-样本不足']
        if '交叉验证' in ts or 'CV' in ts.upper():
            return AUC_TYPE_COLORS['交叉验证']
        return NEUTRAL_COLOR

    colors = [_auc_color(t) for t in auc_types]

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

    # AUC 类型图例（按真实出现的字符串去重，颜色用语义匹配函数）
    seen = []
    handles = []
    for t in auc_types:
        ts = str(t)
        if ts in seen or not ts:
            continue
        seen.append(ts)
        handles.append(plt.Rectangle((0, 0), 1, 1,
                                      color=_auc_color(ts), label=ts))
    if handles:
        ax.legend(handles=handles, loc='lower right', fontsize=9, framealpha=0.9)

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / 'lr_auc_by_segment.png'
    fig.tight_layout()
    fig.savefig(path, dpi=dpi, bbox_inches='tight')
    plt.close(fig)
    return [path]
