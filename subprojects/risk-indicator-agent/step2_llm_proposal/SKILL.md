---
name: step2_llm_proposal
description: 流水线第 2 步.读 seeds.json + 域 prompt + 元表已注册指标 + 基础表字段字典, 调 LLM 输出符合元表 schema 的指标提案 JSON 数组. 严格 JSON 解析,不通过则退回失败.
---

## 前置条件

- Step 1 已跑过, `data/processed/{batch}/seeds.json` 存在
- `.env` 中已填 `ANTHROPIC_API_KEY` (或对应 provider key)
- `prompts/` 下 4 个域上下文 + system + user 模板齐全

## 触发语

- "step 2 / LLM 提案 / propose"
- "把 seeds 跑成提案"

## 入口

```bash
python -m indicator_pipeline --step 2 --batch-id 20260428_first
```

## 处理流程

```
seeds.json (按 domain 分桶)
    ↓
对每个 domain:
    分批 (默认 5 条 seed/批)
        ↓
    context_builder.build():
        + system prompt + meta schema 摘要
        + domain 上下文 (FIN/CRDTC/OPN/PUB)
        + 该域已注册指标摘要 (top 30 by IV) — 给 LLM 去重参考
        + 该域基础表字段子集
        ↓
    llm_call.call():
        anthropic.messages.create(...)
        严格 JSON 解析, 失败重试一次
        ↓
    post_process.normalize():
        + 必填字段补默认 (eff_dt=今天/exp_dt=9999/proposer=LLM_AGENT/lifecycle_status=DRAFT)
        + 合并入 proposals
↓
data/processed/{batch_id}/proposals_draft.json
```

## 输出 (proposals_draft.json)

```json
{
  "batch_id": "...",
  "generated_at": "...",
  "stats": {
    "input_seeds": 776,
    "output_proposals": 220,
    "by_domain": {"FIN": 80, "CRDTC": 24, "OPN": 50, "PUB": 66},
    "llm_calls": 30,
    "llm_token_usage": {...}
  },
  "proposals": [
    {  // 完整 40 字段元表 schema
      "ind_code": "CRDTC_M_GUARQRY_UNPAYOFF_SNAP_RATIO",
      "ind_version": 1,
      "ind_name_cn": "担保查询未结清比",
      "domain": "CRDTC",
      ...
    }
  ]
}
```

## 参数

| 配置项 | 默认 | 说明 |
|---|---|---|
| `step2.batch_size` | 5 | 每个 LLM 调用送几条 seed |
| `step2.max_proposals_per_batch` | 10 | 每批最多产出几条提案 |
| `llm.model` | claude-sonnet-4-5 | 模型 |
| `llm.temperature` | 0.2 | 温度 (低=稳定) |

## 失败处理

- LLM 网络/配额错误: tenacity 自动 3 次重试
- JSON 解析失败: 让 LLM 修一次; 仍失败 → 该批所有 seed 标 reject
- 失败明细写 `data/processed/{batch}/step2_failed_batches.json`

## 职责边界

| 负责 | 不负责 |
|---|---|
| 调 LLM 产生符合 schema 的提案 | 校验提案 (见 step 3) |
| 字段补默认值 | 命名/字段查重 (step 3 dedup 关) |
| 分批控制 + 重试 | 元表写入 (step 5) |
