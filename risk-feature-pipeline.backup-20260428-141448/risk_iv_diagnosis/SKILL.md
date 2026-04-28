---
name: risk_iv_diagnosis
description: IV 与可信度诊断：自适应分箱、WOE 截断、缺失分离、分群 IV、稳健性评级与可选 optbinning 阈值（适用于任意数值特征宽表）
---

## 方法论前提（与数据来源无关）

- **输入**：主实体粒度；二分类目标列（默认 `is_bad`）；用于 IV 的**数值或可分箱**特征列；可选类别/二值分群列（与 `risk_segment_univariate` 相同抽象）。
- **特征含义**：不限于征信；司法涉诉次数、执行金额占比、地理风险指数等均可作为 `feature_cols` 进入同一套 IV 流程。
- **输出**：IV 值、分箱元信息、可信度等级、分群 IV 与诊断告警，供导出与业务规则使用。

实现代码位于本目录 `scripts/`。

## 流水线位置

- **前置**：宽表与 `feature_cols`（来自 `risk_feature_engineering` 或自备）。
- **后置**：`risk_export_report` 将 IV 与可信度写入标准 CSV 与 LLM 结构；**IV>2 或不可信档位的业务采纳规则**以本 Skill 的统计定义为准，导出侧只执行呈现与过滤。
- **全局约定**：`MIN_SAMPLES`、`MIN_BAD_SAMPLES` 等取自 `scripts/config.py` 的 `SAMPLE_THRESHOLDS`；跳过须打印原因。

## 何时使用（触发）

- IV、WOE、分箱、分群 IV、IV 可信度、热力图/透视表数据源、optbinning 阈值探索。

## 职责边界

| 负责 | 不负责 |
|------|--------|
| `calc_iv`、自适应分箱、WOE 截断、缺失 IV 分离 | 宽表与特征构造（见前两个 Skill） |
| 全量/分群 IV、`reliability_diagnosis`、可选 `calc_feature_thresholds` | LR 与 AUC（见 `risk_logistic_regression`） |
| IV 可信度等级与「IV>2 过拟合嫌疑」语义 | 八文件命名与 LLM JSON 拼装（见 `risk_export_report`） |

## 调用入口（最小示例）

```python
from risk_iv_diagnosis.scripts.iv_analysis import calc_iv, _adaptive_bins
from risk_iv_diagnosis.scripts.iv_group_diagnosis import (
    iv_full_analysis,
    iv_by_group,
    iv_by_qualification,
    reliability_diagnosis,
)

bins = _adaptive_bins(n_samples, n_bad, default_bins=10)
iv_value, meta = calc_iv(df, feature, 'is_bad', bins=10)
iv_df = iv_full_analysis(df, feature_cols, target='is_bad')
iv_group = iv_by_group(df, '所属行业', feature_cols, target='is_bad')  # 分群列名示例
summary_df, dist_df, warnings = reliability_diagnosis(all_iv_df)
```

可选业务阈值：

```python
from risk_iv_diagnosis.scripts.iv_group_diagnosis import calc_feature_thresholds
```

## 关键配置（本步为主）

- `SAMPLE_THRESHOLDS`：`MIN_SAMPLES`、`MIN_BAD_SAMPLES`（与 IV 分群准入相关）。
- IV 稳健性相关：`IV_SUSPECT_THRESHOLD`、`WOE_CAP`、`ADAPTIVE_BINS_*`、`IV_THRESHOLD`（弱/中/强档），均以 `scripts/config.py` 为准。

## 方法与规范（本 Skill 专有）

- **自适应分箱**：小样本时降低箱数，避免坏为 0 的箱用 0.5 校正导致 IV 虚高；公式与默认箱数由 `_adaptive_bins` 实现。
- **WOE**：计算后截断至 `[-WOE_CAP, +WOE_CAP]`。
- **缺失**：缺失单独成箱，IV 贡献与非缺失部分分开统计与汇总。
- **可信度等级**：由 `_assess_iv_reliability` 实现（样本与 IV  magnitude 联合判断）；**IV 大于可疑阈值不得作为推荐特征**（与导出规范衔接）。
- **IV 预测力分档**：脚本按 `IV_THRESHOLD` 与可疑阈值标注「无/弱/中/强/过强/过拟合嫌疑」等。

## 主要脚本映射

| 模块 | 作用 |
|------|------|
| `scripts/iv_analysis.py` | `calc_iv`、`_adaptive_bins`、`_assess_iv_reliability`、`run_iv_analysis`（仓库内某一整表 IV 编排入口） |
| `scripts/iv_group_diagnosis.py` | 另一套全量/分群 IV 编排、`reliability_diagnosis`、`calc_feature_thresholds` |

## 输出形态（字段级）

- 全量 IV 表、分群 IV 明细、IV 可信度透视、诊断汇总与告警列表；可选 optbinning 阈值明细表。标准文件名与目录约定见 `risk_export_report`。
