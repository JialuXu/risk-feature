# -*- coding: utf-8 -*-
"""risk_core —— 稳定契约底座（叶子层：谁都能依赖，它谁都不依赖）。

解耦重构（DECOUPLING-DESIGN §4）抽出的最底层包：只含路径/配置/字段映射/
IO/字体/结果读取等无编排、无状态机、无分析算法的稳定件，以及 ``contracts``
（wire schema + 列名/dtype/白名单/文件名模板的单一真源）。

子模块:
  paths           - 项目根/输出根定位（唯一权威）
  config          - 数据/阈值/列名常量（import 时从 YAML 冻结）
  config_loader   - YAML 加载（默认值 + 用户覆盖深度合并）
  column_mapper   - 多银行字段映射 ColumnMapper
  io_utils        - CSV 编码探测 + 批量加载
  font_utils      - matplotlib 中文字体 OS 探测
  results_loader  - load_results + Results（读已导出结果，只读）
  contracts       - §5 磁盘契约单一真源（列名/dtype/白名单/文件名模板/wire schema）

依赖规则：risk_core 不反向依赖任何上层（risk_pipeline / risk_mining / 子 skill）。
兼容性：旧路径 ``risk_pipeline.paths`` 等经 ``risk_pipeline/`` 下的
模块别名转发到此处，是同一对象（``risk_pipeline.paths is risk_core.paths``）。
"""
