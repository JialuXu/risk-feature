---
name: step4_shadow_iv
description: 流水线第 4 步.把 validated 提案打包成给数仓 sandbox 的工单 (shadow_iv_request.json + 每条指标的 SQL 骨架),不在本地执行 SQL.等数仓回填 shadow_iv_response.json 后由 ingest_response 合并到提案,更新 current_iv / iv_history.
---

## 前置条件

- Step 3 已通过人审闸口 1, `validated.json` 存在
- `data/processed/{batch}/APPROVED` sentinel 文件存在

## 触发语

- "step 4 / 出工单 / shadow IV"
- "把 validated 提案给数仓"

## 流程

```
validated.json
   ↓
build_request.build_request_payload()  →  shadow_iv_request.json
build_request.render_sql_skeletons()    →  sql_skeletons/{ind_code}.sql (每条一个文件)
   ↓
[人工把 shadow_iv_request.json + sql_skeletons/ 发给数仓]
[数仓 sandbox 跑 SQL → 回填 shadow_iv_response.json 到 batch 目录]
   ↓
ingest_response.load_response()         →  schema 校验
ingest_response.merge_response_into_proposals()
                                        →  validated_with_shadow.json (current_iv 已更新)
ingest_response.assign_priority_from_shadow()
                                        →  各提案 priority 按 shadow IV 重算
```

## 入口

```bash
# 第 1 阶段: 出工单
python -m indicator_pipeline --step 4 --batch-id 20260428_first

# 第 2 阶段: 数仓回填后再跑一次 (会检测 shadow_iv_response.json 是否存在)
# (实际是 step 5 启动时会读取 shadow_iv_response.json)
```

## 工单格式

详见 `contracts/shadow_iv_request_schema.json`. 关键字段:

- `indicators[].calc_logic_pseudo` —— 给数仓翻 SQL 的伪式
- `indicators[].source_tables / source_fields` —— 依赖
- `indicators[].sql_skeleton_hint_path` —— 配套的 SQL 骨架文件
- `indicators[].expected_iv_range` —— 给数仓的期望 IV 区间 (用于 sanity check)

## 数仓回填格式

详见 `contracts/shadow_iv_response_schema.json`. 必填:

- `results[].ind_code` —— 对应工单
- `results[].shadow_iv_status` —— SUCCESS / FAIL / PENDING_DATAWAREHOUSE / DATA_INSUFFICIENT / SQL_ERROR
- 状态=SUCCESS 时填 `shadow_iv / shadow_coverage_rate / shadow_credibility / shadow_sample_size`

## 失败/降级

- 数仓未回填: 流水线超时(默认 7 天) → 各提案 `shadow_iv_status='PENDING_DATAWAREHOUSE'`,可继续进 Step 5 (priority 保持 DRAFT)
- 数仓回填 SQL_ERROR: 该提案 reject, 不进 Step 5

## 职责边界

| 负责 | 不负责 |
|---|---|
| 工单 + SQL 骨架生成 | 实际 SQL 执行 (数仓做) |
| 回填合并 + 优先级重算 | IV 计算逻辑 (数仓侧) |
| 与数仓的契约维护 | 调度 / 监控 (数仓侧) |
