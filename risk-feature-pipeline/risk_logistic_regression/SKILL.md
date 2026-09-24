---
name: risk_logistic_regression
description: 分群多变量逻辑回归（诊断用，非部署模型）：标准化 + L2、按样本量选 CV 或训练集 AUC、两套特征子集 AUC 对比（与特征主题无关）。当用户说"LR/逻辑回归"、"回归系数"、"AUC"、"多变量效果"时触发。
---

> **何时读我**：只有需要 LR 建模细节（标准化、L2、AUC 类型判定）时才读本文件；常规分析与查询走 analyze/query CLI 卡。

> **本步是 `analyze` 的一个步骤，agent 不单独跑它。** 用 CLI：
> `python -m risk_pipeline analyze --project X --steps lr`（通常 `--steps univariate,iv,lr`）。
> 下方为方法论与 Python API 参考。

> **场景定位**：LR 在本仓库是**诊断工具**，用来看某分群整体可分性与多变量系数方向，
> **不是评分卡/部署模型**。AUC 只作诊断佐证，不得当结论主角或排序依据（见 `report-prompt.md` 硬规则 7）。

## 这一步做什么

对每个分群拟合 `StandardScaler` + `LogisticRegression`（默认 L2 正则，`C=1.0`，`solver='lbfgs'`），
产出标准化系数、AUC 及 **AUC 类型**、可选两套特征子集（如原始/衍生）的 AUC 对比。
输入 = 宽表 + 二分类目标列（默认 `is_bad`）+ 数值 `feature_cols` + 分群列。

## 本步专用门槛（对应 `SAMPLE_THRESHOLDS`，数值以配置为准）

- 单模型拟合：`MIN_BAD_LR`、`MIN_GOOD_LR`；有效特征过少时跳过
- AUC 类型：`MIN_SAMPLES_CV`、`MIN_BAD_CV` 决定是否走 5 折分层 CV，否则为训练集 AUC
- **AUC 类型字段须显式标注**：`5折交叉验证` / `训练集(样本不足)` / `训练集(CV失败)`
- 向业务用户解释 AUC 类型/跳过原因，统一用 `docs/GLOSSARY.md` 话术

## 底层脚本（仅 notebook/单测，agent 走 CLI）

> 实现在本目录 `scripts/`，**仅供 notebook/单测/调试直接 import；agent 一律用上面的 `analyze --steps lr`**（`AGENTS.md` 三禁止在 Bash 里 import 模块手抄）。

| 模块 | 作用 |
|------|------|
| `scripts/group_logistic_regression.py` | 分群 LR：`lr_by_group`、`lr_by_qualification`、`_fit_lr_single` |
