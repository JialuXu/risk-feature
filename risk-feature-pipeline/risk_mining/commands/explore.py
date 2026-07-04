# -*- coding: utf-8 -*-
"""explore_thresholds 子命令：optbinning 单变量最优切点 + 业务级判定（Level 1 后；不改 level）。"""
from __future__ import annotations

import os
import sys
import time

import pandas as pd

from risk_core import contracts as cli_io
from risk_pipeline.pipeline_state import PipelineLevelError, format_status_stamp, load_state

from ._common import (
    _err,
    _features_json_path,
    _is_quiet,
    _is_verbose,
    _output_root,
    _prepared_csv_path,
    _print_stamp,
    _state_dir,
)


def cmd_explore_thresholds(args) -> int:
    """候选规则阈值探索：optbinning 最优切点 + 五道门槛业务有效性判定。

    只读 Level 1 已落盘的 LR/相关/IV 全量结果作为风险方向来源；不推进 level。
    """
    from risk_result_query.scripts.results_loader import load_results
    from risk_threshold_explore.scripts.threshold_explore import explore_thresholds
    from risk_threshold_explore.scripts.io_utils import (
        read_pair_list, write_threshold_outputs, append_audit_node,
    )

    started = time.time()
    project = args.project
    prepared = args.prepared or _prepared_csv_path(project)
    pairs_file = args.pairs_file

    if not os.path.isfile(prepared):
        _err(f'[explore_thresholds] prepared.csv 不存在: {prepared}\n'
             f'建议: 先跑 `python -m risk_pipeline prepare --project {project}`')
    if not os.path.isfile(pairs_file):
        _err(f'[explore_thresholds] --pairs-file 不存在: {pairs_file}')

    state = load_state(project, state_dir=_state_dir(args))
    try:
        state.require_level('Level 1')
    except PipelineLevelError as e:
        _err(f'[explore_thresholds] {e}\n建议: 先跑 export 子命令推进到 Level 1')

    try:
        pair_list = read_pair_list(pairs_file)
    except (FileNotFoundError, ValueError, UnicodeDecodeError) as e:
        _err(f'[explore_thresholds] 解析 --pairs-file 失败: {e}')

    if not pair_list:
        _err('[explore_thresholds] pair-list 为空，无可探索的组合')

    target_col = args.target_col
    if target_col is None:
        info_path = _features_json_path(project)
        if os.path.isfile(info_path):
            target_col = cli_io.read_features_json(info_path).get('target_col', 'is_bad')
        else:
            target_col = 'is_bad'

    df = pd.read_csv(prepared, encoding='utf-8-sig')

    try:
        results = load_results(project, project_root=_output_root())  # 读 export 写过的产物
    except FileNotFoundError:
        # Level 1 已确认但 load_results 仍找不到（自定义 subdir 等）；以 None 继续，
        # 风险方向将回落到 bin_jump
        results = None
        print('  [警告] load_results 未找到导出目录，将回落到 bin_jump 方向推断；'
              '风险方向来源标签会全部为 bin_jump。', file=sys.stderr)

    cfg_overrides = {
        'MIN_RISK_RATIO': args.min_risk_ratio,
        'MAX_P_VALUE': args.max_p,
        'MIN_BAD_HIGH_SIDE': args.min_bad_high,
        'ALERT_RATE_MIN': args.alert_rate_min,
        'ALERT_RATE_MAX': args.alert_rate_max,
        'MIN_IV': args.min_iv,
        'OPTBIN_MIN_BIN_SIZE': getattr(args, 'min_bin_size', None),
    }

    verbose = _is_verbose(args) and not _is_quiet(args)
    outcome = explore_thresholds(
        df=df, pair_list=pair_list, project_name=project,
        results=results, target_col=target_col,
        cfg=cfg_overrides, verbose=verbose,
    )

    # 输出目录：优先复用 load_results 找到的 results_dir，否则按 --results-subdir / project 落盘
    if results is not None and getattr(results, 'results_dir', None):
        results_dir = results.results_dir
    else:
        subdir = args.results_subdir or project
        results_dir = os.path.join(_output_root(), 'data', 'results', subdir)  # 候选阈值表写 output_root

    paths = write_threshold_outputs(
        outcome.summary_df, outcome.detail_df,
        project=project, results_dir=results_dir,
    )

    # audit 节点
    audit_path = os.path.join(results_dir, f'{project}_audit.json')
    n_valid = int(outcome.summary_df['规则有效'].sum()) if (
        outcome.summary_df is not None and not outcome.summary_df.empty
        and '规则有效' in outcome.summary_df.columns
    ) else 0

    candidates_payload = []
    if outcome.summary_df is not None and not outcome.summary_df.empty:
        keep_cols = [
            '分群维度', '分群名称', '特征', '风险方向', '方向来源', '候选阈值',
            '风险倍数', '卡方p值', '触警率', '全局IV', '规则有效', '不通过原因',
        ]
        avail = [c for c in keep_cols if c in outcome.summary_df.columns]
        candidates_payload = outcome.summary_df[avail].to_dict(orient='records')

    append_audit_node(audit_path, 'threshold_candidates', {
        'created_at': cli_io.now_iso(),
        'n_pairs_input': len(pair_list),
        'n_pairs_evaluated': len(outcome.summary_df) if outcome.summary_df is not None else 0,
        'n_pairs_skipped': len(outcome.skipped),
        'n_rules_valid': n_valid,
        'gates': outcome.gates,
        'skipped': outcome.skipped,
        'candidates': candidates_payload,
    })

    state.append_history({
        'cmd': 'explore_thresholds',
        'args_summary': {
            'pairs_file': pairs_file,
            'n_pairs': len(pair_list),
            'gates': outcome.gates,
            'target_col': target_col,
        },
        'outputs': [paths['summary_path'], paths['detail_path'], audit_path],
        'duration_sec': round(time.time() - started, 2),
        'level_after': state.current_level,
        'note': '候选阈值只读后置；不推进 level',
    })
    state.save()

    extras = [
        f'pairs={len(pair_list)} → evaluated={len(outcome.summary_df) if outcome.summary_df is not None else 0}, '
        f'valid={n_valid}, skipped={len(outcome.skipped)}',
    ]
    if outcome.skipped:
        first_few = ', '.join(
            f'{s["分群名称"]}.{s["特征"]}({s["原因"]})'
            for s in outcome.skipped[:3]
        )
        extras.append(f'skipped 示例: {first_few}' + (' ...' if len(outcome.skipped) > 3 else ''))

    _print_stamp(
        format_status_stamp(
            'explore_thresholds', project, state.current_level,
            inputs=[prepared, pairs_file],
            outputs=[paths['summary_path'], paths['detail_path'], audit_path],
            extras=extras,
        ),
        args,
    )
    return 0
