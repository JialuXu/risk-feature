---
name: risk_trigger_extraction
description: 逆向提取风险特征触碰客户清单：基于已筛选的有效风险特征（IV可信、中等以上预测能力），从宽表中判断每个客户是否触碰风险阈值；产出客户触碰宽表、触碰长表、阈值说明表，并给出IV加权风险得分排名
---

## 方法论前提

- **输入**：已完成特征工程的宽表（需含 `is_bad` 目标列）；风险特征配置列表（`RISK_FEATURES`，含 IV、风险方向、可选显式阈值）。
- **产出对象**：
  1. `{project}_风险触碰明细_宽表.csv` — 每行一个客户，含各特征值、触碰标记（0/1）、触碰特征总数、IV加权风险得分、触碰特征清单
  2. `{project}_风险触碰明细_长表.csv` — 仅保留触碰的 客户×特征 记录，含阈值、来源、特征类别
  3. `{project}_触碰阈值说明.csv` — 每个特征的触碰条件、好/坏客户均值、阈值来源

- **非产出**：不重新跑 IV/LR/单变量分析，不替代 `risk_iv_diagnosis` 或 `risk_logistic_regression`。

## 阈值策略

优先级从高到低：

1. **显式阈值**（`explicit_threshold` 字段）：报告中业务专家明确给出，直接使用（如 `本行授信使用率 > 70%`）
2. **坏客户均值**：以坏客户均值水平作为触碰线——只要客户的表现至少与坏客户平均水平一样差，才算触碰。保守且有风控意义。
3. **兜底**：好/坏样本不足时用全量中位数，附注来源说明。

## IV 加权风险得分

```
得分 = Σ(触碰_i × IV_i) / Σ(IV_i) × 100
```

- 高 IV 特征被触碰时贡献更大权重
- 腰部企业专项特征使用 `iv_waist` 参与加权（仅当 `scope='waist'` 且客户属于腰部企业时触发）
- 结果按得分降序排列，便于直接识别高风险客户

## 流水线位置

- **前置**：`risk_data_prep`（宽表构建）+ `risk_feature_engineering`（衍生特征生成）
- **独立使用**：可直接对任何已有宽表运行（不依赖 `risk_iv_diagnosis` / `risk_logistic_regression` 的输出）
- **与 `risk_export_report` 的关系**：并行关系，触碰提取结果是对分析结论的业务落地，不写入八文件体系

## 何时使用

- 分析已经完成，需要"把风险信号落到每个客户头上"
- 需要给客户经理一份**可操作的风险预警名单**
- 需要对存量客户做**批量风险扫描**（触碰了哪些特征、得分多少）
- 需要验证报告结论的**区分度**（坏客户触碰率应显著高于好客户）

## 调用入口

```python
# 推荐用法：先用 prepare_df 准备宽表，再调用 extract_triggers
from risk_data_prep.scripts.prepare_df import prepare_df
from risk_trigger_extraction.scripts.trigger_extraction import extract_triggers

df, feature_cols = prepare_df(
    wide_path='data/raw/...csv',
    bad_customer_path='data/raw/坏客户标记.csv',
)

df_wide, df_long, df_threshold = extract_triggers(
    df=df,
    project_name='征信触碰分析',
)
```

```python
# 高级用法：传入自定义特征配置列表
from risk_trigger_extraction.scripts.trigger_extraction import extract_triggers

MY_FEATURES = [
    {
        'report_name': '资产负债率',
        'source_col': '资产负债率',
        'risk_direction': 'positive',
        'iv': 0.35,
        'category': '偿债能力',
        'explicit_threshold': ('>', 0.75),  # 可选，优先于数据计算
        'scope': 'full',
    },
    ...
]

df_wide, df_long, df_threshold = extract_triggers(
    df=df,
    features=MY_FEATURES,
    target_col='is_bad',
    id_col='客户编号',
    project_name='自定义触碰',
    output_dir='output/',
)
```

```python
# 仅使用核心计算函数（不落盘）
from risk_trigger_extraction.scripts.trigger_extraction import (
    compute_thresholds, evaluate_triggers, build_threshold_table
)
from risk_trigger_extraction.scripts.config import RISK_FEATURES

thresholds = compute_thresholds(df, RISK_FEATURES)
df_wide, df_long = evaluate_triggers(df, RISK_FEATURES, thresholds)
df_thr = build_threshold_table(RISK_FEATURES, thresholds)
```

## 输出列说明（宽表）

| 列名 | 说明 |
|------|------|
| `{特征名称}_值` | 该特征的原始值 |
| `{特征名称}_触碰` | 1=触碰，0=未触碰，NaN=数据缺失 |
| `触碰特征总数` | 触碰的特征数量 |
| `IV加权风险得分` | 0-100，越高风险越大 |
| `触碰特征清单` | 触碰特征名称（分号分隔） |
| `触碰数_{类别前缀}` | 各业务类别下的触碰数 |

## 职责边界

| 负责 | 不负责 |
|------|--------|
| 阈值计算（显式/数据驱动） | 特征工程（见 `risk_feature_engineering`） |
| 客户级触碰评估与 IV 加权得分 | IV/LR 分析（见对应 Skill） |
| 三张 CSV 落盘 | 八文件标准导出（见 `risk_export_report`） |
| 触碰统计摘要打印 | DOCX 报告（见 `risk_docx_report`） |
