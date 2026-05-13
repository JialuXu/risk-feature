# -*- coding: utf-8 -*-
"""7 子命令实现：薄壳 wrap 现有 Python API + state.json 状态管理。

- prepare: 调 risk_data_prep.scripts.prepare_df.prepare_df → 写 prepared.csv + features.json
- analyze: 调 risk_pipeline.pipeline.run_generic_pipeline → 写 _intermediate/
- export:  读 _intermediate/ → 调 risk_export_report.scripts.report_analysis.export_results
- query:   调 risk_result_query.scripts.results_loader.load_results + top_features
- trigger: 调 risk_trigger_extraction.scripts.trigger_extraction.extract_triggers
- report:  调 risk_docx_report.scripts.build_docx_report.build_docx_report
- run:     便捷组合：generic 走 prepare→analyze→export；credit/gsfc 直接转发现有管线
"""
from __future__ import annotations

import argparse as _argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

import pandas as pd

from . import cli_io
from .pipeline_state import (
    PipelineLevelError,
    PipelineState,
    format_status_stamp,
    load_state,
)


# ===== 路径 helpers =====

def _project_processed_dir(project: str) -> str:
    return os.path.join('data', 'processed', project)


def _intermediate_dir(project: str) -> str:
    return os.path.join(_project_processed_dir(project), '_intermediate')


def _prepared_csv_path(project: str) -> str:
    return os.path.join(_project_processed_dir(project), 'prepared.csv')


def _features_json_path(project: str) -> str:
    return os.path.join(_project_processed_dir(project), 'features.json')


def _project_root() -> str:
    from .paths import get_project_root
    return get_project_root()


def _err(msg: str, exit_code: int = 1):
    print(msg, file=sys.stderr)
    sys.exit(exit_code)


def _validate_split_confirmation(args) -> Optional[bool]:
    """C15: 校验拆分版确认 flag。

    Returns:
        True  — 三项全填且都与 args.id_col / args.target_col 一致 → 视为确认通过
        None  — 三项全空 → 未启用拆分版（调用方应回退到 --confirmed-new-dataset）
    Raises:
        SystemExit — 部分填或值不匹配
    """
    cid = getattr(args, 'confirmed_id_col', None)
    ctc = getattr(args, 'confirmed_target_col', None)
    ctp = getattr(args, 'confirmed_target_positive', None)
    provided = [v for v in (cid, ctc, ctp) if v is not None]
    if not provided:
        return None
    if len(provided) < 3:
        _err(
            '[阻断节点 1 / 拆分版] --confirmed-id-col / --confirmed-target-col / '
            '--confirmed-target-positive 必须三项一起传，部分填会让确认动作残缺。\n'
            '  当前已填: '
            f'id_col={cid!r}, target_col={ctc!r}, target_positive={ctp!r}'
        )
    mismatches = []
    if cid != args.id_col:
        mismatches.append(f"--confirmed-id-col={cid!r} 与 --id-col={args.id_col!r} 不一致")
    if ctc != args.target_col:
        mismatches.append(f"--confirmed-target-col={ctc!r} 与 --target-col={args.target_col!r} 不一致")
    if mismatches:
        _err(
            '[阻断节点 1 / 拆分版] 拆分确认值与主参数不匹配（怀疑手抖打错）：\n  - '
            + '\n  - '.join(mismatches)
        )
    return True


def _is_quiet(args) -> bool:
    return bool(getattr(args, 'quiet', False))


def _is_verbose(args) -> bool:
    return bool(getattr(args, 'verbose', False))


def _state_dir(args) -> Optional[str]:
    return getattr(args, 'state_dir', None)


def _print_stamp(stamp: str, args):
    if not _is_quiet(args):
        print(stamp)


# ===== prepare =====

def cmd_prepare(args) -> int:
    from risk_data_prep.scripts.prepare_df import prepare_df

    started = time.time()
    project = args.project
    wide = args.wide

    if not os.path.isfile(wide):
        _err(f'[prepare] 宽表文件不存在: {wide}')
    if args.bad_customer is not None and not os.path.isfile(args.bad_customer):
        _err(f'[prepare] 坏客户清单不存在: {args.bad_customer}')

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

    df, feature_cols = prepare_df(
        wide_path=wide,
        bad_customer_path=args.bad_customer,
        id_col=args.id_col,
        target_col=args.target_col,
        bad_id_col=args.bad_id_col,
        filter=filter_dict,
        exclude_features=exclude_features,
    )

    prepared_path = _prepared_csv_path(project)
    features_path = _features_json_path(project)
    Path(prepared_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(prepared_path, index=False, encoding='utf-8-sig')

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
        'created_at': cli_io.utc_now_iso(),
        'confirmation': confirmation,
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


# ===== analyze =====

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

    state = load_state(project, state_dir=_state_dir(args))

    df = pd.read_csv(prepared, encoding='utf-8-sig')
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
        effective_category_dims = (
            category_dims if category_dims is not None
            else manifest.get('category_dims', [])
        )
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


# ===== export =====

def _write_audit_json(
    *,
    project: str,
    results_dir: str,
    rules_csv_path,
    n_exported: int,
    level: str,
) -> None:
    """C12: 落盘 <project>_audit.json，agent 报回前 cat 这个文件做机器可读自检。

    包含：IV>2.0 过拟合嫌疑特征、不稳定规则列表、文件数、当前 Level。
    自检失败时本函数本身不阻断，仅 stderr 警告——audit 是辅助工具不是关键路径。
    """
    audit = {
        'project_name': project,
        'level': level,
        'created_at': cli_io.utc_now_iso(),
        'n_exported': n_exported,
        'iv_overfit_features': [],
        'unstable_rules': [],
    }

    # 扫 IV 过拟合嫌疑（读已落盘的 _IV分析结果_全量.csv，保证与导出一致）
    try:
        iv_full_path = None
        for fn in (f'{project}_IV分析结果_全量.csv', f'{project}_IV分析结果.csv'):
            cand = os.path.join(results_dir, fn)
            if os.path.isfile(cand):
                iv_full_path = cand
                break
        if iv_full_path:
            iv_df = pd.read_csv(iv_full_path, encoding='utf-8-sig')
            if 'IV值' in iv_df.columns:
                feat_col = '特征' if '特征' in iv_df.columns else (
                    '特征名称' if '特征名称' in iv_df.columns else None
                )
                overfit = iv_df[pd.to_numeric(iv_df['IV值'], errors='coerce') > 2.0]
                if feat_col is not None and not overfit.empty:
                    audit['iv_overfit_features'] = [
                        {'特征': row[feat_col], 'IV值': float(row['IV值'])}
                        for _, row in overfit.iterrows()
                    ]
    except Exception as e:  # noqa: BLE001
        print(f'  [audit 警告] 扫 IV 过拟合特征失败: {e}', file=sys.stderr)

    # 扫规则不稳定（读规则表）
    try:
        if rules_csv_path is not None:
            rules_df = pd.read_csv(str(rules_csv_path), encoding='utf-8-sig')
            if '稳定性等级' in rules_df.columns:
                unstable = rules_df[rules_df['稳定性等级'].astype(str).str.strip() == '不稳定']
                seg_dim = '分群维度' if '分群维度' in unstable.columns else None
                seg_val = '分群名称' if '分群名称' in unstable.columns else (
                    '分群值' if '分群值' in unstable.columns else None
                )
                rule_id = '规则编号' if '规则编号' in unstable.columns else None
                folds = 'CV有效折数' if 'CV有效折数' in unstable.columns else None
                for _, row in unstable.iterrows():
                    entry = {
                        '分群': f"{row.get(seg_dim, '?')}.{row.get(seg_val, '?')}" if seg_dim and seg_val else '全样本',
                        '规则编号': str(row.get(rule_id, '')) if rule_id else '',
                        'CV有效折数': int(row[folds]) if folds and pd.notna(row[folds]) else None,
                    }
                    audit['unstable_rules'].append(entry)
    except Exception as e:  # noqa: BLE001
        print(f'  [audit 警告] 扫规则稳定性失败: {e}', file=sys.stderr)

    audit_path = os.path.join(results_dir, f'{project}_audit.json')
    try:
        with open(audit_path, 'w', encoding='utf-8') as f:
            json.dump(audit, f, ensure_ascii=False, indent=2)
        print(f'  -> {os.path.basename(audit_path)} '
              f'(IV>2 过拟合={len(audit["iv_overfit_features"])} | '
              f'不稳定规则={len(audit["unstable_rules"])})')
    except Exception as e:  # noqa: BLE001
        print(f'  [audit 警告] 写 audit.json 失败: {e}', file=sys.stderr)


def _maybe_export_rules_csv(
    *, inter_dir: str, project: str, output_subdir: str, project_root: str,
):
    """若 _intermediate/rules.pkl 存在，则把规则表写到 data/results/<subdir>/<project>_风险规则表.csv。

    返回写出的 Path（或 None 表示未做）。
    """
    rules_pkl = Path(inter_dir) / 'rules.pkl'
    if not rules_pkl.is_file():
        return None
    try:
        rules_df = pd.read_pickle(rules_pkl)
    except Exception as e:
        print(f'  [警告] 读取 rules.pkl 失败: {e}', file=sys.stderr)
        return None
    if rules_df is None or rules_df.empty:
        # 跑过 rules 但未挖到规则也算有效信号，写一个空表占位
        print('  [提示] rules.pkl 为空（analyze 阶段未挖到满足闸门的规则）', file=sys.stderr)

    from risk_export_report.scripts.report_analysis import export_results as _noop  # noqa
    from risk_rule_mining.scripts.rule_mining_pipeline import export_rules

    out_dir = os.path.join(project_root, 'data', 'results', output_subdir)
    return export_rules(rules_df, project_name=project, output_dir=out_dir)


def cmd_export(args) -> int:
    from risk_export_report.scripts.report_analysis import (
        export_results, build_corr_export, build_lr_export,
        build_comprehensive_table, build_llm_report_data,
    )

    started = time.time()
    project = args.project
    inter_dir = args.intermediate_dir or _intermediate_dir(project)
    output_subdir = args.output_subdir or project

    if not os.path.isdir(inter_dir):
        _err(f'[export] _intermediate/ 不存在: {inter_dir}\n'
             f'建议: 先跑 `python -m risk_pipeline analyze --project {project}`')

    state = load_state(project, state_dir=_state_dir(args))

    results, manifest = cli_io.load_intermediate(inter_dir)

    corr_results = results.get('corr_results') or {}
    meta_results = results.get('meta_results') or {}
    lr_coef_results = results.get('lr_coef_results') or {}
    lr_auc_results = results.get('lr_auc_results') or {}

    if corr_results:
        results['corr_exports'] = build_corr_export(corr_results, meta_results)
    if lr_coef_results:
        results['lr_exports'] = build_lr_export(lr_coef_results, lr_auc_results)

    iv_full_df = results.get('iv_full')
    if iv_full_df is not None and not iv_full_df.empty:
        results['comprehensive'] = build_comprehensive_table(
            iv_full_df, corr_results, lr_coef_results,
            results.get('iv_group_all'),
            raw_features=results.get('raw_features', []),
            derived_features=results.get('derived_features', []),
        )

    df_path = _prepared_csv_path(project)
    if os.path.isfile(df_path) and iv_full_df is not None and not iv_full_df.empty:
        df = pd.read_csv(df_path, encoding='utf-8-sig')
        try:
            results['llm_report_data'] = build_llm_report_data(
                df=df,
                iv_full_df=iv_full_df,
                corr_results=corr_results,
                meta_results=meta_results,
                lr_coef_results=lr_coef_results,
                lr_auc_results=lr_auc_results,
                iv_group_all=results.get('iv_group_all'),
                rel_summary=results.get('reliability_summary'),
                rel_warnings=[],
                comp_all=results.get('feature_set_comparison'),
                feature_cols=results.get('feature_cols', []),
                category_dims=results.get('category_dims', []),
                qual_dims=results.get('qual_dims', []),
                raw_features=results.get('raw_features', []),
                derived_features=results.get('derived_features', []),
                target_col=manifest.get('target_col', 'is_bad'),
            )
        except Exception as e:
            print(f'  [警告] LLM 报告数据构建失败: {e}', file=sys.stderr)

    project_root = _project_root()
    exported = export_results(
        project_root, results,
        project_name=project,
        output_subdir=output_subdir,
        results_base='data/results',
        output_base='output',
    )

    rules_csv = _maybe_export_rules_csv(
        inter_dir=inter_dir, project=project,
        output_subdir=output_subdir, project_root=project_root,
    )
    if rules_csv is not None:
        exported = list(exported) + [rules_csv]

    state.append_history({
        'cmd': 'export',
        'args_summary': {
            'intermediate_dir': inter_dir,
            'output_subdir': output_subdir,
            'n_files': len(exported),
            'rules_csv': str(rules_csv) if rules_csv else None,
        },
        'outputs': [str(p) for p in exported] if exported else [],
        'duration_sec': round(time.time() - started, 2),
        'level_after': 'Level 1',
    }, new_level='Level 1')
    state.save()

    # C12: 写 _audit.json，机器可读自检入口（agent 报回前 cat 这个文件比照 checklist）
    # 注意：必须在 state.append_history(..., new_level='Level 1') 之后写，audit.level 才反映正确层级
    _write_audit_json(
        project=project,
        results_dir=os.path.join(project_root, 'data', 'results', output_subdir),
        rules_csv_path=rules_csv,
        n_exported=len(exported),
        level=state.current_level,
    )

    abs_results_dir = os.path.join(project_root, 'data', 'results', output_subdir)
    abs_output_dir = os.path.join(project_root, 'output', output_subdir)
    _print_stamp(
        format_status_stamp(
            'export', project, state.current_level,
            inputs=[f'{inter_dir}/'],
            outputs=[
                f'{abs_results_dir}/  ← Level 1 分析产物（IV/LR/规则）',
                f'{abs_output_dir}/   ← LLM JSON / 分群画像',
            ],
            extras=[f'{len(exported)} 个文件已落盘'],
        ),
        args,
    )
    return 0


# ===== query =====

def cmd_query(args) -> int:
    from risk_result_query.scripts.results_loader import load_results, top_features

    project = args.project
    try:
        r = load_results(project)
    except FileNotFoundError as e:
        _err(f'[query] {e}')

    df = top_features(
        r, kind=args.kind, dim=args.dim, group=args.group,
        n=args.top, sign=args.sign,
    )

    fmt = args.output_format
    if fmt == 'csv':
        print(df.to_csv(index=False))
    elif fmt == 'json':
        print(df.to_json(orient='records', force_ascii=False, indent=2))
    else:
        if df is None or df.empty:
            print('(无结果)')
        else:
            with pd.option_context('display.max_rows', None, 'display.max_columns', None,
                                   'display.width', 200):
                print(df.to_string(index=False))
    # query 不写 state（不改 level，无副作用）
    return 0


# ===== visualize =====

def cmd_visualize(args) -> int:
    from risk_visualization.scripts.visualize import generate_charts, ALL_KINDS

    started = time.time()
    project = args.project

    kinds: Optional[list] = None
    if args.kinds:
        kinds = [k.strip() for k in args.kinds.split(',') if k.strip()]
        invalid = [k for k in kinds if k not in ALL_KINDS]
        if invalid:
            _err(f'[visualize] 无效 kinds: {invalid}；可选: {list(ALL_KINDS)}')

    try:
        result_paths = generate_charts(
            project_name=project,
            kinds=kinds,
            top_n=args.top,
            out_dir=args.out_dir,
            dim=args.dim,
            dpi=args.dpi,
            project_root=_project_root(),
        )
    except FileNotFoundError as e:
        _err(f'[visualize] {e}')
    except ValueError as e:
        _err(f'[visualize] {e}')

    # 推断输出目录用于 status stamp
    if args.out_dir:
        out_dir_display = args.out_dir
    else:
        out_dir_display = os.path.join('output', project, 'charts')

    summary = ', '.join(
        f'{k}:{len(v)}' for k, v in sorted(result_paths.items())
    ) or '(无图生成；检查结果目录是否完整)'
    skipped = sorted(set((kinds or list(ALL_KINDS))) - set(result_paths.keys()))

    state = load_state(project, state_dir=_state_dir(args))
    state.append_history({
        'cmd': 'visualize',
        'args_summary': {
            'kinds': kinds or list(ALL_KINDS),
            'dim': args.dim,
            'top': args.top,
            'dpi': args.dpi,
        },
        'outputs': [
            p for paths in result_paths.values() for p in paths
        ],
        'duration_sec': round(time.time() - started, 2),
        'level_after': state.current_level,  # visualize 不推进 level
        'note': '只读后置；不推进 level',
    })
    state.save()

    extras = [f'charts={summary}']
    if skipped:
        extras.append(f'skipped={",".join(skipped)}（缺对应 CSV/规则）')
    _print_stamp(
        format_status_stamp(
            'visualize', project, state.current_level,
            inputs=[f'data/results/{project}/'],
            outputs=[f'{out_dir_display}/'],
            extras=extras,
        ),
        args,
    )
    return 0


# ===== trigger =====

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
            f'  若确认无误，重新执行并加 `--confirmed`。'
        )

    df = pd.read_csv(prepared, encoding='utf-8-sig')

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

    output_dir = os.path.join(_project_root(), 'output', project)
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


# ===== explore_thresholds =====

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
        results = load_results(project, project_root=_project_root())
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
        results_dir = os.path.join(_project_root(), 'data', 'results', subdir)

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
        'created_at': cli_io.utc_now_iso(),
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


# ===== report =====

def cmd_report(args) -> int:
    from risk_docx_report.scripts.build_docx_report import build_docx_report

    started = time.time()
    project = args.project
    llm_json_path = args.llm_json or os.path.join(
        _project_root(), 'output', project, f'{project}_LLM报告数据.json',
    )
    report_md_path = args.report_markdown
    out_path = args.output or os.path.join(
        _project_root(), 'output', project, f'{project}.docx',
    )

    if not os.path.isfile(llm_json_path):
        _err(f'[report] LLM JSON 不存在: {llm_json_path}\n'
             f'建议: 先跑 export 子命令落盘 LLM JSON')
    if not os.path.isfile(report_md_path):
        _err(f'[report] --report-markdown 不存在: {report_md_path}')

    state = load_state(project, state_dir=_state_dir(args))
    try:
        state.require_level('Level 1')
    except PipelineLevelError as e:
        _err(f'[report] {e}\n建议: 先跑 export 子命令推进到 Level 1')

    # 阻断节点 3：external 必须显式确认 final version
    if args.purpose == 'external' and not getattr(args, 'confirmed_final_version', False):
        _err(
            '⚠️ [阻断节点 3] 即将生成对外交付的 .docx 报告\n'
            '  原因：.docx 一旦生成并交付，报告与底层数据的一致性承诺即成立；\n'
            '        此后修改 CSV 须同步重新出报告，否则存在数据/报告不一致的合规风险。\n'
            f'  请确认：\n'
            f'    1. 当前的 LLM JSON 是最终版本（无数据更新计划）\n'
            f'    2. 报告用途已对齐（external = 对外交付）\n'
            '  若确认无误，重新执行并加 `--confirmed-final-version`。'
        )

    if args.purpose == 'internal':
        title = f'内部审阅版-{project}风险特征分析报告'
    else:
        title = f'{project}风险特征分析报告'

    appendix_mode = args.appendix_mode or 'both'

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    output = build_docx_report(
        llm_json=Path(llm_json_path),
        report_markdown=Path(report_md_path),
        output_path=Path(out_path),
        title=title,
        appendix_mode=appendix_mode,
    )

    state.append_history({
        'cmd': 'report',
        'args_summary': {
            'purpose': args.purpose,
            'title': title,
            'appendix_mode': appendix_mode,
            'llm_json': llm_json_path,
            'report_markdown': report_md_path,
        },
        'outputs': [str(output)],
        'duration_sec': round(time.time() - started, 2),
        'level_after': 'Level 3',
    }, new_level='Level 3')
    state.save()

    _print_stamp(
        format_status_stamp(
            'report', project, state.current_level,
            inputs=[llm_json_path, report_md_path],
            outputs=[str(output)],
            extras=[f'purpose={args.purpose}', f'title={title}'],
        ),
        args,
    )
    return 0


# ===== run =====

def cmd_run(args) -> int:
    if args.pipeline == 'credit':
        from risk_pipeline.pipeline import run_credit_pipeline
        steps = [s.strip() for s in args.steps.split(',')] if args.steps else None
        started = time.time()
        run_credit_pipeline(steps=steps, verbose=_is_verbose(args) and not _is_quiet(args))
        # credit 用 'credit' 作为 project，state 写入 data/results/征信/credit/
        project = args.project or 'credit'
        state_dir = _state_dir(args) or os.path.join(
            _project_root(), 'data', 'results', '征信', project,
        )
        state = load_state(project, state_dir=state_dir)
        # 只有 export 真的跑了才推进到 Level 1；steps=None 表示全跑（含 export）
        has_export = steps is None or 'export' in steps
        state.append_history({
            'cmd': 'run',
            'pipeline': 'credit',
            'args_summary': {'steps': steps},
            'duration_sec': round(time.time() - started, 2),
            'note': 'credit/gsfc 不可中段独立调用；state 黑盒一项',
        }, new_level='Level 1' if has_export else None)
        state.save()
        if not _is_quiet(args):
            print(f'[run] OK | pipeline=credit | level={state.current_level}')
        return 0

    if args.pipeline == 'gsfc':
        from risk_pipeline.pipeline import run_gsfc_pipeline
        steps = [s.strip() for s in args.steps.split(',')] if args.steps else None
        started = time.time()
        run_gsfc_pipeline(steps=steps, verbose=_is_verbose(args) and not _is_quiet(args))
        project = args.project or 'gsfc'
        state_dir = _state_dir(args) or os.path.join(
            _project_root(), 'data', 'results', '工商财务', project,
        )
        state = load_state(project, state_dir=state_dir)
        has_export = steps is None or 'export' in steps
        state.append_history({
            'cmd': 'run',
            'pipeline': 'gsfc',
            'args_summary': {'steps': steps},
            'duration_sec': round(time.time() - started, 2),
            'note': 'credit/gsfc 不可中段独立调用；state 黑盒一项',
        }, new_level='Level 1' if has_export else None)
        state.save()
        if not _is_quiet(args):
            print(f'[run] OK | pipeline=gsfc | level={state.current_level}')
        return 0

    # generic: prepare → analyze → export
    if not args.wide:
        _err('[run] --pipeline generic 必须提供 --wide')
    if not args.id_col or not args.target_col:
        _err('[run] --pipeline generic 必须提供 --id-col 和 --target-col')
    if not args.project:
        _err('[run] --pipeline generic 必须提供 --project')

    rc = cmd_prepare(_argparse.Namespace(
        wide=args.wide, bad_customer=args.bad_customer,
        id_col=args.id_col, target_col=args.target_col,
        bad_id_col=None, filter_file=None, exclude_features_file=None,
        project=args.project,
        confirmed_new_dataset=getattr(args, 'confirmed_new_dataset', False),
        quiet=_is_quiet(args), verbose=_is_verbose(args),
        state_dir=_state_dir(args),
    ))
    if rc:
        return rc

    rc = cmd_analyze(_argparse.Namespace(
        project=args.project, prepared=None, features_file=None,
        # 默认含 rules，让 visualize 立即能出决策树/规则散点/共现网络
        steps=args.steps or 'univariate,iv,lr,rules',
        category_dims=None, qual_dims=None, target_col=None,
        quiet=_is_quiet(args), verbose=_is_verbose(args),
        state_dir=_state_dir(args),
    ))
    if rc:
        return rc

    rc = cmd_export(_argparse.Namespace(
        project=args.project, intermediate_dir=None, output_subdir=None,
        quiet=_is_quiet(args), verbose=_is_verbose(args),
        state_dir=_state_dir(args),
    ))
    if rc:
        return rc

    if not _is_quiet(args):
        print(f'[run] OK | pipeline=generic | project={args.project} | level=Level 1')
    return 0
