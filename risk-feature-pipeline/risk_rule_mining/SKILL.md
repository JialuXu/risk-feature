---
name: risk_rule_mining
description: 决策树规则挖掘：从宽表产出可读风险规则（非建模），用于预警策略、审批规则与贷后触发条件设计；产出规则表含覆盖率/坏账率/Lift/稳定性
---

## 方法论前提（与数据来源无关）

- **输入**：主实体粒度的宽表；二分类目标列（默认 `is_bad`）；用于分裂的数值/可分箱特征列；可选分群列。
- **产出对象**：**可读的规则**（如 `资产负债率 > 0.75 且 短期借款占比 > 0.40`），每条附带覆盖率、覆盖坏客户数、坏账率、Lift、稳定性评级。
- **非产出**：不产出预测概率、不替代 `risk_logistic_regression` 作为评分模型。定位为 **IV（单变量）+ LR（加性）** 之外的 **多变量交互规则** 补充。

实现代码位于本目录 `scripts/`。

## 业务价值

1. **多变量交互**：补充 IV（单变量）与 LR（加性）的盲区，识别组合信号（高杠杆+短借款期限、行业×规模等）。
2. **规则可落地**：直接可作为预警触发条件、审批剔除条件、贷后检查清单。
3. **分群替代验证**：树可能发现比人工分群（行业/性质）更优的风险细分。

## 流水线位置

- **前置**：`risk_data_prep`（宽表）+ `risk_feature_engineering`（衍生特征）+ `risk_iv_diagnosis`（用 IV 预筛强特征，避免树用噪声列分裂）。
- **推荐输入特征集**：IV ≥ `IV_THRESHOLD['medium']` 且可信度为"可信/参考"的特征；自动剔除 IV > `IV_SUSPECT_THRESHOLD` 的过拟合嫌疑特征。
- **后置**：`risk_export_report` 增量追加 `_风险规则表.csv` 与 LLM JSON 的 `rules` 节点。

## 何时使用（触发）

- 需要产出**业务规则清单**、**预警触发条件**、**审批红线规则**、**贷后检查项**。
- 需要识别**特征交互效应**（LR 无法识别）。
- 需要**替代或验证人工分群维度**（树分裂的 feature 可能揭示更优切分）。

## 职责边界

| 负责 | 不负责 |
|------|--------|
| 决策树拟合、规则路径提取、规则评估（覆盖率/Lift/置信） | 评分模型训练（见 `risk_logistic_regression`） |
| 规则交叉验证稳定性、规则去重与排序 | 特征工程（见 `risk_feature_engineering`） |
| 分群规则挖掘、规则业务语言格式化 | 八文件命名与 LLM JSON 主干（见 `risk_export_report`） |

## 调用入口（最小示例）

```python
from risk_rule_mining.scripts.rule_extraction import mine_rules
from risk_rule_mining.scripts.rule_evaluation import evaluate_rules
from risk_rule_mining.scripts.rule_stability import assess_rule_stability
from risk_rule_mining.scripts.rule_mining_pipeline import rules_by_group, export_rules

# 1. 全样本规则挖掘
rules_df = mine_rules(df, feature_cols, target='is_bad')

# 2. 分群规则挖掘（每个行业/性质/分行分别挖掘）
rules_grouped = rules_by_group(df, segment_col='所属行业',
                               feature_cols=feature_cols, target='is_bad')

# 3. 稳定性评估（5-fold CV）
stable_rules = assess_rule_stability(df, rules_df, feature_cols, target='is_bad')

# 4. 导出 CSV + LLM 文本
export_rules(rules_df, project_name='征信特征分析')
```

## 关键配置（本步为主）

取自 `risk_pipeline.config.RULE_MINING_CONFIG`：

| 参数 | 默认 | 作用 |
|------|------|------|
| `max_depth` | 3 | 树最大深度，限制规则可读性 |
| `min_samples_leaf_ratio` | 0.05 | 叶子最少样本占比（防过拟合） |
| `min_bad_in_leaf` | 5 | 叶子最少坏客户数 |
| `min_coverage` | 0.01 | 规则最小覆盖率 |
| `min_lift` | 1.5 | 规则最小 Lift |
| `top_k_per_segment` | 10 | 每群保留 Top-K |
| `cv_splits` | 5 | 稳定性交叉验证折数 |
| `stability_min_folds` | 3 | 判"稳定"的最少出现折数 |
| `class_weight` | balanced | 样本不平衡权重策略 |

样本准入沿用 `SAMPLE_THRESHOLDS`：`MIN_BAD_LR`（20）、`MIN_GOOD_LR`（50）—— 规则挖掘对坏样本量的要求与 LR 一致。

## 方法与规范（本 Skill 专有）

- **规则定义**：从根到叶的**完整路径**即为一条规则；每条规则为若干 `特征 op 阈值` 的合取（AND）。
- **规则筛选**：叶节点坏账率 > 整体坏账率（Lift > 1）且满足 `min_coverage` / `min_lift` / `min_bad_in_leaf` 三道闸门。
- **规则排序**：优先按 Lift 降序，次按覆盖率降序（Lift 相同时优先覆盖广的）。
- **稳定性**：k-fold 交叉验证，同一规则在 holdout 的坏账率 mean/std，出现在 `stability_min_folds` 折以上视为稳定。
- **去重**：不同树路径可能产生等价规则，按 `(特征集合, 阈值四舍五入)` 去重。
- **输出语言**：规则以中文业务语言呈现（如 `资产负债率 大于 0.75`），避免技术符号。

## 主要脚本映射

| 模块 | 作用 |
|------|------|
| `scripts/rule_extraction.py` | 决策树拟合 + 路径→规则转换 + 规则去重 |
| `scripts/rule_evaluation.py` | 单规则/批量规则评估：覆盖率、坏账率、Lift、置信区间 |
| `scripts/rule_stability.py` | K-fold 交叉验证稳定性评估 |
| `scripts/rule_mining_pipeline.py` | 分群挖掘编排 + 导出 |
| `scripts/config.py` | 模块配置（`from risk_pipeline.config import *`） |

## 输出形态（字段级）

**CSV：`{项目名}_风险规则表.csv`**

| 字段 | 含义 |
|------|------|
| 分群维度 / 分群值 | 规则所属分群（全样本时填"全样本"） |
| 规则编号 | 分群内递增 |
| 规则条件 | 中文业务语言（合取串联） |
| 涉及特征 | 规则中出现的特征列表 |
| 特征数量 | 交互深度 |
| 覆盖样本数 / 覆盖率 | 命中规则的客户数与占比 |
| 覆盖坏客户数 / 坏账率 | 命中客户中坏客户数与坏账率 |
| 整体坏账率 | 分群整体坏账率（用于计算 Lift） |
| Lift | 规则坏账率 / 整体坏账率 |
| CV 坏账率均值 / 标准差 | 交叉验证稳定性 |
| 稳定性等级 | 稳定 / 较稳定 / 不稳定 |
| 建议用途 | 预警 / 审批红线 / 参考 |

**LLM JSON 节点**（供 `risk_export_report` 合并）：
```json
{
  "rules": [
    {
      "segment": "制造业",
      "rule": "资产负债率 > 0.75 且 利息覆盖倍数 < 2.0",
      "coverage": 0.08,
      "bad_rate": 0.32,
      "lift": 3.4,
      "stability": "稳定",
      "suggestion": "预警规则"
    }
  ]
}
```
