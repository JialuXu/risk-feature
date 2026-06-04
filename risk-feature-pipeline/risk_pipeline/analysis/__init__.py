# -*- coding: utf-8 -*-
"""共享分析内核：IV / 引擎 / 导出逻辑的单一权威实现。

历史背景：原先 risk_iv_diagnosis / risk_export_report / risk_logistic_regression
三个 Skill 各自携带一份近乎相同的 ~2400 行分析代码（镜像复制）。本包把真正活着的
逻辑收敛到唯一一处，各 Skill 的 scripts/*.py 退化为再导出 shim，保留原导入路径。
"""
