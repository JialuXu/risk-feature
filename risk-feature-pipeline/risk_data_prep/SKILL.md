---
name: risk_data_prep
description: 风险特征宽表的数据准备：主实体多表合并、清洗、二分类标签打标与分群摸底（内置企业信贷场景脚本，可替换为任意主题宽表）
---

> **本步是 `prepare` / `run` 的数据入口。** agent 一律走 CLI：
> `python -m risk_pipeline prepare ...` 或 `python -m risk_pipeline run --pipeline generic ...`。
> **禁止**在 Bash 里手抄"读宽表 + merge 坏客户 + 筛特征列"——这正是 `prepare` 封装的事。
> 下方 Python `prepare_df` 仅供 notebook 调研 / 单测。

## 触发 → CLI

| 用户说 | 跑 |
|---|---|
| 给了宽表 + 坏客户清单，要打标分析 | `python -m risk_pipeline prepare --wide W.csv --bad-customer B.csv --id-col 客户编号 --target-col is_bad --project X --confirmed-new-dataset` |
| 自带宽表已含 `is_bad`，想直接全流程 | `python -m risk_pipeline run --pipeline generic --wide W.csv --id-col 客户编号 --target-col is_bad --project X --confirmed-new-dataset` |
| 宽表缺目标列 | 先要用户补坏客户清单，再用 `--bad-customer` 合并打标；**不得**擅自改无监督 |

> ⚠️ 首次跑新数据集**必须** `--confirmed-new-dataset`（阻断节点 1，见 `AGENTS.md` 五）。复杂 filter / 排除列走 `--filter-file *.json` / `--exclude-features-file *.json` 避免 shell 转义（模板见 `AGENTS.md` 六）。

## 这一步做什么

打 `is_bad` 标签 → 可选过滤 → 自动挑数值型非零方差特征列，产出 `(df, feature_cols)` 喂给下游。
分析粒度 = 一行一个主实体（客户/借据/账户，由业务定义）；必备稳定主键 + 二分类目标列（默认 `is_bad`）。
征信/工商/财务/司法/供应链等只是**主题示例**，同一套流程适用任意主题宽表。

## filter 规则键

| 键 | 含义 |
|---|---|
| `exclude` / `include` | 类别值列表（字符串比较） |
| `min` / `max` / `range: [lo,hi]` | 数值范围（自动 `pd.to_numeric`） |
| `drop_na: true` | 丢弃该列为空的行 |

CLI：`--filter-file filter.json`，内容如 `{"企业规模": {"exclude": ["0"]}, "资产负债率": {"max": 1.0, "drop_na": true}}`。

## 本 Skill 强制规范

- 分析总体以**主实体基准表**去重后的集合为准；侧表中落在该集合之外的行不纳入。
- 数值缺失填 0 仅适用「无该主题暴露」等业务可解释情形；类别缺失保留 NaN，不随意填充。换主题（如司法）须重判"无记录 vs 未知"是否仍适用填 0 并写明含义。
- 合并后必须打印：总样本、好/坏客户数、坏客户率；各源匹配条数与剔除说明。
- 金额字段先清洗 `-`、`,` 再转数值；侧表按主键去重取最新。
- 不在日志/示例输出客户姓名、证件号、手机号。

## 关键配置（`scripts/config.py`）

- 数据源（内置模板）：`DATA_CONFIG`、`CREDIT_CONFIG['data']`
- 征信宽表准备列：`CREDIT_CONFIG['credit_prep_amount_cols']`、`['credit_prep_object_keep_cols']`
- 财务侧表去重列：`FINANCE_MERGE_DUP_COLS`
- 授信分层/腰部企业：`CREDIT_BINS`、`CREDIT_LABELS`、`WAIST_*`、`WAIST_HIGH_RATINGS`
- 分群维度候选：`SEGMENT_DIMS`、`CREDIT_CONFIG['category_dims']`
- 样本门槛统一在 `SAMPLE_THRESHOLDS`，不在此重复

## 底层脚本（仅 notebook/单测，agent 走 CLI）

> `prepare_df`（宽表+打标+选列）已由 `prepare` / `run` CLI 封装；**agent 用上面的 CLI，不要在 Bash 里手抄合并**（`AGENTS.md` 一/三）。notebook 调研可 `from risk_data_prep.scripts.prepare_df import prepare_df`；多源合并参考实现见 `data_prep.prepare_credit_wide_table` / `wide_table_builder.build_wide_table`。

## 主要脚本映射

| 模块 | 作用 |
|------|------|
| `scripts/prepare_df.py` | ⭐ `prepare_df`（宽表+打标+选列一行合成） |
| `scripts/data_prep.py` | `load_credit_data`、`prepare_credit_wide_table` |
| `scripts/wide_table_builder.py` | `build_wide_table` |
| `scripts/io_utils.py` | `load_data`、`read_csv_auto_encoding` |
