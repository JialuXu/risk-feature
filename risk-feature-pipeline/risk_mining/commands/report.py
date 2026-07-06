# -*- coding: utf-8 -*-
"""report 子命令：LLM JSON + Markdown → .docx（→ Level 3；阻断节点 3）。"""
from __future__ import annotations

import os
import time
from pathlib import Path

from risk_pipeline.pipeline_state import PipelineLevelError, format_status_stamp, load_state

from ._common import _err, _output_root, _print_stamp, _state_dir


def cmd_report(args) -> int:
    from risk_docx_report.scripts.build_docx_report import build_docx_report

    started = time.time()
    project = args.project
    llm_json_path = args.llm_json or os.path.join(
        _output_root(), 'output', project, f'{project}_LLM报告数据.json',
    )
    report_md_path = args.report_markdown
    out_path = args.output or os.path.join(
        _output_root(), 'output', project, f'{project}.docx',
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
