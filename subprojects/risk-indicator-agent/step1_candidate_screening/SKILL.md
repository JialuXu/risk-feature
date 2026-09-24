---
name: step1_candidate_screening
description: 流水线第 1 步.从 risk-feature-pipeline 的 results/ 跨项目聚合 IV 结果, 排除过拟合/无法计算, 做信号分级, 输出 seeds.json 给 Step 2 用作 LLM 提案的输入.
---

## 前置条件

- `risk-feature-pipeline` 至少跑过一轮特征分析, `data/results/{project}/` 下有 8 张 CSV
- `config/local.yaml`（不入库）的 `upstream.results_dirs` 指向真实结果目录
- `references/` 下放好 `表清单.csv` / `表字段清单.csv`（不入库）

## 触发语

- "扫挖掘结果出 seed"
- "step 1 / candidate screening"
- "看哪些 IV 强但元表里没有"

## 入口

```bash
python -m indicator_pipeline --step 1 --batch-id 20260428_first
```

或 Python:
```python
from indicator_pipeline.config_loader import load
from step1_candidate_screening.scripts.run import run
run(batch_id="20260428_first", cfg=load())
```

## 处理流程

```
results_dirs (跨 project)  ─→ load_iv_results.aggregate_iv()
                                  │
                                  ▼
                         apply_filters.filter_iv()
              排除 IV可信度 ∈ {无法计算, 不可信-过拟合嫌疑}
              排除 IV >= 2.0  (硬阈值,过拟合)
                                  │
                                  ▼
                       seed_builder.build_seeds()
              · 跨项目去重(保留最大 IV)
              · 信号分级(强/中/弱/观察期)
              · domain 归口(按项目 → 域)
              · 与元表已有 ind_code 对照,标 "已注册" / "需提案"
                                  │
                                  ▼
                  data/processed/{batch_id}/seeds.json
```

## 输出 schema (seeds.json)

```json
{
  "batch_id": "20260428_first",
  "generated_at": "2026-04-28T15:00:00",
  "stats": {
    "total_features": 1085,
    "after_filter": 776,
    "already_registered": 40,
    "to_propose": 736,
    "by_domain": {"FIN": 357, "CRDTC": 24, "OPN": 84, "PUB": 311}
  },
  "seeds": [
    {
      "feature_name_cn": "担保查询未结清比",
      "source_project": "腰部企业征信分析",
      "domain": "CRDTC",
      "iv": 0.5604,
      "iv_credibility": "可信",
      "coverage_rate": 1.0,
      "signal_strength": "强",
      "risk_direction": "正向",
      "already_registered": false,
      "candidate_source": "mining_supplement"
    }
  ]
}
```

## 参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `iv_max` | 2.0 | 排除 IV >= 此值 |
| `exclude_credibility` | `[无法计算, 不可信-过拟合嫌疑]` | 排除的可信度 |
| `signal_thresholds.strong` | 0.10 | 强信号阈值 |
| `signal_thresholds.medium` | 0.05 | 中信号阈值 |
| `signal_thresholds.weak` | 0.02 | 弱信号阈值 |

## 职责边界

| 负责 | 不负责 |
|---|---|
| 跨项目聚合 IV | 重新计算 IV (见 risk_iv_diagnosis) |
| 信号分级 + domain 归口 | 写指标提案 (见 step 2) |
| 与元表对照标 "已注册" | 元表写入 (见 step 5) |
