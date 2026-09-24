# -*- coding: utf-8 -*-
"""risk_legacy_chains 顶层包：征信(credit) + 工商财务(gsfc) 黑盒链路编排层。

独立的**编排层 skill**（与 risk_mining 平级；有自己的 SKILL.md，但刻意不挂进顶层
主路径路由）。合法地跨多个子 skill 复用，故不作为 pipeline 的某一步。
两条链路保持原口径，数值由 tests/test_golden_legacy_chains.py 锁定。
"""
