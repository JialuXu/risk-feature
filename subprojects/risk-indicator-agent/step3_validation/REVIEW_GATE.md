# Step 3 评审闸口（人审介入点 1）

## 触发时机

Step 3 跑完 6 道关后, 如果有提案通过校验, 流水线**会写一份评审包并暂停**, 等你审完才进入 Step 4.

## 评审包位置

```
data/processed/{batch_id}/
├── step3_review.md          # 主文档,人审主要看这个
├── validated.json           # 通过的提案 (会进入 Step 4)
├── rejected.json            # 被拒的提案 + 原因
└── validation_report.json   # 详细的 6 道关结果矩阵
```

## 怎么审

打开 `step3_review.md`, 按段评估:

1. **概览**: 通过/拒绝比例; 拒绝率 > 50% 应该重做
2. **逐条审视**: 每条提案的 4 项 (ind_code / 中文名 / 业务口径 / calc_logic)
3. **关注 warnings**: 即使 passed,warnings 多的可能要修
4. **批准范围**: 全部 OK → 直接 APPROVED; 部分有问题 → 编辑 `validated.json` 删掉问题条目再 APPROVED

## 通过

```bash
cd subprojects/risk-indicator-agent   # 自仓库根
touch data/processed/{batch_id}/APPROVED
```

## 拒绝

```bash
touch data/processed/{batch_id}/REJECTED
# 流水线会写 ERROR_step3_rejected.json 并退出
```

## 默认超时

24 小时. 修改 `config/default.yaml` 的 `approval_gate.timeout_hours`.

## 调试 (跳过审批)

```bash
python -m indicator_pipeline --step 4 --batch-id X --auto-approve
```

仅供测试, 不要在生产中用.
