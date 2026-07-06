# -*- coding: utf-8 -*-
"""9 子命令实现（组合根）：每命令一文件，薄壳 wrap 现有 Python API + state.json 状态管理。

- prepare:            调 risk_data_prep.scripts.prepare_df.prepare_df → 写 prepared.csv + features.json
- analyze:            调 risk_pipeline.pipeline.run_generic_pipeline → 写 _intermediate/
- export:             读 _intermediate/ → 调 risk_export_report.scripts.report_analysis.export_results
- query:              调 risk_result_query.scripts.results_loader.load_results + top_features
- visualize:          调 risk_visualization.scripts.visualize.generate_charts
- trigger:            调 risk_trigger_extraction.scripts.trigger_extraction.extract_triggers
- explore_thresholds: 调 risk_threshold_explore.scripts.threshold_explore.explore_thresholds
- report:             调 risk_docx_report.scripts.build_docx_report.build_docx_report
- run:                便捷组合：generic 走 prepare→analyze→export；credit/gsfc 直接转发现有链路

cli.py 通过 getattr(commands, f'cmd_{子命令}') 分发，故此处必须导出全部 cmd_*。
"""
from .analyze import cmd_analyze
from .explore import cmd_explore_thresholds
from .export import cmd_export
from .prepare import cmd_prepare
from .query import cmd_query
from .report import cmd_report
from .run import cmd_run
from .trigger import cmd_trigger
from .visualize import cmd_visualize

__all__ = [
    'cmd_prepare',
    'cmd_analyze',
    'cmd_export',
    'cmd_query',
    'cmd_visualize',
    'cmd_trigger',
    'cmd_explore_thresholds',
    'cmd_report',
    'cmd_run',
]
