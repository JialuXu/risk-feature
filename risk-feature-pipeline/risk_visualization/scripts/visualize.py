# -*- coding: utf-8 -*-
"""risk_visualization 顶层入口：generate_charts(project_name, kinds=...) → {kind: [paths]}

读 Level 1 已落盘的 8 张 CSV + 可选的 _风险规则表.csv + 可选的 _intermediate/rule_tree_*.pkl，
输出 PNG 到 output/<project>/charts/。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

_SKILL_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _SKILL_ROOT not in sys.path:
    sys.path.insert(0, _SKILL_ROOT)

from risk_result_query.scripts.results_loader import load_results, Results

from . import style  # 触发字体配置（必须先于 chart_* import）
from .chart_iv import chart_iv_full, chart_iv_heatmap
from .chart_corr import chart_corr
from .chart_lr import chart_lr_coef, chart_lr_auc
from .chart_segment import chart_segment_profile
from .chart_tree import chart_tree
from .chart_rules import chart_rules_scatter
from .chart_combinations import chart_combo_lift, chart_combo_network


ALL_KINDS = (
    'iv', 'iv_heatmap', 'corr', 'lr', 'auc', 'segment',
    'tree', 'rules', 'combos', 'combo_network',
)


def _find_project_root(start: Optional[str] = None) -> str:
    cur = Path(start or os.getcwd()).resolve()
    for p in [cur, *cur.parents]:
        if (p / 'data').exists():
            return str(p)
    return str(cur)


def _load_rules_csv(results: Results) -> Optional[pd.DataFrame]:
    """从 results_dir 或 output_dir 找 _风险规则表.csv。"""
    for base in (results.results_dir, results.output_dir):
        if not base:
            continue
        path = os.path.join(base, f'{results.project_name}_风险规则表.csv')
        if os.path.isfile(path):
            for enc in ('utf-8-sig', 'utf-8', 'gbk'):
                try:
                    return pd.read_csv(path, encoding=enc)
                except UnicodeDecodeError:
                    continue
    return None


def _intermediate_dir_for(results: Results) -> Optional[Path]:
    """从 results_dir 反推 _intermediate/。"""
    project = results.project_name
    root = _find_project_root(results.results_dir)
    candidates = [
        Path(root) / 'data' / 'processed' / project / '_intermediate',
        # 老路径兜底
        Path(results.results_dir).parent / project / '_intermediate' if results.results_dir else None,
    ]
    for c in candidates:
        if c is not None and c.is_dir():
            return c
    return None


def generate_charts(
    project_name: str,
    kinds: Optional[List[str]] = None,
    top_n: int = 15,
    out_dir: Optional[str] = None,
    dim: Optional[str] = None,
    dpi: int = 300,
    project_root: Optional[str] = None,
) -> Dict[str, List[str]]:
    """生成 PNG 图表集合。

    Args:
        project_name: 跑管线时传入的 project_name
        kinds:        要画的图（见 ALL_KINDS），None = 全部
        top_n:        条形图 top-N
        out_dir:      输出目录，默认 <project_root>/output/<project>/charts/
                       —— 注意：load_results 找到的 output_dir（如 output/征信/<project>）
                       优先于此默认值
        dim:          限定单一分群维度
        dpi:          PNG 分辨率
        project_root: 项目根目录（含 data/），默认从 CWD 向上找

    Returns:
        {kind: [str(path), ...]}；未生成的 kind 缺省（不在 dict 里）

    Raises:
        FileNotFoundError: 项目结果目录整体不存在（由 load_results 抛出）
    """
    if kinds is None:
        kinds = list(ALL_KINDS)
    invalid = [k for k in kinds if k not in ALL_KINDS]
    if invalid:
        raise ValueError(f'不支持的 kinds: {invalid}；可选: {list(ALL_KINDS)}')

    r = load_results(project_name, project_root=project_root)

    if out_dir is not None:
        chart_dir = Path(out_dir)
    elif r.output_dir:
        chart_dir = Path(r.output_dir) / 'charts'
    else:
        chart_dir = Path(_find_project_root()) / 'output' / project_name / 'charts'
    chart_dir.mkdir(parents=True, exist_ok=True)

    rules_df = _load_rules_csv(r)
    inter_dir = _intermediate_dir_for(r)

    out: Dict[str, List[str]] = {}

    def _record(key: str, paths: List[Path]):
        if paths:
            out[key] = [str(p) for p in paths]

    if 'iv' in kinds:
        _record('iv', chart_iv_full(r.iv_full, chart_dir, top_n=top_n, dpi=dpi))
    if 'iv_heatmap' in kinds:
        _record('iv_heatmap', chart_iv_heatmap(
            r.iv_pivot, r.reliability_pivot, r.iv_full,
            chart_dir, top_n=top_n, dpi=dpi,
        ))
    if 'corr' in kinds:
        _record('corr', chart_corr(r.corr_long, chart_dir, top_n=top_n, dim=dim, dpi=dpi))
    if 'lr' in kinds:
        _record('lr', chart_lr_coef(r.lr_coef_long, chart_dir, top_n=top_n, dim=dim, dpi=dpi))
    if 'auc' in kinds:
        _record('auc', chart_lr_auc(r.lr_auc_long, chart_dir, dim=dim, dpi=dpi))
    if 'segment' in kinds:
        _record('segment', chart_segment_profile(r.segment_profiles, chart_dir, dpi=dpi))
    if 'tree' in kinds:
        _record('tree', chart_tree(rules_df, inter_dir, chart_dir, dpi=dpi))
    if 'rules' in kinds:
        _record('rules', chart_rules_scatter(rules_df, chart_dir, dpi=dpi))
    if 'combos' in kinds:
        _record('combos', chart_combo_lift(rules_df, chart_dir, top_n=top_n, dpi=dpi))
    if 'combo_network' in kinds:
        _record('combo_network', chart_combo_network(rules_df, chart_dir, dpi=dpi))

    return out


__all__ = ['generate_charts', 'ALL_KINDS']
