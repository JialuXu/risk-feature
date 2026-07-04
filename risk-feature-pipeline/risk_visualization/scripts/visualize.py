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

from risk_core.results_loader import load_results, Results

# matplotlib / seaborn 是可视化的硬依赖；缺失时给出可执行的安装提示，
# 避免用户面对一大堆 traceback 不知道该装什么。
try:
    from . import style  # 触发字体配置（必须先于 chart_* import）
    from .chart_iv import chart_iv_full, chart_iv_heatmap
    from .chart_corr import chart_corr_heatmap
    from .chart_lr import chart_lr_heatmap, chart_lr_auc
    from .chart_segment import chart_segment_profile
    from .chart_rules import chart_rules_scatter
    from .chart_combinations import chart_combo_lift
    from .chart_threshold import chart_threshold_binning, chart_threshold_summary
except ModuleNotFoundError as _viz_import_err:
    if _viz_import_err.name in ('matplotlib', 'seaborn', 'matplotlib.pyplot'):
        raise ModuleNotFoundError(
            f"可视化依赖缺失：{_viz_import_err.name} 未安装。\n"
            f"  解决：pip install matplotlib seaborn\n"
            f"  或安装项目时启用 [viz] extras：pip install -e .[viz]\n"
            f"  PEP 668 锁定环境（部分 macOS / CI）请先 `python -m venv .venv && source .venv/bin/activate`，"
            f"或加 `--break-system-packages`。"
        ) from None
    raise


ALL_KINDS = (
    'iv', 'iv_heatmap',
    'corr_heatmap',
    'lr_heatmap', 'auc',
    'segment',
    'rules', 'combos',
    'thresholds',
)
# 已下线（对最终业务报告无增量价值）：
#   corr / lr —— 每分群一张的散图，与 corr_heatmap / lr_heatmap 信息重复且随分群数量爆炸
#   tree      —— 决策树图（>3 层不可读、按分群数量爆炸；规则表 + rules 散点已覆盖）
#   combo_network —— 特征共现网络，自述用途为“反向辅助特征工程”，属建模阶段工具


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


def _load_csv_by_suffix(results: Results, suffix: str) -> Optional[pd.DataFrame]:
    """通用：按 `{project}_{suffix}.csv` 在 results_dir / output_dir 找并读取。"""
    fname = f'{results.project_name}_{suffix}.csv'
    for base in (results.results_dir, results.output_dir):
        if not base:
            continue
        path = os.path.join(base, fname)
        if os.path.isfile(path):
            for enc in ('utf-8-sig', 'utf-8', 'gbk'):
                try:
                    return pd.read_csv(path, encoding=enc)
                except UnicodeDecodeError:
                    continue
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
        project_name: 跑链路时传入的 project_name
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
        from risk_pipeline.paths import output_dir as _output_dir_for
        chart_dir = Path(_output_dir_for(project_name)) / 'charts'
    from risk_pipeline.paths import ensure_writable_dir
    ensure_writable_dir(chart_dir)

    rules_df = _load_rules_csv(r)

    out: Dict[str, List[str]] = {}

    def _record(key: str, paths: List[Path]):
        if paths:
            out[key] = [str(p) for p in paths]

    if 'iv' in kinds:
        _record('iv', chart_iv_full(r.iv_full, chart_dir, top_n=top_n, dpi=dpi))
    if 'iv_heatmap' in kinds:
        # 每个分群维度一张（行=该维度各分群、列=特征），与 corr/lr 热力图同口径
        _record('iv_heatmap', chart_iv_heatmap(
            r.iv_group_all, r.iv_full,
            chart_dir, top_n=top_n, dpi=dpi,
        ))
    if 'corr_heatmap' in kinds:
        _record('corr_heatmap', chart_corr_heatmap(
            r.corr_long, chart_dir, top_n=top_n, dim=dim, dpi=dpi,
        ))
    if 'lr_heatmap' in kinds:
        _record('lr_heatmap', chart_lr_heatmap(
            r.lr_coef_long, chart_dir, top_n=top_n, dim=dim, dpi=dpi,
        ))
    if 'auc' in kinds:
        _record('auc', chart_lr_auc(r.lr_auc_long, chart_dir, dim=dim, dpi=dpi))
    if 'segment' in kinds:
        _record('segment', chart_segment_profile(r.segment_profiles, chart_dir, dpi=dpi))
    if 'rules' in kinds:
        _record('rules', chart_rules_scatter(rules_df, chart_dir, dpi=dpi))
    if 'combos' in kinds:
        _record('combos', chart_combo_lift(rules_df, chart_dir, top_n=top_n, dpi=dpi))
    if 'thresholds' in kinds:
        thr_summary = _load_csv_by_suffix(r, '候选阈值表')
        thr_detail = _load_csv_by_suffix(r, '候选阈值_分箱明细')
        if thr_summary is not None and thr_detail is not None:
            bin_paths = chart_threshold_binning(thr_detail, thr_summary, chart_dir, dpi=dpi)
            sum_paths = chart_threshold_summary(thr_summary, chart_dir, dpi=dpi)
            all_paths = list(bin_paths) + list(sum_paths)
            if all_paths:
                # 合并为单一 key 'thresholds'，stamp 用此 key 跟 kinds 集合对齐
                out['thresholds'] = [str(p) for p in all_paths]

    return out


__all__ = ['generate_charts', 'ALL_KINDS']
