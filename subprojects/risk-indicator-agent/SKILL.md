---
name: risk-indicator-agent
description: LLM 指标衍生 Agent 流水线（5 步）。把 risk-feature-pipeline 的 IV/LR 挖掘结果翻译成符合元表 schema 的衍生指标提案，经 2 个人审闸口后写入本地元表（SQLite + CSV）。每步是独立子 Skill，人工 CLI 触发。
---

## 触发语

- "把挖掘结果转成衍生指标设计稿"
- "跑指标衍生 agent / LLM 提案"
- "新指标提案 / 注册到元表"
- "出加工需求文档（数仓接力）"

## 5 步路由

| Step | 子 Skill | 是否调 LLM | 输入 | 输出 |
|---|---|---|---|---|
| ① | `step1_candidate_screening` | 否 | risk-feature-pipeline 的 results/ + 元表 + 表字段清单 | `data/processed/{batch}/seeds.json` |
| ② | `step2_llm_proposal` | **是** | seeds + domain prompt + 元表摘要 | `proposals_draft.json` |
| ③ | `step3_validation` | 部分（语义关） | proposals_draft + 元表 | `validation_report.md` + `validated.json` |
| 闸口 1 | — | — | validation_report | 等 `data/processed/{batch}/APPROVED` |
| ④ | `step4_shadow_iv` | 否 | validated | `shadow_iv_request.json` + `sql_skeleton.sql`（给数仓） |
| — | 数仓侧 | 否 | request | `shadow_iv_response.json`（手工放回） |
| 闸口 2 | — | — | response | 等 `APPROVED` |
| ⑤ | `step5_registration` | 否 | response + validated | SQLite SCD2 + CSV 快照 + delivery docx |

## 入口（CLI）

```bash
cd /Volumes/Xujl/Skill/risk-indicator-agent
pip install -e .
cp .env.example .env  # 填 ANTHROPIC_API_KEY

# 一次性 batch：5 步顺序
BATCH=20260428_first
python -m indicator_pipeline --step 1 --batch-id $BATCH
python -m indicator_pipeline --step 2 --batch-id $BATCH
python -m indicator_pipeline --step 3 --batch-id $BATCH
# Step 3 写 review packet → 人工审 → touch APPROVED
touch data/processed/$BATCH/APPROVED
python -m indicator_pipeline --step 4 --batch-id $BATCH
# 数仓回填 shadow_iv_response.json → 人工审 → touch APPROVED
touch data/processed/$BATCH/STEP5_APPROVED
python -m indicator_pipeline --step 5 --batch-id $BATCH
```

## 关键原则（详见 AGENTS.md）

1. **不写 ETL / Hive DDL**：流水线的产物是设计稿 + 工单 JSON + SQL 骨架（参考），数仓拿过去自己翻
2. **不动 risk-feature-pipeline**：单向只读引用
3. **元表 SCD2**：所有写入都开新版本，旧版关闭拉链；不允许原地覆盖业务字段
4. **2 个人审闸口必须过**：sentinel 文件机制，不可绕过
5. **LLM 输出严格 JSON**：违 schema 直接 reject，不让劣质提案污染元表

## 与 risk-feature-pipeline 的关系

- **上游**：消费 `risk-feature-pipeline/data/results/{project}/` 的 IV/LR/相关性 CSV
- **下游**：本 skill 写入元表后，下次 `risk-feature-pipeline` 重跑时把 P3-观察 指标加入 `feature_cols` 验证；IV 结果回写到元表 `iv_history`，触发优先级升降

## 职责边界

| 负责 | 不负责 |
|---|---|
| 从挖掘结果到提案的"翻译" | 跑 IV/LR（见 risk-feature-pipeline） |
| 元表 SCD2 注册（本地起步） | 实际 Hive DDL / 调度 / ETL（数仓团队） |
| 指标命名规范、口径校验、去重 | 阈值评估（见 risk_trigger_extraction） |
| 工单生成（给数仓） | SQL 执行与影子计算 |
| 人审闸口编排 | 风控合规决策（人审者负责） |
