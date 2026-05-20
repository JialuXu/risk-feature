---
name: risk_segment_univariate
description: 分群摸底与单变量风险分析：类别维度统计、二值标签对比、点二列相关、T 检验与跨分群差异（与特征主题无关）
---

## 方法论前提（与数据来源无关）

- **输入**：主实体粒度宽表；二分类目标列（脚本默认 `is_bad`）；数值型 `feature_cols`；一个或多个**类别型分群列**（如行业、地区、案件类型等），以及可选的**二值标签列**（本仓库常用 `是_` 前缀，你也可使用任意 0/1 列并在调用时传入 `qual_dims`）。
- **不关心特征来自何种主题**：司法、征信、财务或混合宽表，只要列类型与含义满足统计前提即可。
- **输出**：各分群内样本/坏率、相关矩阵、检验结果、跨分群离散度，供业务解读与下游 `compare_corr_lr` 使用。

实现代码位于本目录 `scripts/`。

## 流水线位置

- **前置**：宽表、目标列、分群列、`feature_cols`（来自 `risk_feature_engineering` 或自备）。
- **后置**：`risk_logistic_regression` 中 `compare_corr_lr` 等可消费本步相关系数结果；`risk_export_report` 可汇总导出。
- **全局约定**：与分群相关的**最小样本**等阈值以 `scripts/config.py` 的 `SAMPLE_THRESHOLDS` 为准；凡跳过须打印原因（全流水线一致，此处不展开）。

## 何时使用（触发）

- 任意业务维度上的样本概况、坏率对比、单特征与目标列的相关与 T 检验、跨分群特征稳定性。

## 职责边界

| 负责 | 不负责 |
|------|--------|
| `detect_dims`、`segment_stats`、`qualification_stats` | IV、WOE、分箱（见 `risk_iv_diagnosis`） |
| `univariate_by_group`、`univariate_by_qualification`、`cross_group_variance` | 多变量 LR 与 AUC（见 `risk_logistic_regression`） |

## 调用入口（最小示例）

```python
from risk_segment_univariate.scripts.segment_univariate import (
    detect_dims,
    segment_stats,
    qualification_stats,
    univariate_by_group,
    univariate_by_qualification,
    cross_group_variance,
)

category_dims, qual_dims = detect_dims(df)
stats_df = segment_stats(df, '所属行业', min_group_size=50)  # 列名示例，可改为司法案由/地域等
qual_df, pivot = qualification_stats(df, qual_dims)
corr_df, diff_df, pval_df, meta_df, skipped = univariate_by_group(
    df, '所属行业', feature_cols, min_bad=15, min_good=30, min_group_size=50
)
```

## 本步专用门槛（与 config 对应关系）

以下名称均对应 `SAMPLE_THRESHOLDS` 中的常量，**具体数值以配置文件为准**：

- 分群进入统计/单变量：`MIN_SAMPLES`（分群总样本）。
- 点二列相关与 T 检验：`MIN_BAD_CORR`、`MIN_GOOD_CORR`。

## 本 Skill 强制规范

- 每条相关/T 检验结果须能关联到**分群元信息**（`n_total`、`n_bad`、坏率等，由 `meta_df` 或脚本约定列给出）。
- 跳过某分群时须在日志逐条说明原因（与项目 CLAUDE 规则一致）。
- 不在输出中展示敏感标识类字段。

## 主要脚本映射

| 模块 | 作用 |
|------|------|
| `scripts/segment_univariate.py` | 分群检测、统计、单变量、跨分群方差 |
| `scripts/univariate.py` | `calc_correlation_pvalue`、`ttest_good_bad` 等底层计算 |
| `scripts/boxplot.py` | 单变量步骤的箱形图副产物：好/坏对比 + 分群对比 |

## 副产物：箱形图（顺手出图）

跑 `'univariate'` 步骤时链路会自动调用 `boxplot.generate_boxplots_for_univariate(...)`，
渲染失败不影响主流程。生成的 PNG 落在 `output/<project>/charts/boxplots/`：

| 文件名 | 朝向 | 业务用法 |
|---|---|---|
| `box_good_bad_grid_top<N>.png` | 全样本 "好/坏" 并排（top-N 特征做小多图） | 一图扫一遍哪些指标真的能把好坏分开（中位数 + IQR，免被极值欺骗） |
| `box_by_<dim>_grid_top<N>.png` | X=分群值，每个分群内并排 "好/坏"（每个分群维度一张） | 看指标分布是否随分群漂移、好坏可分性是否随分群退化 |

**为什么不放在 `risk_visualization`**：箱形图需要原始数值分布，
而 `risk_visualization` 是只读 CSV 摘要的路径。把这两类图绑在 `univariate` 步骤后，
链路自然在 `df` 还在内存里时把图出完，无须落 parquet 中转。

**特征排序口径**：全样本按 `|点二列相关系数|` 与 `target` 排序后取 top-N（默认 12）。
样本数 < 30 或常数列自动跳过；尾部按 0.5%/99.5% 分位裁剪以免极值把箱压成线段。
