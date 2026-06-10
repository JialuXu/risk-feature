---
name: step5_registration
description: 流水线第 5 步.读 validated.json + shadow_iv_response.json, 合并 shadow IV → 重算 priority → 写人审 review packet → 等闸口 2 → 元表 SCD2 写入 + CSV 快照 + 加工需求 docx 交付.
---

## 前置条件

- Step 4 已跑过, `shadow_iv_request.json` 与 `sql_skeletons/` 已生成
- 数仓 (或测试 fixture) 已把 `shadow_iv_response.json` 放到 `data/processed/{batch}/` 下
   - 若未放,流水线降级: 全部以 PENDING_DATAWAREHOUSE 状态注册, priority 暂不重算

## 触发语

- "step 5 / register / 注册到元表"

## 流程

```
validated.json + shadow_iv_response.json (可选)
    ↓
ingest_response.merge_response_into_proposals()  →  validated_with_shadow.json
ingest_response.assign_priority_from_shadow()    →  priority 重算
    ↓
prepare_review_packet.render_review_md()         →  step5_review.md
write_review_packet                              →  data/processed/{batch}/step5_review.md
    ↓
[闸口 2: 等 STEP5_APPROVED 文件]
    ↓
scd2_writer.register_proposals()                 →  写 SQLite + CSV 快照
                                                     audit.log
    ↓
export_delivery_doc:
  - 衍生指标设计稿.md
  - 衍生指标设计稿.csv
  - 加工需求文档.docx
    → output/{batch_id}/
```

## 入口

```bash
python -m indicator_pipeline --step 5 --batch-id 20260428_first
```

## SCD2 写入规则

详见 `indicator_pipeline/meta_store.py`. 简版:

| 情形 | 动作 |
|---|---|
| ind_code 未注册 | INSERT, ind_version=1 |
| ind_code 已存在, **业务字段**有变 | 旧版 exp_dt 关闭, 新版 ind_version+1 |
| ind_code 已存在, 仅 IV/priority 变化 | 软更新, 不开新版本 (追加 iv_history) |
| shadow_iv_status='FAIL' / 'SQL_ERROR' | 跳过, 不注册 |
| shadow_iv_status='PENDING_DATAWAREHOUSE' | 注册 (lifecycle_status=ACTIVE 但 priority 保持 P3-观察) |

## 闸口 2

详见 `REVIEW_GATE.md`.

## 失败处理

- 写入冲突: SQLite 事务回滚, 失败明细写 `data/processed/{batch}/ERROR_step5.json`
- 部分失败: 已成功的保留, 失败的进 errors 列表

## 职责边界

| 负责 | 不负责 |
|---|---|
| shadow IV 合并 + priority 重算 | shadow IV 计算 (step 4 + 数仓) |
| 元表 SCD2 写入 + CSV 快照 | Hive DDL / 物理迁移 |
| 加工需求 docx 导出 | 评审决策 (人审者负责) |
