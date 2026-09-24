---
name: risk_rule_mining
description: 决策树规则挖掘：从宽表产出可读风险规则（非建模），用于预警策略、审批规则与贷后触发条件设计；规则在训练集挖掘、在留出集评估 Lift/稳定性。当用户说"规则挖掘"、"预警规则"、"审批规则/红线"、"特征组合规则"时触发（CLI `analyze --steps ...,rules`）。
---

> **何时读我**：只有需要决策树规则挖掘算法细节时才读本文件；常规规则挖掘在 analyze 带 `--steps ...,rules`（见 `references/cli/analyze.md`）。

> **本步是 `analyze` 的可选步骤，agent 不单独跑它。** 用 CLI：
> `python -m risk_pipeline analyze --project X --steps univariate,iv,lr,rules --category-dims <dim>` 然后 `export`
> （或一把梭 `run --pipeline generic --steps univariate,iv,lr,rules …`）。
> rules 步骤拟合树并把 pkl 落 `_intermediate/`，**`export` 才会把规则表写到 `data/results/<project>/<project>_风险规则表.csv`**。
> ⚠️ `--steps rules` 单跑时 `--category-dims` 必须是前置 analyze 已用维度的**子集**（否则与 `_intermediate/` 错位，CLI 直接 exit）。

## 何时用（贷后预警/审批规则的核心引擎）

- 要产出**业务规则清单 / 预警触发条件 / 审批红线 / 贷后检查项**
- 要识别**特征交互效应**（IV 单变量、LR 加性都识别不了的组合信号，如"高杠杆 + 短借款期限"）
- 要**替代或验证人工分群维度**（树分裂可能揭示更优切分）

## 与 `risk_threshold_explore` 怎么选

| | risk_rule_mining | risk_threshold_explore |
|---|---|---|
| 输入 | 全特征自动喂决策树 | 手工挑好的 (分群,特征) 清单 |
| 方法 | 决策树 max_depth=3，**多变量 AND** | optbinning **单变量**最优切点 |
| 用途 | 自动发现交互规则 | 分析师候选规则评审 |

## 推荐输入特征集

IV ≥ `IV_THRESHOLD['medium']` 且可信度为"可信/参考"的特征；自动剔除 IV > `IV_SUSPECT_THRESHOLD` 的疑似数据穿越特征（避免树用噪声列分裂）。

## 关键配置（`risk_pipeline.config.RULE_MINING_CONFIG`）

| 参数 | 默认 | 作用 |
|------|------|------|
| `max_depth` | 3 | 树深，限制规则可读性 |
| `min_samples_leaf_ratio` | 0.05 | 叶子最少样本占比 |
| `min_bad_in_leaf` | 5 | 叶子最少坏客户数 |
| `min_coverage` | 0.01 | 规则最小覆盖率 |
| `min_lift` | 1.5 | 规则最小 Lift |
| `top_k_per_segment` | 10 | 每群保留 Top-K |
| `holdout_ratio` / `holdout_min_bad` | 0.3 / 10 | 留出测试集比例 / 测试集坏客户下限（不足则回退全量样本内评估） |
| `bootstrap_n` / `stability_min_valid_ratio` | 200 / 0.6 | 稳定性：测试集 bootstrap 次数 / 有效重抽样占比下限 |
| `class_weight` | balanced | 不平衡权重 |

样本准入沿用 `SAMPLE_THRESHOLDS`：`MIN_BAD_LR`(20)、`MIN_GOOD_LR`(50)。

## 方法要点

- **规则**：根→叶完整路径，即若干 `特征 op 阈值` 的合取（AND）
- **留出评估**：分层 70/30 切分，训练集挖树，覆盖率/坏账率/Lift/闸门/建议用途全部在测试集（样本外）上计算；坏客户不足时回退全量，`评估口径` 列标 `样本内`
- **缺失值**：挖掘用训练集中位数填补，评估与打分沿用同一组填补值
- **筛选**：叶坏账率 > 整体（Lift>1）且过 `min_coverage`/`min_lift`/`min_bad_in_leaf` 三闸门
- **排序**：先 Lift 降序，次覆盖率降序
- **稳定性**：测试集 bootstrap 重抽样，按有效占比与坏账率离散系数判 `稳定/较稳定/不稳定`
- **去重**：按 `(特征集合, 阈值四舍五入)` 去重
- **输出语言**：中文业务语言（如 `资产负债率 大于 0.75`）

## 输出

**`{项目名}_风险规则表.csv`** 关键列：`分群维度` / `分群名称` / `规则编号` / `规则条件` / `涉及特征` / `特征数量` / `覆盖样本数` / `覆盖率` / `覆盖坏客户数` / `坏账率` / `整体坏账率` / `Lift` / `训练集Lift` / `稳定性坏账率均值` / `稳定性坏账率标准差` / `稳定性有效次数` / `稳定性重抽样次数` / `稳定性等级` / `评估口径`（样本外 / 样本内） / `建议用途`（预警 / 审批红线 / 参考）。`Lift` 等指标为测试集口径，`训练集Lift` 仅供对照乐观偏差。
阈值精度按特征名自适应：比率类→2 位小数；金额类→整数+千分位；其它 `:.4g`。

> ⚠️ `export` 完成时若有 `稳定性等级=不稳定` 的规则，stdout 会列出前 5 条，并落到 `_audit.json` 的 `unstable_rules`。**不稳定规则不得直接写进政策，须附人工复核标注。**

> 注：规则**目前只落 CSV + `_audit.json`**，不并入 `_LLM报告数据.json`（`build_llm_rules_payload` 已实现但未接线）。

## 底层脚本（仅 notebook/单测，agent 走 CLI）

> 实现在本目录 `scripts/`，**仅供 notebook/单测/调试直接 import；agent 一律用上面的 `analyze --steps …,rules`**（`AGENTS.md` 三禁止在 Bash 里 import 模块手抄）。

## 主要脚本映射

| 模块 | 作用 |
|------|------|
| `scripts/rule_extraction.py` | 决策树拟合 + 路径→规则 + 去重 |
| `scripts/rule_evaluation.py` | 覆盖率、坏账率、Lift、置信区间 |
| `scripts/rule_stability.py` | K-fold 稳定性 |
| `scripts/rule_mining_pipeline.py` | 分群挖掘编排 + 导出 |
