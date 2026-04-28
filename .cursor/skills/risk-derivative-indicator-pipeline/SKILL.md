---
name: risk-derivative-indicator-pipeline
description: Generates and maintains credit risk derivative indicator pipelines from Hive field inventories, derivative templates, and rule-engine feedback. Use when the user asks to 自动生成衍生指标, 持续孵化指标, 生成候选指标池, 生成指标加工需求, or 适配统一风险引擎中台.
---

# Risk Derivative Indicator Pipeline

## 使用场景

当用户需要持续生成风险衍生指标时，使用本 Skill。它可以从原始 Hive 表字段清单初始化字段资产字典，再结合衍生模板和生成规则，自动产出候选指标池、评分清单、正式指标加工需求和规则中台适配清单。

默认输入目录：

`衍生指标设计/衍生指标持续孵化流水线/`

核心配置文件：

- `../基础指标（已落地）/表字段清单.csv`
- `字段资产字典.csv`
- `衍生模板库.csv`
- `候选指标生成规则.csv`

## 快速执行

在工作区根目录运行：

```bash
python .cursor/skills/risk-derivative-indicator-pipeline/scripts/generate_pipeline.py \
  --init-field-dict
```

这会先从原始 `表字段清单.csv` 生成：

- `字段资产字典_自动初始化.csv`

然后继续生成候选指标、正式需求和规则适配清单。

如只想初始化字段资产字典：

```bash
python .cursor/skills/risk-derivative-indicator-pipeline/scripts/generate_pipeline.py \
  --init-field-dict \
  --init-only
```

如已人工复核 `字段资产字典.csv`，可直接运行：

```bash
python .cursor/skills/risk-derivative-indicator-pipeline/scripts/generate_pipeline.py
```

默认输出到：

`衍生指标设计/衍生指标持续孵化流水线/auto_output/`

## 输出文件

脚本会生成：

- `候选指标池_自动生成.csv`
- `候选指标评分清单_自动生成.csv`
- `正式指标加工需求清单_自动生成.csv`
- `规则中台适配清单_自动生成.csv`
- `指标孵化闭环台账_自动生成.csv`

## 工作原则

1. 不直接让模型凭语义决定指标。
2. 原始入口优先使用 `表字段清单.csv`，自动初始化字段资产字典。
3. 人工复核字段资产字典后，再匹配衍生模板库生成候选指标。
4. 候选指标必须经过评分清单分层，才能进入正式加工需求。
5. 规则候选指标要同步生成统一风险引擎中台适配信息。

## 常用参数

```bash
python .cursor/skills/risk-derivative-indicator-pipeline/scripts/generate_pipeline.py \
  --init-field-dict \
  --source-schema "衍生指标设计/基础指标（已落地）/表字段清单.csv" \
  --config-dir "衍生指标设计/衍生指标持续孵化流水线" \
  --output-dir "衍生指标设计/衍生指标持续孵化流水线/auto_output" \
  --batch-id BATCH_001
```

## 人工复核点

生成后重点检查：

- 字段资产字典中的字段角色是否准确。
- 衍生模板是否匹配了合适字段。
- 跨表指标的关联键和时间字段是否一致。
- 规则候选是否具备明确比较符、阈值口径和观察期。
- 评分清单中“待计算”的指标是否需要接入真实历史样本进一步验证。
