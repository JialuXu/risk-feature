# `run` —— 全流程便捷组合（generic / credit / gsfc）

generic 内部串 `prepare → analyze → export`；credit/gsfc 转发既有黑盒链路。

## 全流程 generic（最常用）

```bash
# 沙盒/安装模式：先 export RISK_PROJECT_ROOT / RISK_OUTPUT_ROOT（见 paths-env.md），
# 且 --wide / --bad-customer 建议传绝对路径（相对路径按 CWD 解析，不按项目根）
python -m risk_pipeline run --pipeline generic \
  --wide data/raw/<宽表>.csv \
  --bad-customer data/raw/<坏客户清单>.csv \
  --id-col 客户编号 --target-col is_bad \
  --project <项目名> \
  --confirmed-new-dataset      # 首次跑该数据集时必带（阻断节点 1，见 blocking-gates.md）
```

## 带规则挖掘的一把梭（推荐，供 visualize 出规则/组合图）

```bash
python -m risk_pipeline run --pipeline generic \
  --wide data/raw/<宽表>.csv \
  --bad-customer data/raw/<坏客户清单>.csv \
  --id-col 客户编号 --target-col is_bad \
  --project <项目名> \
  --steps univariate,iv,lr,rules \
  --confirmed-new-dataset

# 出图（可视化是独立 Level-1-后步骤，不在 run 中）
python -m risk_pipeline visualize --project <项目名>
```

`--steps` 缺省时 generic 兜底 `univariate,iv,lr,rules`（全跑含规则）。

## credit / gsfc 主题（数据路径走 config/ 默认）

```bash
python -m risk_pipeline run --pipeline credit
python -m risk_pipeline run --pipeline gsfc --steps data_prep,iv
```

## 复杂 filter / exclude 用 JSON 文件（避免 shell 转义）

`--filter-file / --exclude-features-file / --bad-id-col` 与 C15 拆分确认三件套
（`--confirmed-id-col / --confirmed-target-col / --confirmed-target-positive`）
都可直接传给 run，不必拆三步：

```bash
echo '{"企业规模": {"exclude": ["0"]}}' > /tmp/filter.json
echo '["授信总金额", "表内授信余额"]' > /tmp/exclude.json
python -m risk_pipeline run --pipeline generic \
  --wide data/raw/<宽表>.csv --bad-customer data/raw/<坏客户清单>.csv \
  --id-col 客户编号 --target-col is_bad --project <项目名> \
  --filter-file /tmp/filter.json \
  --exclude-features-file /tmp/exclude.json \
  --confirmed-new-dataset
```

## 何时不用 run 一把梭，改拆三步（prepare→analyze→export）

- 想在 analyze 后人工核对 `_intermediate/` 里的 IV/LR 中间结果再决定是否 export
- 想换不同 `--category-dims` / `--qual-dims` 反复 analyze（数据已 prepare 过）
- prepare 阶段 filter 复杂，需要分阶段调试

## 雷区

- `run --pipeline credit/gsfc` **不可中段独立调用**（state.json 黑盒一项）；
  不接受 `--wide` 等 generic 参数；`--steps` 不含 `export` 时不推进 Level 1。
- `--category-dims` 仅 generic 生效；credit/gsfc 用预置维度，传了会告警忽略。
