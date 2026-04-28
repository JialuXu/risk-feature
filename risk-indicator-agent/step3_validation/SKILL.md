---
name: step3_validation
description: 流水线第 3 步.对 Step 2 的 LLM 提案做 6 道校验关 (命名/schema/字段查存/去重/calc_logic/LLM 语义),输出 validated.json + rejected.json + step3_review.md.触发人审闸口 1.
---

## 前置条件

- Step 2 已跑过, `proposals_draft.json` 存在
- 元表已初始化 (空也行, 第一次运行会创建)
- `references/` 软链就绪 (字段查存关需要)

## 触发语

- "step 3 / validate / 校验提案"
- "看哪些提案被拒"

## 6 道校验关

| # | 关 | 类型 | 处理 |
|---|---|---|---|
| 1 | naming | 规则 (正则) | reject 不通过的 |
| 2 | schema | 规则 (jsonschema) | reject |
| 3 | field_existence | 规则 (字段字典) | warn 但不 reject (P0-阻塞 接受表缺失) |
| 4 | dedup (rapidfuzz) | 规则 | reject 文本重复 |
| 5 | calc_logic (sqlglot) | 规则 | reject 用了禁词;无法 parse 仅 warn |
| 6 | semantic_llm | LLM | reject 语义重复 |

各关串行. 任一关 **errors 非空 → reject**; warnings 累积但不 reject.

## 入口

```bash
python -m indicator_pipeline --step 3 --batch-id 20260428_first
```

## 输出文件

```
data/processed/{batch_id}/
├── validated.json              # 通过的提案 (送 step 4)
├── rejected.json               # 被拒的提案 + 失败原因
├── validation_report.json      # 详细矩阵: 每提案在每道关的结果
└── step3_review.md             # 给人审看的 markdown 摘要
```

## 闸口 1

校验完写完文件后, 流水线**等待 sentinel**:

- `data/processed/{batch_id}/APPROVED` → 进入 Step 4
- `data/processed/{batch_id}/REJECTED` → 退出
- 24h 无动作 → 超时报错

详见 `REVIEW_GATE.md`.

## 失败上报

任一关报硬错时, 写 `data/processed/{batch_id}/ERROR_step3.json`.

## 职责边界

| 负责 | 不负责 |
|---|---|
| 6 道关 + 闸口编排 | 修指标 (LLM 重新提案见 step 2) |
| 评审包写出 | 注册到元表 (见 step 5) |
| 拒绝率统计 + 失败明细 | 影子 IV (见 step 4) |
