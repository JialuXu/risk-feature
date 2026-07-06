---
name: risk_feature_engineering
description: 风险特征工程：比率/占比/效率类衍生、安全除法与缩尾，并产出可分析数值特征列（内置多类主题模板，可扩展）
---

> **何时读我**：只有需要理解或修改衍生特征公式时才读本文件；agent 常规工作流不直接调用本 skill（特征工程内嵌在 credit/gsfc 链路中）。

> **本步在 `python -m risk_pipeline run --pipeline credit/gsfc` 内部自动执行，没有独立 CLI 子命令，agent 不单独跑它。**
> `generic` 链路默认用用户宽表里已有的数值列（`prepare` 自动选列）；如需衍生比率特征，
> 在调用 `run` 前于 notebook 造好列、并入宽表再喂 `--wide`（见文末「底层脚本」）。

## 这一步做什么

把原始度量转成**可比、可解释、对规模不敏感**的衍生列（比率/占比/周转/强度），
并给出进入 IV/LR/单变量的 `feature_cols`。输入 = 主实体粒度宽表 + 目标列 + 原始度量列。

## 本 Skill 强制规范

- 参与风险解释的连续特征以**比率/效率/占比类衍生**为主；绝对量原始指标默认不进分析集（以 `get_feature_cols` 关键词规则为准，例外需显式声明）。
- 所有除法走 `safe_divide`，避免分母为 0/NaN 产生 Inf。
- Winsorize 仅针对比率类列（脚本对营运资金、自由现金流、他行融资估算等列排除缩尾）；分位数与列集合以脚本为准。
- 构造前检查基础列存在；衍生列已存在则避免重复计算。
- 运行后应能说明：新增/保留的衍生列规模、缩尾影响范围（以脚本打印为准）。

## 关键配置

- `CREDIT_CONFIG['raw_features']` / `['derived_features']`：内置流程中划分「原始/衍生」特征子集的列清单，供 LR 对比使用；其他主题仿照在自有配置维护等价两组。

## 内置脚本覆盖的主题

| 主题域 | 入口 | 说明 |
|--------|------|------|
| 机构与授信行为类 | `create_credit_features` | 机构/渠道/笔数占比与交叉强度 |
| 财务报表类 | `feature_engineering` | 比率为核心的财务衍生 |
| 工商变更类 | `feature_engineering_gsbb` | 变更频次、集中度、近期占比 |
| 司法等 | （无内置） | 按同一原则自编：占比、强度/时间衰减、计数比，并纳入 `feature_cols` |

## 底层脚本（无独立子命令）

> 本步在 `run --pipeline credit/gsfc` 内**自动执行**，没有独立 CLI 子命令，agent 不单独跑。
> 仅当 `generic` 链路要自备衍生特征时，才在喂 `--wide` 前于 notebook 造列（属数据准备、非链路步骤）：按宽表实际侧表选调 `create_credit_features` / `feature_engineering` / `feature_engineering_gsbb`，再用 `get_feature_cols(df)` 取列。自备其他主题：自行生成数值列并维护 `feature_cols`。

## 主要脚本映射

| 模块 | 作用 |
|------|------|
| `scripts/io_utils.py` | `safe_divide`、编码自适应读 CSV、`load_data` |
| `scripts/credit_feature_engineering.py` | `create_credit_features`、`get_feature_sets` |
| `scripts/financial_feature_engineering.py` | `feature_engineering`、`get_feature_cols` |
| `scripts/change_feature_engineering.py` | `feature_engineering_gsbb` |
