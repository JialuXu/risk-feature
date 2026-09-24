# risk-indicator-agent · 硬规矩（AGENTS.md）

## 1. 必须先读

- `SKILL.md` — 5 步路由
- （以下 3 份为本地参考资料，不入库；本地没有则跳过）
- `references/工作链路-指标设计方法论.md` — 业务方法论
- `references/衍生指标层数据结构设计文档.md` §1.2 — 元表 40 字段
- `references/原始加工逻辑整合纪要.md` §3 — 4 个设计模式（动态展开/参考日期/空值/后处理）
- `config/meta_schema.yaml` — 单一事实源

## 2. 绝对禁止

- ❌ **直接修改 risk-feature-pipeline 的任何文件**（单向只读引用）
- ❌ **跳过任一人审闸口**（sentinel 文件不存在就不能进入下一步）
- ❌ **元表写入不开新 SCD2 版本**（业务字段变更必须 `ind_version+1`，旧版 `exp_dt` 关闭）
- ❌ **LLM 输出 JSON 不通过 schema 校验就入下一步**（校验关 #2 必过）
- ❌ **calc_logic 写可执行 SQL**（必须是伪式；可执行 SQL 由数仓在 Step 4 之后翻）
- ❌ **首版引入 embedding 依赖**（torch / sentence-transformers / openai embedding）
- ❌ **泄漏 ANTHROPIC_API_KEY 到日志或 review packet**

## 3. 必须做

### 3.1 命名规范（全部 ind_code）

```
^(FIN|CRDTC|OPN|PUB|JUDI|LON|GUAR|RELA|FUND)_[MDA]_[A-Z0-9_]+_(SNAP|M3|M6|M12|Y1|Y3|Y5|LIFE|EVT)?_(CNT|AMT|RATIO|FLG|IDX|STD|CV|AVG|MAX|MIN|DAYS)$
```

- 全大写、下划线分段
- 长度 ≤ 60 字符
- 跨域不允许重名

### 3.2 元表写入

- 必须走 `meta_store.write_scd2()`，不允许直接 SQL UPDATE
- 每次写入同时落 SQLite + CSV 快照（snapshots/indicator_meta_<dt>_<batch_id>.csv）
- 写 audit.log 记录 batch_id / who / 影响行数

### 3.3 LLM 调用

- 通过 `llm_client.generate(messages, response_schema)`
- 必须 retry（tenacity，3 次指数退避）
- JSON 严格解析失败 → 重试 1 次让 LLM 修；仍失败 → 该条 reject 并记录原因
- 不允许直接 `import anthropic` 在业务代码里

### 3.4 人审闸口（sentinel 文件机制）

```
data/processed/{batch_id}/
  step3_review.md       # agent 写
  APPROVED              # 人审通过 touch；agent 检测后续
  REJECTED              # 拒绝；agent 退出，不进入 Step 4
  step5_review.md
  STEP5_APPROVED
  STEP5_REJECTED
```

- 闸口检测：`approval_gate.wait_for_sentinel(batch_id, gate='step3' | 'step5')`
- 默认轮询间隔 5s，超时 24 小时（可配置）
- 自动化测试用 `auto_approve=True` fixture 跳过等待

### 3.5 与现有元表去重

- Step 3 dedup 关：rapidfuzz token_set_ratio 默认阈值 85（config 可调）
- 阈值以上 → reject（标 duplicate_of=xxx）
- 阈值以下 → pass

### 3.6 错误上报格式

任何 step 失败时写 `data/processed/{batch_id}/ERROR_step{N}.json`：

```json
{
  "batch_id": "...",
  "step": 3,
  "stage": "check_dedup",
  "error_type": "ValidationError",
  "error_msg": "...",
  "stack_trace": "...",
  "input_file": "data/processed/{batch_id}/proposals_draft.json",
  "occurred_at": "2026-04-28T14:30:00",
  "next_action": "修复后从 step3 继续 (--resume)"
}
```

## 4. 决策树（用户提问 → 走哪条路）

| 用户说 | 应该跑 |
|---|---|
| "用最新挖掘结果出指标提案" | step 1 → step 2 |
| "校验上次提案" | step 3 |
| "提交工单给数仓" | step 4 |
| "注册到元表" | step 5（前置闸口必须过） |
| "重跑某一步" | `--step N --resume`（保留历史 batch 数据） |
| "查元表" | `python -m indicator_pipeline meta query --domain CRDTC` |

## 5. 复用清单（不要重写）

- `risk_result_query.load_results` → Step 1 加载 IV
- `pandas` 读 CSV、utf-8-sig 编码 → io_utils 统一
- `sqlglot` 解析 calc_logic → 不要手写 SQL parser
- `rapidfuzz` 文本相似度 → 不要手写 Levenshtein

## 6. 失败重试策略

| 失败位置 | 策略 |
|---|---|
| LLM 调用 | tenacity 3 次指数退避（1s/2s/4s） |
| LLM JSON 解析 | 1 次重试（让 LLM 修） |
| 元表写入冲突 | SQLite 事务回滚，换 batch_id 重试 |
| 数仓 sandbox 回填超时 | 降级：record `shadow_iv_status='PENDING_DATAWAREHOUSE'`，跳过此条入 Step 5 |
| 人审闸口超时（24h） | 写 ERROR；不自动通过 |
