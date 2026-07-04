# `prepare` —— 进数据的唯一合法入口（→ 前置态）

宽表 + 坏客户清单 → `data/processed/<project>/prepared.csv` + `features.json`。

```bash
python -m risk_pipeline prepare \
  --wide data/raw/<宽表>.csv \
  --bad-customer data/raw/<坏客户清单>.csv \
  --id-col 客户编号 --target-col is_bad \
  --project <项目名> \
  --confirmed-new-dataset      # 首次新数据集必带（阻断节点 1，见 blocking-gates.md）
```

- 复杂 filter / 排除特征走 JSON 文件（模板见 cli/run.md 同名段落），
  flag：`--filter-file` / `--exclude-features-file` / `--bad-id-col`。
- 补充维度表（分群维度在另一张 CSV）：`--merge-table <csv> [--merge-id-col ...] [--merge-cols a,b]`。
- 拆分版确认（留审计痕迹）：`--confirmed-id-col/--confirmed-target-col/--confirmed-target-positive` 三件套。

## 雷区

- `--id-col` / `--target-col` 传错会静默通过但目标列语义错误——阻断节点 1 就是为此设的，认真核对。
- `--filter-file` 的 `exclude` / `include` 逻辑相反，别混。
- 列名预检：`column_mapping.yaml` 的分群维度在宽表 0% 命中时 CLI 直接 exit 1 并列出实际列；
  处理：改 YAML 重跑（最常用）/ analyze 传 `--category-dims` / 有意全样本加 `--skip-preflight`。
- 主键契约：prepared.csv 读写强制主键 str（保前导零），源头读也已锁——不要绕过 CLI 手写合并。
