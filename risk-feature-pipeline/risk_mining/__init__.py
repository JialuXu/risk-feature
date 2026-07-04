# -*- coding: utf-8 -*-
"""risk_mining —— 挖掘内核 + 组合根（DECOUPLING-DESIGN §4）。

解耦重构阶段 2 起，统一 CLI 的「组合根/路由层」落于此包：
  cli       - 顶层薄 CLI：解析参数 + 分发/转发到子命令（唯一 blessed 入口）
  commands/ - 9 个子命令实现（cmd_prepare/analyze/export/query/visualize/
              trigger/explore_thresholds/report/run），每命令一文件

依赖规则：组合根可 import risk_core（叶子）、挖掘内核、子 skill（转发函数直调）；
挖掘内核 (analyze/export/analysis/pipeline_state) 不得 import 任何子 skill。
对 agent 而言入口仍是 `python -m risk_pipeline <子命令>`（risk_pipeline 转发至此）。
"""
