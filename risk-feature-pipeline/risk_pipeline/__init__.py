# -*- coding: utf-8 -*-
"""risk-feature-pipeline 公共配置 + 统一 CLI 入口模块。

子模块:
  config         - 数据/阈值/列名常量
  config_loader  - YAML 配置加载（默认值 + 用户覆盖深度合并）
  column_mapper  - 多银行字段映射
  pipeline       - run_credit_pipeline / run_gsfc_pipeline / run_generic_pipeline
  cli            - 9 子命令 CLI（prepare/analyze/export/query/visualize/trigger/explore_thresholds/report/run）
"""
