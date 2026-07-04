---
name: risk_segment_univariate
description: 分群摸底与单变量风险分析：类别维度统计、二值标签对比、点二列相关、T 检验与跨分群差异（与特征主题无关）
---

> **何时读我**：只有需要单变量方法口径（相关系数/均值差/T 检验）细节时才读本文件；常规分析走 `python -m risk_pipeline analyze`（见 `references/cli/analyze.md`）。

> **本步是 `analyze` 的一个步骤，agent 不单独跑它。** 用 CLI：
> `python -m risk_pipeline analyze --project X --steps univariate --category-dims 所属行业`
> （通常与 `iv,lr` 一起跑：`--steps univariate,iv,lr`）。下方为方法论与 Python API 参考。

## 这一步做什么

在每个**类别型分群列**（行业、地区、案件类型等）和可选**二值标签列**上算：
分群样本/坏率、点二列相关、好/坏 T 检验、跨分群离散度。
输入 = 宽表 + 二分类目标列（默认 `is_bad`）+ 数值 `feature_cols` + 分群列。与特征来自何种主题无关。

## 本步专用门槛（对应 `SAMPLE_THRESHOLDS`，数值以配置为准）

- 分群进入统计/单变量：`MIN_SAMPLES`（分群总样本）
- 点二列相关与 T 检验：`MIN_BAD_CORR`、`MIN_GOOD_CORR`

**向业务用户解释跳过原因**统一用 `docs/GLOSSARY.md`「判定标准（业务口径）」的话术，不展示英文常量名。

## 本 Skill 强制规范

- 每条相关/T 检验结果须能关联到分群元信息（`n_total`、`n_bad`、坏率，由 `meta_df` 给出）。
- 跳过某分群时逐条 log 原因。
- 不输出敏感标识字段。

相关系数结果由 `analyze` 的 LR / `export` 步骤自动消费；导出后用 `python -m risk_pipeline query --kind corr` 查询。

## 底层脚本（仅 notebook/单测，agent 走 CLI）

> 实现在本目录 `scripts/`，**仅供 notebook/单测/调试直接 import；agent 一律用上面的 `analyze --steps univariate`**（`AGENTS.md` 三禁止在 Bash 里 import 模块手抄）。

| 模块 | 作用 |
|------|------|
| `scripts/segment_univariate.py` | 分群检测、统计、单变量、跨分群方差 |
| `scripts/univariate.py` | `calc_correlation_pvalue`、`ttest_good_bad` 等底层计算 |
