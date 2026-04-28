---
name: risk_data_extract
description: 从银行内部数据库（Hive 等）按口径导出风险分析所需的原始数据文件，作为 risk-feature-pipeline 的上游。仅产出可粘贴执行的 SQL 模板与导出后落盘 CSV 的 schema 校验，不直连数据库。
when_to_use: |
  以下情形触发本 Skill：
  - 用户说"取数"、"导出宽表"、"从 Hive 拉数据"、"准备原始数据"
  - 用户已经拿到银行的数据库表结构，需要生成 SQL 让 data team 或自己在 HUE / DBeaver 里跑
  - 用户想核对一份导出后的 CSV 是否满足下游分析管线的字段要求
  不触发本 Skill 的情形（请走 risk-feature-pipeline）：
  - 用户已经有 CSV，要做特征工程 / IV / LR / 报告
  - 用户问"分析结果"、"top N 特征"、"分群表现"
---

# risk_data_extract — 行内数据导出 Skill（占位草稿）

> ⚠️ **本文件为骨架草稿**。具体的表名、字段、口径将根据银行内的数据结构设计后再补全。
> 完成度: 0%（仅边界与契约已定）

---

## 1. 定位

本 Skill 负责 **风险特征分析的"上游取数"环节**，**与 `risk-feature-pipeline` 解耦**：

```
[行内 Hive / 数仓]
        │
        │  本 Skill 提供：参数化 SQL 模板 + 导出后 CSV 校验
        ▼
[落盘 CSV → data/raw/]
        │
        │  契约：column_mapping.yaml 指定的列名/类型
        ▼
[risk-feature-pipeline] ← 下游分析 Skill，本 Skill 不参与
```

**核心约束**：
- 本 Skill **不直连数据库**，不要求 PyHive / impyla / JDBC。
- LLM **不接触数据库凭证**；SQL 由 data team 或业务用户在 HUE / DBeaver / Beeline 里粘贴执行。
- 本 Skill 的"产物"是：可复制的 SQL 文本 + 落盘 CSV 的校验报告。

---

## 2. 与 risk-feature-pipeline 的契约

衔接靠两样东西：

1. **CSV 文件**：落盘到 `data/raw/<project>/`，文件名约定见 §5。
2. **`column_mapping.yaml`**：与 `risk-feature-pipeline/config/column_mapping.yaml` 同源（建议软链接或对齐机制）。本 Skill 的 SQL 模板**输出列名必须满足**该 yaml 中 `required.*` + 用户启用的特征列。

下游不关心 Hive 表里字段叫什么；上下游只通过 yaml 对齐。

---

## 3. 目录结构（计划）

```
risk_data_extract/
├── SKILL.md                          # 本文件
├── sql_templates/                    # 参数化 SQL 模板（Jinja2）
│   ├── credit_wide_table.sql.j2      # 待填：征信宽表
│   ├── bad_customer.sql.j2           # 待填：坏客户清单
│   ├── industrial_change.sql.j2      # 待填：工商变更
│   └── README.md                     # 待填：每个模板的占位说明
├── scripts/
│   ├── render_sql.py                 # 待填：占位 → 可复制 SQL
│   ├── validate_export.py            # 待填：CSV schema 校验
│   └── config.py                     # 待填：模板参数默认值
├── schemas/                          # 待填：每张导出表的期望 schema（JSON Schema）
│   ├── credit_wide_table.schema.json
│   └── bad_customer.schema.json
└── README.md                         # 待填：使用说明
```

> 当前仅创建目录与本 SKILL.md 占位；具体内容根据银行数据结构再设计。

---

## 4. 典型工作流（设计目标）

```
1. 用户/Data team 看 SKILL.md，确定要导出的数据范围
2. 在 sql_templates/ 选模板，根据 占位（日期、分行、客户类型等）填参数
   ↳ 用 render_sql.py 自动填占位，或手动改
3. 把生成的 SQL 粘贴到 HUE / Beeline 执行 → 下载 CSV
4. CSV 落到 data/raw/<project>/
5. 跑 validate_export.py：检查列名、类型、空率、行数区间
6. 校验通过 → 切到 risk-feature-pipeline 跑分析
```

---

## 5. 落盘约定（待确认）

```
data/raw/<project>/
├── 征信宽表.csv             # 满足 column_mapping.required.customer_id + 数值特征列
├── 坏客户清单.csv           # 至少含 customer_id（可选 target、违约日期）
├── 工商变更.csv             # 待填
└── _extract_meta.json       # 由 render_sql.py 写入：模板版本、参数、生成时间、SQL 哈希
```

`_extract_meta.json` 用于：
- 留痕：哪份 CSV 是用什么参数、什么版本模板导的
- 回溯：复现分析时知道源数据的口径

---

## 6. SQL 模板设计原则（占位条目，待细化）

待补充内容（按银行数据结构敲定后填）：

- [ ] 占位参数命名规范（日期、机构、客户类型、特征清单）
- [ ] 时间口径（快照日 / 时间窗 / 滚动窗）
- [ ] 分群维度的 join 顺序
- [ ] 大表分批策略（按分行 / 按月 / 按客户哈希）
- [ ] 数据脱敏要求（客户名、证件号、手机号）
- [ ] 行级权限（branch filter）的强制注入
- [ ] 字段口径文档来源（链接到行内数据字典）

---

## 7. 安全 & 合规约束（占位）

- [ ] 不直连数据库，不存储数据库凭证
- [ ] SQL 模板必须在生成的注释里标注：导出人、用途、留存周期
- [ ] CSV 落盘前由 data team 对脱敏字段做 mask/hash
- [ ] 校验脚本不输出原始值，仅输出统计指标（rows / null_rate / dtype）
- [ ] 模板变更走 Git PR，不允许在 HUE 里临时改

---

## 8. 不在本 Skill 范围内的事

- ❌ 直接执行 SQL 取数（由 data team / 业务用户在 HUE 里操作）
- ❌ 数据脱敏（由数仓侧或 data team 脚本完成）
- ❌ 特征工程、衍生变量计算（由 `risk-feature-pipeline/risk_feature_engineering` 完成）
- ❌ 字段映射定义（由 `risk-feature-pipeline/config/column_mapping.yaml` 主导，本 Skill 引用）

---

## 9. 待办（下一阶段补全）

按优先级：

1. 拿到银行内征信表、坏客户表、工商表的真实 schema
2. 与 data team 对齐字段口径（什么算"坏"、时间窗、分行口径）
3. 起草 `credit_wide_table.sql.j2` 第一版
4. 起草 `validate_export.py` —— 这个不依赖具体表，可以先做骨架
5. 跟 `risk-feature-pipeline/config/column_mapping.yaml` 对齐 / 共享机制设计

---

**注**：本文件随银行数据结构调研推进而更新；当前为占位骨架。
