# -*- coding: utf-8 -*-
"""候选阈值可视化：每个 pair 的分箱坏率柱图 + 分群内风险倍数对比图。"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

from . import style  # 触发字体配置
from .style import (
    FIGSIZE_BAR_WIDE, FIGSIZE_BAR_TALL, GRID_COLOR,
    POS_COLOR, NEG_COLOR, NEUTRAL_COLOR, ANNO_COLOR,
)


_FNAME_SAFE = re.compile(r'[\\/:\s　]+')


def _slug(s: str) -> str:
    """文件名安全化：保留中文，替换不安全字符为下划线。"""
    return _FNAME_SAFE.sub('_', str(s)).strip('_') or 'x'


def _parse_bin_bounds(bin_str: str) -> tuple[float, float, str]:
    """解析 optbinning binning_table 的 Bin 列文本（形如 '(-inf, 0.42]'）。

    返回 (lo, hi, label)。无法解析时返回 (NaN, NaN, raw)。
    """
    raw = str(bin_str)
    s = raw.strip()
    if not s.startswith(('(', '[')) or not s.endswith((')', ']')):
        return float('nan'), float('nan'), raw
    inner = s[1:-1]
    parts = inner.split(',')
    if len(parts) != 2:
        return float('nan'), float('nan'), raw
    try:
        lo = float(parts[0].strip())
    except ValueError:
        lo = float('-inf')
    try:
        hi = float(parts[1].strip())
    except ValueError:
        hi = float('inf')
    return lo, hi, raw


def chart_threshold_binning(
    detail_df: Optional[pd.DataFrame],
    summary_df: Optional[pd.DataFrame],
    out_dir: Path,
    dpi: int = 300,
) -> List[Path]:
    """每个 (分群维度, 分群名称, 特征) 一张分箱坏率柱图 + 候选阈值标注。"""
    import matplotlib.pyplot as plt

    if detail_df is None or detail_df.empty:
        return []
    if summary_df is None or summary_df.empty:
        return []

    needed_summary = {'分群维度', '分群名称', '特征', '候选阈值', '风险方向', '风险倍数', '规则有效'}
    if not needed_summary.issubset(summary_df.columns):
        return []
    needed_detail = {'分群维度', '分群名称', '特征', '分箱', '坏率'}
    if not needed_detail.issubset(detail_df.columns):
        return []

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []

    for (dim, group, feat), sub in detail_df.groupby(['分群维度', '分群名称', '特征'], sort=False):
        meta_rows = summary_df[
            (summary_df['分群维度'] == dim)
            & (summary_df['分群名称'] == group)
            & (summary_df['特征'] == feat)
        ]
        if meta_rows.empty:
            continue
        meta = meta_rows.iloc[0]
        cutoff = pd.to_numeric(pd.Series([meta['候选阈值']]), errors='coerce').iloc[0]
        if pd.isna(cutoff):
            continue
        direction = str(meta['风险方向'])
        risk_ratio = pd.to_numeric(pd.Series([meta['风险倍数']]), errors='coerce').iloc[0]
        valid = bool(meta['规则有效'])

        rates = pd.to_numeric(sub['坏率'], errors='coerce').fillna(0.0).values
        counts = pd.to_numeric(sub.get('样本数', pd.Series([0] * len(sub))), errors='coerce').fillna(0).astype(int).values
        bins = sub['分箱'].astype(str).tolist()
        bin_centers = list(range(len(bins)))
        # 解析每个 bin 的下/上界：下界用于颜色判定（inf 不会短路），上界用于定位候选阈值竖线
        parsed = [_parse_bin_bounds(b) for b in bins]
        uppers = [hi for _, hi, _ in parsed]

        colors = []
        for lo, hi, _ in parsed:
            if direction == 'positive':
                # bin 整体在 cutoff 右侧（含 [cutoff, inf)）→ 高风险
                is_high = lo >= cutoff
            else:
                # bin 整体在 cutoff 左侧（含 (-inf, cutoff]）→ 高风险
                is_high = hi <= cutoff
            colors.append(NEG_COLOR if is_high else POS_COLOR)

        fig, ax = plt.subplots(figsize=FIGSIZE_BAR_WIDE)
        bars = ax.bar(bin_centers, rates, color=colors, edgecolor='white')

        # 顶部标注：坏率 + 样本数
        for i, (bar, r, c) in enumerate(zip(bars, rates, counts)):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + max(rates.max() if len(rates) else 0.01, 0.005) * 0.02,
                    f'{r:.1%}\nn={c}', ha='center', va='bottom',
                    fontsize=8, color=ANNO_COLOR)

        # 候选阈值竖线：定位在 cutoff 对应的边界（bin upper bound 命中处）
        cutoff_idx = None
        for i, upp in enumerate(uppers):
            if np.isfinite(upp) and abs(upp - float(cutoff)) < 1e-9:
                cutoff_idx = i + 0.5  # 落在第 i 个 bin 与第 i+1 个 bin 的边界
                break
        if cutoff_idx is not None:
            ax.axvline(cutoff_idx, color='#7B241C', linestyle='--', linewidth=1.5,
                       label=f'候选阈值 = {cutoff:.4f}')

        ax.set_xticks(bin_centers)
        ax.set_xticklabels(bins, rotation=30, ha='right', fontsize=8)
        ax.set_ylabel('分箱坏客户率')
        op = '大于' if direction == 'positive' else '小于等于'
        valid_tag = '[有效]' if valid else '[未通过]'
        title = (f'{dim}.{group} - {feat}\n'
                 f'方向={direction}（高风险 = {op} {cutoff:.4f}）| '
                 f'风险倍数={risk_ratio:.2f}x | {valid_tag}')
        ax.set_title(title, fontsize=11)
        ax.grid(axis='y', color=GRID_COLOR, linewidth=0.6)
        ax.set_axisbelow(True)
        if cutoff_idx is not None:
            ax.legend(loc='best', fontsize=9, framealpha=0.9)

        fname = f'threshold_binning_{_slug(dim)}_{_slug(group)}_{_slug(feat)}.png'
        path = out_dir / fname
        fig.tight_layout()
        fig.savefig(path, dpi=dpi, bbox_inches='tight')
        plt.close(fig)
        paths.append(path)

    return paths


def chart_threshold_summary(
    summary_df: Optional[pd.DataFrame],
    out_dir: Path,
    dpi: int = 300,
) -> List[Path]:
    """按分群维度分组的候选规则风险倍数横向条形图。"""
    import matplotlib.pyplot as plt

    if summary_df is None or summary_df.empty:
        return []
    needed = {'分群维度', '分群名称', '特征', '风险倍数', '规则有效'}
    if not needed.issubset(summary_df.columns):
        return []

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []

    df = summary_df.copy()
    df['风险倍数'] = pd.to_numeric(df['风险倍数'], errors='coerce')
    df = df.dropna(subset=['风险倍数'])
    if df.empty:
        return []

    for dim, sub in df.groupby('分群维度', sort=False):
        sub = sub.sort_values('风险倍数', ascending=True)
        labels = sub.apply(lambda r: f'{r["分群名称"]} | {r["特征"]}', axis=1).tolist()
        ratios = sub['风险倍数'].tolist()
        valid_flags = sub['规则有效'].astype(bool).tolist()
        colors = [NEG_COLOR if v else NEUTRAL_COLOR for v in valid_flags]

        height = max(3.0, min(0.5 * len(labels) + 1.5, 14.0))
        fig, ax = plt.subplots(figsize=(FIGSIZE_BAR_TALL[0], height))
        bars = ax.barh(labels, ratios, color=colors, edgecolor='white')
        ax.axvline(1.0, color=NEUTRAL_COLOR, linestyle=':', linewidth=1, alpha=0.7,
                   label='Lift=1 基线')

        for bar, val, v in zip(bars, ratios, valid_flags):
            ax.text(bar.get_width() + max(ratios) * 0.01,
                    bar.get_y() + bar.get_height() / 2,
                    f'{val:.2f}x' + ('' if v else '（未通过）'),
                    va='center', fontsize=9, color=ANNO_COLOR)

        ax.set_xlabel('风险倍数（高风险侧坏率 / 低风险侧坏率）')
        ax.set_title(f'{dim} - 候选规则风险倍数对比')
        ax.grid(axis='x', color=GRID_COLOR, linewidth=0.6)
        ax.set_axisbelow(True)
        ax.legend(loc='lower right', fontsize=9, framealpha=0.9)

        fname = f'threshold_summary_{_slug(dim)}.png'
        path = out_dir / fname
        fig.tight_layout()
        fig.savefig(path, dpi=dpi, bbox_inches='tight')
        plt.close(fig)
        paths.append(path)

    return paths


__all__ = ['chart_threshold_binning', 'chart_threshold_summary']
