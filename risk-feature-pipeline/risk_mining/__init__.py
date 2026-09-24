# -*- coding: utf-8 -*-
"""risk_mining —— 挖掘内核 + 组合根（DECOUPLING-DESIGN §4）。

挖掘内核（只依赖 risk_core；导出步另调其实现 risk_export_report）:
  analysis/       - engine（分群单变量/IV/LR）+ iv_core（IV/WOE/自适应分箱/可信度）
  pipeline        - run_generic_pipeline：generic 链路 Python API
  pipeline_state  - .pipeline_state.json：Level 状态机
  export          - assemble_exports：唯一导出装配

组合根/路由层（唯一允许同时 import 内核与各子 skill 的地方）:
  cli       - 顶层薄 CLI：解析参数 + 分发/转发到子命令（唯一 blessed 入口）
  argspec   - flag 单一注册表
  commands/ - 9 个子命令实现（cmd_prepare/analyze/export/query/visualize/
              trigger/explore_thresholds/report/run），每命令一文件

分层红线由 tests/test_unit_kernel_boundary.py 机器化验收（含字符串式动态导入）。
对 agent 而言入口是 `python -m risk_pipeline <子命令>`（risk_pipeline 转发至此）。
"""
