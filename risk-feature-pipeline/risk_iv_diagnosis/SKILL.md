---
name: risk_iv_diagnosis
description: IV 与可信度诊断：自适应分箱、WOE 截断、缺失单独成箱、分群 IV 与可信度评级（适用于任意数值特征宽表）。当用户说"IV 分析"、"IV 可信度"、"哪些特征区分度高"时触发；业务阈值切点请用 risk_threshold_explore。
---

> **何时读我**：只有需要 IV/自适应分箱/可信度算法细节时才读本文件；常规分析与查询走 analyze/query CLI 卡。

> **本步是 `analyze` 的一个步骤，agent 不单独跑它。** 用 CLI：
> `python -m risk_pipeline analyze --project X --steps iv`（通常 `--steps univariate,iv,lr`）。
> 下方为方法论与 Python API 参考。

## 这一步做什么

对数值/可分箱 `feature_cols` 算：IV 值、自适应分箱元信息、WOE（截断到 `[-WOE_CAP, +WOE_CAP]`）、
缺失单独成箱、分群 IV、可信度等级与诊断告警。输入 = 宽表 + 二分类目标列（默认 `is_bad`）。
不限于征信主题。

## 可信度与 IV 分档（关键业务口径）

- **可信度等级**：`可信` / `参考` / `不可信-样本不足` / `不可信-疑似数据穿越`（由样本量与 IV magnitude 联合判断）
- **IV 预测力分档**：`iv_power_label(iv)` → `无`(<0.02) / `弱`(<0.1) / `中`(<0.3) / `强`(≥0.3)
- **铁律**：`IV > IV_SUSPECT_THRESHOLD`（2.0）= 疑似数据穿越，**强制排除出结论推荐**，不得正常引用
- 向业务用户解释分档/可信度/跳过原因，统一用 `docs/GLOSSARY.md`「判定标准（业务口径）」话术，不展示英文常量名

## 关键配置（`scripts/config.py`）

- `SAMPLE_THRESHOLDS`：`MIN_SAMPLES`、`MIN_BAD_SAMPLES`（分群准入）
- IV 稳健性：`IV_SUSPECT_THRESHOLD`、`WOE_CAP`、`ADAPTIVE_BINS_*`、`IV_THRESHOLD`（弱/中/强档）

## 方法要点

- **自适应分箱**：小样本降箱数，避免坏为 0 的箱用 0.5 校正导致 IV 虚高
- **缺失**：单独成箱，IV 贡献与非缺失部分分开统计汇总

## 输出形态

全量 IV 表、分群 IV 明细、IV 可信度透视、诊断汇总与告警；可选 optbinning 阈值明细。
标准文件名与目录由 `risk_export_report` 落盘（查询用 `risk_result_query` 的 `kind='iv'` / `'iv_group'`）。

## 底层脚本（仅 notebook/单测，agent 走 CLI）

> 实现在本目录 `scripts/`，**仅供 notebook/单测/调试直接 import；agent 一律用上面的 `analyze --steps iv`**（`AGENTS.md` 三禁止在 Bash 里 import 模块手抄）。

| 模块 | 作用 |
|------|------|
| `scripts/iv_analysis.py` | `calc_iv`、`_adaptive_bins`、`_assess_iv_reliability`、`iv_power_label` |
| `scripts/iv_group_diagnosis.py` | 全量/分群 IV 编排、`reliability_diagnosis` |
