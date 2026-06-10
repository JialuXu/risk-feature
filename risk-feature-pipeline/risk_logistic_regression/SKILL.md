---
name: risk_logistic_regression
description: 分群多变量逻辑回归：标准化 + L2、按样本量选择 CV 或训练集 AUC、两套特征子集 AUC 对比与相关-LR 对照（与特征主题无关）
---

## 方法论前提（与数据来源无关）

- **输入**：同粒度宽表；二分类目标列（默认 `is_bad`）；数值 `feature_cols`；分群列与可选二值标签列；`compare_feature_sets` 需要两组互斥或可比的特征列表（内置场景常命名为「原始 / 衍生」，你也可定义为「司法 / 非司法」「表 A / 表 B」等任意业务含义）。
- **输出**：各分群标准化系数、AUC 及 AUC 类型、特征集对比、与单变量结论的对照标签。

实现代码位于本目录 `scripts/`。

## 流水线位置

- **前置**：宽表与 `feature_cols`（`risk_feature_engineering` 或自备）；与单变量衔接时消费 `risk_segment_univariate` 的相关系数矩阵（如 `compare_corr_lr`）。
- **后置**：`risk_export_report` 写入 LR 系数与 AUC 相关标准文件。
- **全局约定**：建模与 CV 门槛取自 `scripts/config.py` 的 `SAMPLE_THRESHOLDS`；跳过须打印原因；**禁止**不标注类型地报告训练集 AUC。

## 何时使用（触发）

- 分群逻辑回归、标准化系数、AUC（交叉验证或降级）、两套特征子集的 AUC 对比、相关与 LR 系数一致性。

## 职责边界

| 负责 | 不负责 |
|------|--------|
| `lr_by_group`、`lr_by_qualification`、`_fit_lr_single` | IV 与分箱（见 `risk_iv_diagnosis`） |
| `compare_feature_sets`、`compare_corr_lr` | 八文件导出与 LLM 报告结构（见 `risk_export_report`） |

## 调用入口（最小示例）

```python
from risk_logistic_regression.scripts.group_logistic_regression import (
    lr_by_group,
    lr_by_qualification,
    compare_feature_sets,
    compare_corr_lr,
)

coef_df, auc_df, skipped = lr_by_group(
    df, '所属行业', feature_cols, min_bad=20, min_good=50, min_group_size=50
)  # 分群列名示例
coef_df, auc_df, skipped = lr_by_qualification(
    df, qual_dims, feature_cols, min_bad=20, min_good=50
)
comp_df = compare_feature_sets(
    df, '所属行业', raw_features, derived_features, min_bad=20, min_good=50
)  # 两组列表可为任意业务含义下的特征子集
comparison_df = compare_corr_lr(corr_df, lr_coef_df)
```

## 本步专用门槛（与 config 对应）

常量名见 `SAMPLE_THRESHOLDS`，数值以配置文件为准：

- 单模型拟合：`MIN_BAD_LR`、`MIN_GOOD_LR`；有效特征过少时跳过（脚本内判断）。
- AUC：`MIN_SAMPLES_CV`、`MIN_BAD_CV` 决定是否采用 5 折分层 CV，否则为训练集 AUC，且 **AUC 类型字段须显式标注**（如训练集因样本不足）。

**向业务用户解释 AUC 类型、跳过原因时**，统一使用 `docs/GLOSSARY.md`「判定标准（业务口径）」的话术与数值，不向业务用户展示英文常量名。

## 模型设定（概要）

- `StandardScaler` + `LogisticRegression(penalty='l2', C=1.0, solver='lbfgs')`；系数以标准化后尺度解释。
- 拟合异常须捕获并记入跳过原因（脚本已实现 try/except 路径时遵循脚本）。

## 相关 vs LR（语义约定）

- **稳健 / 冗余 / 抑制 / 弱相关** 等标签以 `compare_corr_lr` 的规则为准，用于解读多变量与单变量结论差异，不替代 IV 可信度。

## 主要脚本映射

| 模块 | 作用 |
|------|------|
| `scripts/group_logistic_regression.py` | 分群 LR、特征集对比、相关-LR 对照 |
| `scripts/base_modeling.py` | `fit_logistic_regression`（系数字典含 `AUC类型`）、`eval_lr_roc_auc` 与 config 中 CV 门槛对齐 |
