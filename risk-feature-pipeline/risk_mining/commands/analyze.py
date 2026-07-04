# -*- coding: utf-8 -*-
"""analyze 子命令：调 run_generic_pipeline → 写 _intermediate/（过渡态）；含 rules 步骤。"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pandas as pd

from risk_core import contracts as cli_io
from risk_pipeline.pipeline_state import format_status_stamp, load_state

from ._common import (
    _err,
    _features_json_path,
    _intermediate_dir,
    _is_quiet,
    _is_verbose,
    _prepared_csv_path,
    _print_stamp,
    _state_dir,
)


_VALID_ANALYZE_STEPS = ('univariate', 'iv', 'lr', 'rules')


def cmd_analyze(args) -> int:
    from risk_pipeline.pipeline import run_generic_pipeline

    started = time.time()
    project = args.project
    prepared = args.prepared or _prepared_csv_path(project)
    features_path = args.features_file or _features_json_path(project)

    if not os.path.isfile(prepared):
        _err(f'[analyze] prepared.csv 不存在: {prepared}\n'
             f'建议: 先跑 `python -m risk_pipeline prepare --wide ... --project {project}`')
    if not os.path.isfile(features_path):
        _err(f'[analyze] features.json 不存在: {features_path}\n'
             f'建议: 先跑 prepare 子命令生成 features.json')

    info = cli_io.read_features_json(features_path)
    target_col = args.target_col or info.get('target_col', 'is_bad')
    feature_cols = info.get('feature_cols', [])
    if not feature_cols:
        _err('[analyze] features.json 中 feature_cols 为空，无法分析')

    requested = [s.strip() for s in (args.steps or '').split(',') if s.strip()]
    if not requested:
        requested = list(_VALID_ANALYZE_STEPS)
    if 'export' in requested:
        _err('[analyze] --steps 禁止包含 export；export 由独立 `export` 子命令完成')
    invalid = [s for s in requested if s not in _VALID_ANALYZE_STEPS]
    if invalid:
        _err(f'[analyze] 无效 steps: {invalid}；可选: {list(_VALID_ANALYZE_STEPS)}')
    steps = [s for s in _VALID_ANALYZE_STEPS if s in requested]

    category_dims = (
        [d.strip() for d in args.category_dims.split(',') if d.strip()]
        if args.category_dims
        else None
    )
    if args.qual_dims is None:
        qual_dims = None
    elif args.qual_dims == '':
        qual_dims = []
    else:
        qual_dims = [d.strip() for d in args.qual_dims.split(',') if d.strip()]

    # Phase B：--category-dims 列存在性硬校验（避免下游 KeyError）
    if category_dims is not None:
        prepared_cols = pd.read_csv(prepared, nrows=0, encoding='utf-8-sig').columns.tolist()
        invalid = [d for d in category_dims if d not in prepared_cols]
        if invalid:
            hint = ''
            if os.path.isfile(features_path):
                try:
                    audit = cli_io.read_features_json(features_path).get(
                        'column_mapping_audit', {}
                    ).get('segment_dims', {})
                    if audit.get('actual'):
                        hint = f'\n  prepare 时检测到的可用分群维度: {audit["actual"]}'
                except Exception:  # noqa: BLE001
                    pass
            _err(
                f'[analyze] --category-dims 中以下列在 prepared.csv 不存在: {invalid}\n'
                f'  prepared.csv 前 30 列: {prepared_cols[:30]}{hint}\n'
                '  建议: 编辑 config/column_mapping.yaml 后重跑 prepare，或直接传实际列名'
            )
    else:
        # 自动检测路径：若 prepare 阶段命中率为 0，提示用户分析会退化到全样本
        if os.path.isfile(features_path):
            try:
                audit_seg = cli_io.read_features_json(features_path).get(
                    'column_mapping_audit', {}
                ).get('segment_dims', {})
                if audit_seg and audit_seg.get('hit_rate', 1.0) == 0:
                    print(
                        '⚠️ [analyze] features.json 显示 segment_dims 自动检测为空；'
                        '本次分析将仅在全样本范围进行，不会有分群对比。'
                        '如需分群，请编辑 config/column_mapping.yaml 后重跑 prepare，'
                        '或直接给 analyze 传 --category-dims <实际列名>。',
                        file=sys.stderr,
                    )
            except Exception:  # noqa: BLE001
                pass

    state = load_state(project, state_dir=_state_dir(args))

    df = cli_io.read_prepared(prepared, id_col=info.get('id_col'))  # §5.1 主键 str 契约
    verbose = _is_verbose(args) and not _is_quiet(args)

    # rules 是 CLI 层独立步骤；run_generic_pipeline 不识别它，剥离后再传
    pipeline_steps = [s for s in steps if s != 'rules']
    inter_dir = _intermediate_dir(project)

    if pipeline_steps:
        results = run_generic_pipeline(
            df=df,
            feature_cols=feature_cols,
            target_col=target_col,
            project_name=project,
            category_dims=category_dims,
            qual_dims=qual_dims,
            steps=pipeline_steps,
            verbose=verbose,
        )
        cli_io.dump_intermediate(
            results, inter_dir,
            project_name=project,
            target_col=target_col,
            category_dims=results.get('category_dims', category_dims or []),
            qual_dims=results.get('qual_dims', qual_dims or []),
            feature_cols=feature_cols,
            raw_features=info.get('raw_features'),
            derived_features=info.get('derived_features'),
        )
        effective_category_dims = results.get('category_dims', category_dims or [])
    else:
        # rules-only：前置 manifest 必须存在，否则 export 阶段没东西可读
        manifest_path = os.path.join(inter_dir, 'manifest.json')
        if not os.path.isfile(manifest_path):
            _err(
                f'[analyze] --steps rules 需要前置的 _intermediate/manifest.json：{manifest_path}\n'
                f'建议: 先跑 `python -m risk_pipeline analyze --project {project} '
                f'--steps univariate,iv,lr` 再追加 rules'
            )
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        manifest_dims = manifest.get('category_dims', [])
        # rules-only 模式下 --category-dims 必须是 manifest 维度的子集；
        # 凭空引入新维度会让 rules 与前置 corr/iv/lr 结果错位（下游 export 读旧 manifest）
        if category_dims is not None:
            invalid = [d for d in category_dims if d not in manifest_dims]
            if invalid:
                _err(
                    f'[analyze] --steps rules 单跑时 --category-dims 必须是前置 analyze '
                    f'已用维度的子集。\n'
                    f'  前置维度（manifest）: {manifest_dims}\n'
                    f'  CLI 传入但不在前置维度中: {invalid}\n'
                    f'  原因：corr / iv_group / lr 已按 manifest 维度落盘到 _intermediate/；'
                    f'新维度需先重跑 univariate,iv,lr 才能与 rules 对齐。'
                )
            effective_category_dims = category_dims
        else:
            effective_category_dims = manifest_dims
        results = {}  # 只是给后面 status stamp 用

    rules_summary = ''
    if 'rules' in steps:
        rules_summary = _run_rule_mining_step(
            df=df,
            feature_cols=feature_cols,
            target_col=target_col,
            category_dims=effective_category_dims,
            inter_dir=inter_dir,
            verbose=verbose,
        )

    state.append_history({
        'cmd': 'analyze',
        'args_summary': {
            'steps': steps,
            'category_dims': effective_category_dims,
            'qual_dims': results.get('qual_dims', qual_dims or []),
            'features': len(feature_cols),
            'target_col': target_col,
        },
        'outputs': [inter_dir + '/'],
        'duration_sec': round(time.time() - started, 2),
    }, new_level='过渡态')
    state.save()

    extras = [f'steps={",".join(steps)}']
    if rules_summary:
        extras.append(rules_summary)
    # "下一步"提示按真实 level 给：仅在 过渡态 时建议 export
    if state.current_level == '过渡态':
        extras.append(
            f'下一步: python -m risk_pipeline export --project {project}（→ Level 1）'
        )
    else:
        extras.append(
            f'当前 level={state.current_level}（本次为补充分析；如需刷新结果重跑 export）'
        )

    _print_stamp(
        format_status_stamp(
            'analyze', project, state.current_level,
            inputs=[prepared, features_path],
            outputs=[f'{inter_dir}/'],
            extras=extras,
        ),
        args,
    )
    return 0


def _run_rule_mining_step(
    df: 'pd.DataFrame',
    feature_cols: list,
    target_col: str,
    category_dims: list,
    inter_dir: str,
    verbose: bool,
) -> str:
    """analyze 的 rules 步骤：拟合树 + 落 pkl 到 _intermediate/，规则 DF pickle 一并落盘。

    返回一行人类可读的 summary 字符串（用于 status stamp）。
    """
    from risk_rule_mining.scripts.rule_mining_pipeline import (
        mine_rules_full, rules_by_group,
    )
    inter = Path(inter_dir)
    inter.mkdir(parents=True, exist_ok=True)

    parts = []

    # 1) 全样本规则（pkl → _intermediate/rule_tree_全样本.pkl）
    rules_full = mine_rules_full(
        df, feature_cols, target=target_col, verbose=verbose,
        persist_tree_path=inter / 'rule_tree_全样本.pkl',
    )
    if not rules_full.empty:
        rules_full.insert(0, 'segment_dim', '全样本')
        rules_full.insert(1, 'segment_value', '全样本')
        parts.append(rules_full)

    # 2) 每个分群维度的规则（pkl → _intermediate/rule_tree_<dim>__<group>.pkl）
    for dim in (category_dims or []):
        if dim not in df.columns:
            print(f'[跳过 rules] 分群维度列不存在: {dim}', file=sys.stderr)
            continue
        try:
            rules_dim = rules_by_group(
                df, segment_col=dim, feature_cols=feature_cols,
                target=target_col, verbose=verbose,
                persist_tree_dir=inter,
            )
        except Exception as e:
            print(f'[跳过 rules] {dim} 规则挖掘失败: {e}', file=sys.stderr)
            continue
        if not rules_dim.empty:
            parts.append(rules_dim)

    rules_pkl = inter / 'rules.pkl'
    if not parts:
        # 没挖出任何规则也写一个空 pkl，避免 export 阶段误以为是"未跑过 rules"
        import pandas as _pd
        _pd.DataFrame().to_pickle(rules_pkl)
        return 'rules=0（未挖到满足闸门的规则）'

    import pandas as _pd
    rules_all = _pd.concat(parts, ignore_index=True)
    rules_all.to_pickle(rules_pkl)
    n_pkl = len(list(inter.glob('rule_tree_*.pkl')))
    return f'rules={len(rules_all)}（树 pkl={n_pkl}；规则 pkl={rules_pkl.name}）'
