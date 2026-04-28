---
name: risk_feature_engineering
description: 风险特征工程：比率/占比/效率类衍生、安全除法与缩尾，并产出可分析数值特征列（内置多类主题模板，可扩展）
---

## 方法论前提（与数据来源无关）

- **输入**：主实体粒度宽表 + 目标列 + 用于建模的原始度量列（不同主题下字段名不同，但应可映射为「分子/分母」或可对比的强度/占比）。
- **输出**：尽量使用**可比、可解释、对规模不敏感**的衍生列；并给出进入 IV/LR/单变量的 `feature_cols`（或等价列表）。
- **新主题（如司法）**：本目录脚本提供的是**可复用的工程模式**（安全除法、缩尾、列筛选）；具体司法指标需你新增函数或配置列清单，再与下游对齐命名。

实现代码位于本目录 `scripts/`。

## 流水线位置

- **前置**：`risk_data_prep` 或任意方式得到的同粒度宽表。
- **后置**：`risk_segment_univariate`、`risk_iv_diagnosis`、`risk_logistic_regression` 使用本步输出的比率类列及 `feature_cols`。
- **全局约定**：全流水线禁止静默跳过；与本步相关的列存在性检查、重复构造防护以脚本为准。

## 何时使用（触发）

- 将原始度量转为比值/占比/周转/强度类特征、消除规模影响、在进入 IV/LR 前统一数值质量。

## 职责边界

| 负责 | 不负责 |
|------|--------|
| 调用本目录内置脚本生成**参考主题**的衍生列（见下表） | 司法等未内置主题的领域规则（需自行实现后接入同一流程） |
| `safe_divide`、对比率列 Winsorize（在内置路径中） | 宽表合并与目标列打标（见 `risk_data_prep`） |
| 用 `get_feature_cols` 等筛出参与建模/IV 的数值列 | IV 分箱、WOE、可信度等级（见 `risk_iv_diagnosis`） |

## 调用入口（最小示例）

**仅使用内置模板时**（按宽表中实际存在的侧表选择调用子集，不必强行全开）：

```python
from risk_feature_engineering.scripts.credit_feature_engineering import create_credit_features
from risk_feature_engineering.scripts.financial_feature_engineering import feature_engineering, get_feature_cols
from risk_feature_engineering.scripts.change_feature_engineering import feature_engineering_gsbb

df = create_credit_features(df)
df = feature_engineering(df)
df = feature_engineering_gsbb(df)
feature_cols = get_feature_cols(df)
```

**自备司法或其他主题特征**：自行生成数值列后，保证列类型为数值、含义可解释，并自行维护 `feature_cols`（可与 `get_feature_cols` 的筛选原则对齐或独立维护）。

## 关键配置（仅列本步读取项）

- `CREDIT_CONFIG['raw_features']`、`CREDIT_CONFIG['derived_features']`：内置流程中用于划分「原始/衍生」特征子集的列清单；其他主题可仿照在自有配置中维护 `raw_features` / `derived_features` 或等价两组列表供 LR 对比使用。

## 本 Skill 强制规范

- 参与风险解释的连续特征以**比率/效率/占比类衍生**为主；绝对量原始指标默认不进入分析集（以 `get_feature_cols` 及关键词规则为准，或在你自有筛选中显式声明例外）。
- 所有除法须走脚本内 `safe_divide`（或等价实现），避免分母为 0 或 NaN 导致 Inf。
- Winsorize 针对比率类列（脚本对例外列如营运资金、自由现金流、他行融资估算等排除缩尾）；具体分位数与列集合以脚本为准。
- 构造前检查基础列是否存在；若衍生列已存在避免重复计算。
- 运行后应能说明：新增/保留的衍生列规模、缩尾影响范围（以脚本打印为准）。

## 内置脚本覆盖的主题（概要，细节以脚本为准）

| 主题域 | 模块入口 | 说明 |
|--------|----------|------|
| 机构与授信行为类 | `create_credit_features` | 本仓库中命名偏「征信」场景，本质是机构/渠道/笔数占比与交叉强度 |
| 财务报表类 | `feature_engineering` | 比率为核心的财务衍生 |
| 工商变更类 | `feature_engineering_gsbb` | 变更频次、集中度、近期占比等 |
| 司法等 | （无内置） | 按同一原则自编：占比、强度/时间衰减、计数比等，并纳入 `feature_cols` |

## 主要脚本映射

| 模块 | 作用 |
|------|------|
| `scripts/io_utils.py` | `safe_divide`、编码自适应读 CSV、`load_data`（与内置路径配置配合） |
| `scripts/credit_feature_engineering.py` | `create_credit_features`、`get_feature_sets` |
| `scripts/financial_feature_engineering.py` | `feature_engineering`、`get_feature_cols` |
| `scripts/change_feature_engineering.py` | `feature_engineering_gsbb` |
