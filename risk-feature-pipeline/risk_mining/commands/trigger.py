# -*- coding: utf-8 -*-
"""trigger 子命令：客户级触碰提取 → 三张表（→ Level 2；阻断节点 2）。"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from risk_core import contracts as cli_io
from risk_mining.pipeline_state import PipelineLevelError, format_status_stamp, load_state

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


def cmd_trigger(args) -> int:
    from risk_trigger_extraction.scripts.trigger_extraction import extract_triggers

    started = time.time()
    project = args.project
    prepared = args.prepared or _prepared_csv_path(project)
    if not os.path.isfile(prepared):
        _err(f'[trigger] prepared.csv 不存在: {prepared}\n'
             f'建议: 先跑 `python -m risk_pipeline prepare --project {project}`')

    state = load_state(project, state_dir=_state_dir(args))
    try:
        state.require_level('Level 1')
    except PipelineLevelError as e:
        _err(f'[trigger] {e}\n建议: 先跑 export 子命令推进到 Level 1')

    # 阻断节点 2：features 配置必须显式确认（默认/自定义都拦）
    if not getattr(args, 'confirmed', False):
        cfg_desc = (
            '默认 RISK_FEATURES 通用配置'
            if args.use_default_features
            else f'项目专属特征列表（{args.features_file}）'
        )
        _err(
            '⚠️ [阻断节点 2] trigger 即将基于 features 配置生成预警名单\n'
            f'  原因：触碰阈值依赖的特征集错误会直接导致预警名单错误，是可运营决策的上游，\n'
            f'        一旦推送给业务部门不可撤回。\n'
            f'  当前 features 来源：{cfg_desc}\n'
            f'  请确认：\n'
            f'    1. features 配置正确（report_name / source_col / risk_direction / iv 全部核对）\n'
            f'    2. 项目专属特征是否已对齐 prepared.csv 的实际列名\n'
            f'  非 GSFC 数据集请走 --features-file，模板见：\n'
            f'    risk_trigger_extraction/examples/features_template_generic.json\n'
            f'  若确认无误，重新执行并加 `--confirmed`。'
        )

    features = None
    if args.features_file:
        if not os.path.isfile(args.features_file):
            _err(f'[trigger] --features-file 不存在: {args.features_file}')
        with open(args.features_file, 'r', encoding='utf-8') as f:
            features = json.load(f)

    info = {}
    info_path = _features_json_path(project)
    if os.path.isfile(info_path):
        info = cli_io.read_features_json(info_path)

    id_col = args.id_col or info.get('id_col', '客户编号')
    target_col = args.target_col or info.get('target_col', 'is_bad')

    # §5.1 主键 str 契约（本重构点名必修的真 bug）：先解析 id_col 再读，
    # 否则带前导零的客户编号被推断成 int → 下游与客户宽表 merge 0 命中 → 全 0 预警名单
    df = cli_io.read_prepared(prepared, id_col=id_col)

    output_dir = os.path.join(_output_root(), 'output', project)  # trigger 写三件套
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    verbose = _is_verbose(args) and not _is_quiet(args)

    keep_metadata_cols = None
    if getattr(args, 'keep_metadata_cols', None):
        keep_metadata_cols = [c.strip() for c in args.keep_metadata_cols.split(',') if c.strip()]

    df_wide, df_long, df_threshold = extract_triggers(
        df=df,
        features=features,
        target_col=target_col,
        id_col=id_col,
        project_name=project,
        output_dir=output_dir,
        verbose=verbose,
        keep_metadata_cols=keep_metadata_cols,
    )

    used_default = bool(args.use_default_features)
    state.append_history({
        'cmd': 'trigger',
        'args_summary': {
            'used_default_features': used_default,
            'features_file': args.features_file,
            'id_col': id_col,
            'target_col': target_col,
            'rows': len(df_wide),
            'triggers': len(df_long),
        },
        'outputs': [
            os.path.join(output_dir, f'{project}_风险触碰明细_宽表.csv'),
            os.path.join(output_dir, f'{project}_风险触碰明细_长表.csv'),
            os.path.join(output_dir, f'{project}_触碰阈值说明.csv'),
        ],
        'duration_sec': round(time.time() - started, 2),
        'level_after': 'Level 2',
    }, new_level='Level 2')
    state.save()

    _print_stamp(
        format_status_stamp(
            'trigger', project, state.current_level,
            inputs=[prepared],
            outputs=[
                f'{output_dir}/{project}_风险触碰明细_宽表.csv',
                f'{output_dir}/{project}_风险触碰明细_长表.csv',
                f'{output_dir}/{project}_触碰阈值说明.csv',
            ],
            extras=[
                f'rows={len(df_wide)}, triggers={len(df_long)}',
                f'used_default_features={used_default}',
            ],
        ),
        args,
    )
    return 0
