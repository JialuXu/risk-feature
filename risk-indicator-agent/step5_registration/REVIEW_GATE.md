# Step 5 评审闸口（人审介入点 2）

## 触发时机

shadow IV 回填 + priority 重算后, 流水线**写一份评审包并暂停**, 等你审完才写元表.

## 评审包位置

```
data/processed/{batch_id}/
├── step5_review.md                 # 主文档
├── validated_with_shadow.json      # 即将注册的提案 (含 shadow IV 字段)
└── shadow_iv_response.json         # 数仓回填 (若已就绪)
```

## 怎么审

打开 `step5_review.md`, 重点确认:

1. shadow IV 是否符合预期 (与 step 1 的 current_iv 偏差大小)
2. priority 重算结果是否合理 (P0 / P0-阻塞 / P1 等)
3. shadow_iv_status 异常的提案 (FAIL / SQL_ERROR / DATA_INSUFFICIENT) 已自动跳过

## 通过

```bash
cd <仓库根>/risk-indicator-agent
touch data/processed/{batch_id}/STEP5_APPROVED
```

写元表后,产出在 `output/{batch_id}/` 下:
- `衍生指标设计稿.md`
- `衍生指标设计稿.csv`
- `加工需求文档.docx`

## 拒绝

```bash
touch data/processed/{batch_id}/STEP5_REJECTED
```

不写元表, 流水线退出. 不影响 SQLite (无任何变更).
