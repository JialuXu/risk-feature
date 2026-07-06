# -*- coding: utf-8 -*-
"""prepare 子命令：调 risk_data_prep.prepare_df → 写 prepared.csv + features.json（前置态）。"""
from __future__ import annotations

import json
import os
import sys
import time

from risk_core import contracts as cli_io
from risk_pipeline.pipeline_state import format_status_stamp, load_state

from ._common import (
    _err,
    _features_json_path,
    _is_quiet,
    _preflight_column_mapping,
    _prepared_csv_path,
    _print_stamp,
    _state_dir,
    _validate_split_confirmation,
)


def cmd_prepare(args) -> int:
    from risk_data_prep.scripts.prepare_df import prepare_df

    started = time.time()
    project = args.project
    wide = args.wide

    if not os.path.isfile(wide):
        _err(f'[prepare] 宽表文件不存在: {wide}')
    if args.bad_customer is not None and not os.path.isfile(args.bad_customer):
        _err(f'[prepare] 坏客户清单不存在: {args.bad_customer}')
    merge_table = getattr(args, 'merge_table', None)
    if merge_table is not None and not os.path.isfile(merge_table):
        _err(f'[prepare] --merge-table 不存在: {merge_table}')
    merge_cols = None
    if getattr(args, 'merge_cols', None):
        merge_cols = [c.strip() for c in args.merge_cols.split(',') if c.strip()]

    filter_dict = None
    if args.filter_file:
        if not os.path.isfile(args.filter_file):
            _err(f'[prepare] --filter-file 不存在: {args.filter_file}')
        with open(args.filter_file, 'r', encoding='utf-8') as f:
            filter_dict = json.load(f)
        if not _is_quiet(args):
            summary = ', '.join(f'{c}: {sorted(r.keys())}' for c, r in filter_dict.items())
            print(f'[prepare] filter 规则 {len(filter_dict)} 列 → {summary}')

    exclude_features = None
    if args.exclude_features_file:
        if not os.path.isfile(args.exclude_features_file):
            _err(f'[prepare] --exclude-features-file 不存在: {args.exclude_features_file}')
        with open(args.exclude_features_file, 'r', encoding='utf-8') as f:
            exclude_features = json.load(f)

    state = load_state(project, state_dir=_state_dir(args))

    # 阻断节点 1：首次新数据集必须显式确认（C15：支持拆分版 + 一键版）
    is_known = state.is_known_dataset(wide)
    confirmed_legacy = bool(getattr(args, 'confirmed_new_dataset', False))
    confirmed_split = _validate_split_confirmation(args)  # 全填 + 一致 → True；任一不一致 → 抛错；全空 → None
    confirmed = confirmed_legacy or (confirmed_split is True)

    if not is_known and not confirmed:
        _err(
            f'⚠️ [阻断节点 1] 检测到首次使用的数据集: {wide}\n'
            f'  原因：id_col/target_col/坏客户定义跑错会污染后续 8 张 CSV，无法从结果层面发现。\n'
            f'  请确认：\n'
            f'    1. 主键字段名 = {args.id_col!r}\n'
            f'    2. 目标列名 = {args.target_col!r}（1=坏客户）\n'
            f'    3. filter 排除规则是否正确（当前: {filter_dict}）\n'
            f'  确认方式（任选其一）：\n'
            f'    a) 一键确认：加 `--confirmed-new-dataset`\n'
            f'    b) 拆分确认（推荐，留审计痕迹）：\n'
            f'       --confirmed-id-col {args.id_col!r} --confirmed-target-col {args.target_col!r} '
            f'--confirmed-target-positive 1'
        )

    try:
        df, feature_cols = prepare_df(
            wide_path=wide,
            bad_customer_path=args.bad_customer,
            id_col=args.id_col,
            target_col=args.target_col,
            bad_id_col=args.bad_id_col,
            merge_table_path=merge_table,
            merge_id_col=getattr(args, 'merge_id_col', None),
            merge_cols=merge_cols,
            filter=filter_dict,
            exclude_features=exclude_features,
        )
    except ValueError as e:
        # prepare_df 的守门错误（缺主键列 / 目标列非 0/1 / 坏客户 0 匹配等）：
        # 中文消息直接转 _err，避免裸 traceback 暴露给无技术背景的用户
        _err(f'[prepare] {e}')
    except UnicodeDecodeError as e:
        _err(f'[prepare] CSV 文件编码无法识别（请确认为 UTF-8 / GBK 等常见编码）: {e}')

    # 配置预检（Phase A）：把 YAML 期望列与实际 df.columns 对比
    from risk_core.column_mapper import ColumnMapper
    column_audit = _preflight_column_mapping(df, ColumnMapper())
    seg_hit = column_audit['segment_dims']['hit_rate']
    cred_hit = column_audit['credit_category_dims']['hit_rate']
    skip_preflight = bool(getattr(args, 'skip_preflight', False))

    # 硬错：两组分群维度均 0% 命中 → 字段彻底对不上 YAML，分群分析会全空跑
    if seg_hit == 0 and cred_hit == 0 and not skip_preflight:
        _err(
            '⚠️ [配置预检] column_mapping.yaml 中所有分群维度字段在宽表中均不存在\n'
            f'  期望 segment_dims:        {column_audit["segment_dims"]["expected"]}\n'
            f'  期望 credit_category_dims: {column_audit["credit_category_dims"]["expected"]}\n'
            f'  宽表实际可用列（前 20 个）: {list(df.columns)[:20]}\n'
            '  原因：分群字段全军覆没意味着后续分群分析会全部空跑，结果只剩全样本 IV。\n'
            '  处理方式：\n'
            '    a) 分群维度列名与默认配置不同（最常见）：加 --skip-preflight 放行本步，\n'
            '       随后 analyze/run 传 --category-dims <实际列名>（不改任何配置文件）\n'
            '    b) 有意只跑全样本（不分群）：加 --skip-preflight\n'
            '    c) 编辑 risk_core/config/column_mapping.yaml 仅限开发仓库长期接入新数据源；\n'
            '       沙盒/skill 安装模式禁止改随包分发的默认配置（会污染其它数据集的运行）'
        )

    # 软警告：>0 但 <30% 命中 → 不阻断，stderr 提示哪几个维度可用
    if 0 < seg_hit < 0.3:
        print(
            f'⚠️ [配置预检] segment_dims 命中率 {seg_hit:.0%}'
            f'（实际命中 {column_audit["segment_dims"]["actual"]} / '
            f'期望 {column_audit["segment_dims"]["expected"]}）；'
            '其余维度的分群分析将自动跳过。如需补全，analyze/run 时传 --category-dims <实际列名>；'
            '编辑 risk_core/config/column_mapping.yaml 仅限开发仓库长期适配。',
            file=sys.stderr,
        )

    prepared_path = _prepared_csv_path(project)
    features_path = _features_json_path(project)
    cli_io.write_prepared(df, prepared_path)  # §5.1 唯一写点（含 mkdir）

    n_bad = int(df[args.target_col].sum()) if args.target_col in df.columns else 0
    confirmation = {
        'mode': 'split' if confirmed_split is True else ('legacy' if confirmed_legacy else 'known_dataset'),
        'id_col': getattr(args, 'confirmed_id_col', None),
        'target_col': getattr(args, 'confirmed_target_col', None),
        'target_positive': getattr(args, 'confirmed_target_positive', None),
    }
    info = {
        'feature_cols': feature_cols,
        'id_col': args.id_col,
        'target_col': args.target_col,
        'wide_source_path': wide,
        'wide_source_fingerprint': cli_io.dataset_fingerprint(wide),
        'bad_customer_path': args.bad_customer,
        'filter_applied': filter_dict,
        'exclude_features': list(exclude_features) if exclude_features else None,
        'n_rows': len(df),
        'n_bad': n_bad,
        'n_features': len(feature_cols),
        'created_at': cli_io.now_iso(),
        'confirmation': confirmation,
        'column_mapping_audit': column_audit,
        'preflight_skipped': skip_preflight,
    }
    cli_io.write_features_json(features_path, info)

    state.record_dataset(wide)
    state.append_history({
        'cmd': 'prepare',
        'args_summary': {
            'wide': wide,
            'bad_customer': args.bad_customer,
            'id_col': args.id_col,
            'target_col': args.target_col,
            'filter': filter_dict,
            'rows': len(df),
            'bad': n_bad,
            'features': len(feature_cols),
        },
        'outputs': [prepared_path, features_path],
        'duration_sec': round(time.time() - started, 2),
        'level_after': state.current_level,
    })
    state.save()

    _print_stamp(
        format_status_stamp(
            'prepare', project, state.current_level,
            inputs=[f'wide={wide}'] + ([f'bad={args.bad_customer}'] if args.bad_customer else []),
            outputs=[prepared_path, features_path],
            extras=[f'rows={len(df)}, features={len(feature_cols)}, bad={n_bad}'],
        ),
        args,
    )
    return 0
