# -*- coding: utf-8 -*-
"""单变量分析顺手出箱形图（好坏对比 + 分群对比）。

与 `risk_visualization` 那条「只读 CSV」路径不同：箱形图需要原始数值分布，
所以由 `risk_segment_univariate` 在跑分析时直接消费 wide 表（`df` + 数值
`feature_cols`），把图直接写到 `output/<project>/charts/boxplots/`。

只生成两类图（每类合成一张大 PNG，避免文件爆炸）：

1. `box_good_bad_grid_top<N>.png`
   - 全样本 "好客户 vs 坏客户" 对比，top-N 特征做小多图
   - 业务用法：扫一遍哪些指标真的能把好坏分开
2. `box_by_<dim>_grid_top<N>.png`（每个分群维度一张）
   - X 轴 = 分群值（如 小型/中型/大型企业），Y 轴 = 特征值
   - 同一分群内 "好/坏" 用色区分（hue 风格）
   - 业务用法：看指标分布在不同分群下是否漂移、好坏可分性是否随分群退化

特征排序：按 |点二列相关| 与 target 的关系全样本排序后取 top-N。
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import List, Optional, Sequence

import numpy as np
import pandas as pd

# 确保 risk-feature-pipeline/ 在 sys.path 上（boxplot 可能被独立导入）
_SKILL_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _SKILL_ROOT not in sys.path:
    sys.path.insert(0, _SKILL_ROOT)

# 颜色与样式（不依赖 risk_visualization.style，避免循环依赖）
_GOOD_COLOR = '#2E86C1'   # 蓝
_BAD_COLOR = '#C0392B'    # 红
_NEUTRAL_COLOR = '#7F8C8D'
_GRID_COLOR = '#E5E7E9'

# 防止数据全 NaN 或全为常数时的兜底标识
_DEGENERATE_LABEL = '(数据不足)'


def _configure_chinese_font_once() -> None:
    """转发到管线级共享的字体配置入口（risk_pipeline.font_utils）。

    历史上这里调用过 `risk_visualization.scripts.font_utils`，但那条路径
    在 risk_visualization 没被加载时会静默失败，导致中文渲染成方框。
    现在固定走 `risk_pipeline.font_utils`，与 risk_visualization 同源。
    """
    from risk_pipeline.font_utils import configure_chinese_font
    configure_chinese_font()


def _rank_features_by_corr(
    df: pd.DataFrame, feature_cols: Sequence[str], target: str, top_n: int,
) -> List[str]:
    """全样本按 |点二列相关系数| 排序，取 top_n。"""
    if not feature_cols or target not in df.columns:
        return []
    y = pd.to_numeric(df[target], errors='coerce')
    scores = []
    for f in feature_cols:
        if f not in df.columns:
            continue
        x = pd.to_numeric(df[f], errors='coerce')
        sub = pd.concat([x, y], axis=1).dropna()
        if len(sub) < 30 or sub.iloc[:, 0].std() == 0:
            continue
        # numpy.corrcoef 在常数列上会 RuntimeWarning，前置过滤已避免
        c = float(sub.corr().iloc[0, 1])
        if not math.isnan(c):
            scores.append((f, abs(c)))
    scores.sort(key=lambda x: x[1], reverse=True)
    return [f for f, _ in scores[:top_n]]


def _grid_dims(n: int) -> tuple[int, int]:
    """按特征数选合适的子图行列数。优先 4 列，行数向上取整。"""
    if n <= 0:
        return (1, 1)
    if n <= 4:
        return (1, n)
    cols = 4 if n > 6 else 3
    rows = math.ceil(n / cols)
    return (rows, cols)


def _trim_for_box(values: pd.Series, q_low: float = 0.005, q_high: float = 0.995) -> pd.Series:
    """温和裁剪极端尾部，让箱形不被两个孤立点拉成线段。
    业务上风控特征常有极端值（除零、未填默认大值），保留 0.5%~99.5% 区间足以
    判断分布形态；离群点本身另有"离群点扫描"图覆盖。
    """
    s = pd.to_numeric(values, errors='coerce').dropna()
    if len(s) < 20:
        return s
    lo, hi = s.quantile([q_low, q_high])
    if lo == hi:
        return s
    return s[(s >= lo) & (s <= hi)]


# ---------- 1. 好客户 vs 坏客户（全样本，小多图）----------

def chart_box_good_bad(
    df: pd.DataFrame,
    feature_cols: Sequence[str],
    out_dir: Path,
    target: str = 'is_bad',
    top_n: int = 12,
    dpi: int = 200,
) -> Optional[Path]:
    """全样本下 "好/坏" 对比箱形图（top-N 特征做小多图）。"""
    import matplotlib.pyplot as plt
    _configure_chinese_font_once()

    if df is None or df.empty or target not in df.columns:
        return None
    feats = _rank_features_by_corr(df, feature_cols, target, top_n)
    if not feats:
        return None

    rows, cols = _grid_dims(len(feats))
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 3.3, rows * 3.0), squeeze=False)

    for idx, feat in enumerate(feats):
        r, c = divmod(idx, cols)
        ax = axes[r][c]

        good = _trim_for_box(df.loc[df[target] == 0, feat])
        bad = _trim_for_box(df.loc[df[target] == 1, feat])

        # 至少一边有数据才画
        if good.empty and bad.empty:
            ax.text(0.5, 0.5, _DEGENERATE_LABEL, ha='center', va='center',
                    transform=ax.transAxes, color=_NEUTRAL_COLOR, fontsize=10)
            ax.set_title(feat, fontsize=10)
            ax.axis('off')
            continue

        data = [good.values, bad.values]
        bp = ax.boxplot(
            data, positions=[0, 1], widths=0.55, patch_artist=True,
            showfliers=False,  # 离群点已被 _trim_for_box 截断，避免干扰
            medianprops=dict(color='#2C3E50', linewidth=1.5),
            whiskerprops=dict(color=_NEUTRAL_COLOR),
            capprops=dict(color=_NEUTRAL_COLOR),
            flierprops=dict(marker='o', markersize=2, alpha=0.4),
        )
        for patch, color in zip(bp['boxes'], [_GOOD_COLOR, _BAD_COLOR]):
            patch.set_facecolor(color)
            patch.set_alpha(0.65)

        ax.set_xticks([0, 1])
        ax.set_xticklabels(
            [f'好\nn={len(good)}', f'坏\nn={len(bad)}'], fontsize=9,
        )
        ax.set_title(feat, fontsize=10)
        ax.grid(axis='y', color=_GRID_COLOR, linewidth=0.6)
        ax.set_axisbelow(True)

    # 关闭多余空子图
    for idx in range(len(feats), rows * cols):
        r, c = divmod(idx, cols)
        axes[r][c].axis('off')

    fig.suptitle(
        f'全样本 好/坏 客户特征分布对比（top-{len(feats)}，按 |相关系数| 排序）',
        fontsize=12, y=1.005,
    )
    fig.tight_layout()

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f'box_good_bad_grid_top{len(feats)}.png'
    fig.savefig(path, dpi=dpi, bbox_inches='tight')
    plt.close(fig)
    return path


# ---------- 2. 分群箱形图（每分群维度一张）----------

def chart_box_by_segment(
    df: pd.DataFrame,
    feature_cols: Sequence[str],
    dim_col: str,
    out_dir: Path,
    target: str = 'is_bad',
    top_n: int = 12,
    dpi: int = 200,
    min_group_size: int = 30,
) -> Optional[Path]:
    """每个分群维度一张图：top-N 特征做小多图，每个子图 X 轴是分群值，
    每个分群内并排两个箱（好/坏，颜色区分）。"""
    import matplotlib.pyplot as plt
    _configure_chinese_font_once()

    if df is None or df.empty or dim_col not in df.columns or target not in df.columns:
        return None

    df_v = df[df[dim_col].notna()].copy()
    if df_v.empty:
        return None

    # 过滤过小分群
    grp_sizes = df_v.groupby(dim_col).size()
    keep_groups = grp_sizes[grp_sizes >= min_group_size].sort_values(ascending=False).index.tolist()
    if not keep_groups:
        return None

    feats = _rank_features_by_corr(df_v, feature_cols, target, top_n)
    if not feats:
        return None

    rows, cols = _grid_dims(len(feats))
    # 子图宽度按分群数线性扩展（每个分群留约 0.9 寸）
    sub_w = max(3.5, 0.9 * len(keep_groups) + 1.5)
    fig, axes = plt.subplots(rows, cols, figsize=(cols * sub_w, rows * 3.0), squeeze=False)

    for idx, feat in enumerate(feats):
        r, c = divmod(idx, cols)
        ax = axes[r][c]

        positions = []
        data = []
        colors = []
        x_centers = []
        x_labels = []

        gap = 0.3  # 分群之间间距
        cluster_w = 0.9  # 一个分群（好+坏）内部宽度
        for gi, gname in enumerate(keep_groups):
            base = gi * (cluster_w + gap)
            sub = df_v[df_v[dim_col] == gname]
            good = _trim_for_box(sub.loc[sub[target] == 0, feat])
            bad = _trim_for_box(sub.loc[sub[target] == 1, feat])
            if not good.empty:
                positions.append(base + 0)
                data.append(good.values)
                colors.append(_GOOD_COLOR)
            if not bad.empty:
                positions.append(base + 0.45)
                data.append(bad.values)
                colors.append(_BAD_COLOR)
            x_centers.append(base + 0.225)
            x_labels.append(str(gname))

        if not data:
            ax.text(0.5, 0.5, _DEGENERATE_LABEL, ha='center', va='center',
                    transform=ax.transAxes, color=_NEUTRAL_COLOR, fontsize=10)
            ax.set_title(feat, fontsize=10)
            ax.axis('off')
            continue

        bp = ax.boxplot(
            data, positions=positions, widths=0.4, patch_artist=True,
            showfliers=False,
            medianprops=dict(color='#2C3E50', linewidth=1.2),
            whiskerprops=dict(color=_NEUTRAL_COLOR),
            capprops=dict(color=_NEUTRAL_COLOR),
        )
        for patch, color in zip(bp['boxes'], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.65)

        ax.set_xticks(x_centers)
        ax.set_xticklabels(x_labels, fontsize=9, rotation=20, ha='right')
        ax.set_title(feat, fontsize=10)
        ax.grid(axis='y', color=_GRID_COLOR, linewidth=0.6)
        ax.set_axisbelow(True)

    # 关闭多余空子图
    for idx in range(len(feats), rows * cols):
        r, c = divmod(idx, cols)
        axes[r][c].axis('off')

    # 全图共享图例
    legend_handles = [
        plt.Rectangle((0, 0), 1, 1, color=_GOOD_COLOR, alpha=0.65, label='好客户'),
        plt.Rectangle((0, 0), 1, 1, color=_BAD_COLOR, alpha=0.65, label='坏客户'),
    ]
    fig.legend(handles=legend_handles, loc='upper right',
               bbox_to_anchor=(0.99, 1.005), fontsize=10, framealpha=0.9, ncol=2)

    fig.suptitle(
        f'分群 × 特征 箱形分布对比 | {dim_col}（top-{len(feats)}，每个分群内并排好/坏）',
        fontsize=12, y=1.005,
    )
    fig.tight_layout()

    out_dir.mkdir(parents=True, exist_ok=True)
    # dim_col 里可能含 / : 等字符，做基本清洗
    safe_dim = ''.join(ch if ch.isalnum() or ch in '_-' else '_' for ch in str(dim_col))
    path = out_dir / f'box_by_{safe_dim}_grid_top{len(feats)}.png'
    fig.savefig(path, dpi=dpi, bbox_inches='tight')
    plt.close(fig)
    return path


# ---------- 顶层封装：单变量步骤里一次调用 ----------

def generate_boxplots_for_univariate(
    df: pd.DataFrame,
    feature_cols: Sequence[str],
    category_dims: Sequence[str],
    project_name: str,
    target: str = 'is_bad',
    top_n: int = 12,
    dpi: int = 200,
    out_dir: Optional[Path] = None,
    verbose: bool = True,
) -> List[Path]:
    """单变量步骤的统一调用入口。

    生成：
        - 1 张 全样本"好/坏"对比图
        - len(category_dims) 张 分群对比图（每个维度一张）

    Returns:
        所有生成的 PNG 路径列表（失败的步骤自动跳过，不抛异常）
    """
    paths: List[Path] = []
    if df is None or df.empty:
        if verbose:
            print('  [跳过 boxplot] 宽表为空')
        return paths

    if out_dir is None:
        try:
            from risk_pipeline.paths import output_dir as _output_dir, ensure_writable_dir
            base = Path(_output_dir(project_name)) / 'charts' / 'boxplots'
            ensure_writable_dir(base)
            out_dir = base
        except Exception as e:
            if verbose:
                print(f'  [跳过 boxplot] 无法解析输出目录: {e}')
            return paths

    p = chart_box_good_bad(df, feature_cols, out_dir, target=target, top_n=top_n, dpi=dpi)
    if p is not None:
        paths.append(p)
        if verbose:
            print(f'  [boxplot] 好/坏对比图: {p.name}')

    for dim in (category_dims or []):
        p = chart_box_by_segment(
            df, feature_cols, dim, out_dir,
            target=target, top_n=top_n, dpi=dpi,
        )
        if p is not None:
            paths.append(p)
            if verbose:
                print(f'  [boxplot] 分群对比图 ({dim}): {p.name}')

    return paths


__all__ = [
    'chart_box_good_bad',
    'chart_box_by_segment',
    'generate_boxplots_for_univariate',
]
