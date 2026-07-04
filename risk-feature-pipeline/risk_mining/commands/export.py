# -*- coding: utf-8 -*-
"""export 子命令：读 _intermediate/ → 8 张 CSV + LLM JSON + audit（→ Level 1）。"""
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
    _intermediate_dir,
    _output_root,
    _prepared_csv_path,
    _print_stamp,
    _state_dir,
)


def _write_audit_json(
    *,
    project: str,
    results_dir: str,
    rules_csv_path,
    n_exported: int,
    level: str,
) -> None:
    """C12: 落盘 <project>_audit.json，agent 报回前 cat 这个文件做机器可读自检。

    包含：IV>2.0 疑似数据穿越特征（键名沿用 iv_overfit_features）、不稳定规则列表、文件数、当前 Level。
    自检失败时本函数本身不阻断，仅 stderr 警告——audit 是辅助工具不是关键路径。
    """
    audit = {
        'project_name': project,
        'level': level,
        'created_at': cli_io.now_iso(),
        'n_exported': n_exported,
        'iv_overfit_features': [],
        'unstable_rules': [],
    }

    # 扫 IV 疑似数据穿越（IV>2，读已落盘的 _IV分析结果_全量.csv，保证与导出一致）
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
        print(f'  [audit 警告] 扫 IV 疑似数据穿越特征失败: {e}', file=sys.stderr)

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
              f'(IV>2 疑似穿越={len(audit["iv_overfit_features"])} | '
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

    project_root = _output_root()  # export 写产物 → output_root
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
