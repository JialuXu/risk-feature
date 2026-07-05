# -*- coding: utf-8 -*-
"""risk_legacy_chains 顶层包：征信(credit) + 工商财务(gsfc) 黑盒链路编排层。

与 risk_mining 平级的**编排层**（非独立子 skill——合法地跨多个子 skill 复用）。
两条链路从 risk_pipeline/pipeline.py 逐字迁出（解耦收尾），算法/前端/内核均未改动。
"""
