# -*- coding: utf-8 -*-
"""兼容 shim：9 子命令实现已拆入组合根 ``risk_mining.commands``（解耦重构阶段 2）。

原 1382 行单文件按命令拆成 risk_mining/commands/<cmd>.py（LLM 每任务只加载单命令上下文）。
保留 ``from risk_pipeline.cli_commands import cmd_X`` 旧导入路径，逐字转发。
"""
from risk_mining.commands import (  # noqa: F401  再导出：实现已拆入 risk_mining.commands
    cmd_analyze,
    cmd_explore_thresholds,
    cmd_export,
    cmd_prepare,
    cmd_query,
    cmd_report,
    cmd_run,
    cmd_trigger,
    cmd_visualize,
)
