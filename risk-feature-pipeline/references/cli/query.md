# `query` —— 读已有结果的唯一合法入口（只读，不改 level）

```bash
# 全量 IV top 15
python -m risk_pipeline query --project <项目名> --kind iv --top 15

# 分群 LR 正向系数 top 15
python -m risk_pipeline query --project <项目名> \
  --kind lr --dim 企业规模 --group 小型企业 --top 15 --sign positive

# 分群相关性 top 15
python -m risk_pipeline query --project <项目名> \
  --kind corr --dim 企业规模 --group 小型企业 --top 15

# 输出格式：table（默认）/ csv / json
python -m risk_pipeline query --project <项目名> --kind iv --top 15 --output-format csv
```

`--kind`：`iv`（全量 IV）/ `iv_group`（分群 IV）/ `corr` / `lr`。

**速查捷径**：横向对比同一特征在多个分群下的 IV，直接读 `_IV值透视表.csv`
（行=分群名称，列=特征，值=IV），比反复传 `--dim/--group` 更快：

```bash
head -1 data/results/<项目名>/<项目名>_IV值透视表.csv | tr ',' '\n' | head -20
```

## 雷区

- 读的是**磁盘快照**——上游重跑后不重新 export，查到的是旧结果。
- `--sign positive` 在坏客户定义反转的项目中方向反转。
- `--kind iv` 走全量表，不接受 `--dim/--group`（会告警忽略）；分群 IV 用 `--kind iv_group`。
