---
name: risk_export_report
description: 分析结果导出与报告读取技能：标准 CSV、综合汇总表、LLM JSON/CSV、分群画像、核心发现提炼，以及结果文件的真实导出契约与推荐读取顺序。
---

## 先读这里

本 Skill 不只负责"导出"，也是**读结果的契约文档**：
- 实际落地哪些文件（名称 + 目录）
- 用户只要结论时，优先读哪些文件
- 如何避免猜文件名、猜列名

若只需查询/解读已有结果，优先使用 `risk_result_query`（`load_results` + `top_features`），本 Skill 不重复提供查询 API。

## 方法论前提

- **输入**：上游算好的 IV、单变量、LR 结构化结果 + 宽表元信息；不依赖数据来源主题。
- **输出形态固定**：八类标准 CSV + 可选 LLM JSON/CSV。

## 流水线位置

- **前置**：完成 IV、单变量、LR 并持有内存结果对象与宽表。
- **本 Skill 为交付端**：标准文件名、目录、编码（`utf-8-sig`）均以本页为唯一说明。
- **推荐调用方式**：`python -m risk_pipeline export --project <项目名>`（agent 工作流必须经 CLI，见 `AGENTS.md` 三）；notebook 调研可用 `risk_pipeline.pipeline.run_generic_pipeline(..., steps=[..., 'export'])`。不建议直接调用脚本（避免路径参数不一致）。

## 何时使用

导出 CSV、综合特征表、LLM JSON、特征自动分类、维度去重、热力图/透视表数据落盘。

## 职责边界

| 负责 | 不负责 |
|------|--------|
| 八文件导出、`build_comprehensive_table`、LLM 数据构建 | 重新计算 IV/LR/相关（上游 Skill） |
| `get_feature_category`、`_detect_redundant_dims`、`_generate_key_findings` | 宽表与特征工程 |

## 实际导出契约

### 命名模式

```
{项目名}_{类型}.csv   或   {项目名}_{类型}.json
```

### 导出文件清单

**结果目录（默认 `data/results/...`，可通过 `results_base` 参数自定义）**

| 文件后缀 | 内容 |
|----------|------|
| `_IV分析结果_全量.csv` ⭐ | 全量 IV（旧名 `_IV分析结果.csv` 仍写一份兼容副本，下版本移除；文件名变更史见 `CHANGELOG.md`） |
| `_IV分析结果_分群.csv` ⭐ | 分群 IV 明细 + 可信度（旧名 `_IV值分析.csv` 仍写一份兼容副本） |
| `_特征风险相关性.csv` | 分群相关系数 + 样本元信息 |
| `_逻辑回归系数.csv` | 分群 LR 系数 + AUC + AUC类型 |
| `_IV值透视表.csv` | 分群×特征 IV 透视（行=分群，列=特征；查 top N 最快） |
| `_IV可信度透视表.csv` | 分群×特征 IV 可信度透视 |
| `_IV可信度诊断.csv` | 分群层面样本/坏率/可信率概况 |
| `_综合特征分析结果.csv` | 汇总全局 IV、跨分群一致性、综合评级 |
| `_风险规则表.csv` | 决策树规则（仅在 `analyze --steps univariate,iv,lr,rules` 后产生） |
| `_audit.json` ⭐ | 机器可读自检：IV>2 过拟合特征、不稳定规则、Level 状态 |

**输出目录（默认 `output/...`，可通过 `output_base` 参数自定义）**

| 文件后缀 | 内容 |
|----------|------|
| `_LLM报告数据.json` | 高层结论 JSON，适合报告生成与下游 DOCX |
| `_LLM_特征有效性汇总.csv` | LLM 视角重点特征摘要 |
| `_LLM_分群画像.csv` | 每个分群一行的画像结果 |

> 不是每次都产生全部文件；取决于是否执行了对应步骤且上游结果非空。**不要猜测文件名，以目录中的真实文件为准。**

## 推荐读取顺序

### 用户要高层结论

1. `_LLM报告数据.json`
2. `_LLM_分群画像.csv`
3. `_综合特征分析结果.csv`

### 用户要证据链

4. `_IV分析结果_分群.csv`（旧名 `_IV值分析.csv` 仍可兼容读取）
5. `_逻辑回归系数.csv`
6. `_特征风险相关性.csv`
7. `_IV可信度诊断.csv`

### 用户只问单一分群

先过滤 `分群维度 == <用户指定维度>` 再读取，不要扫全表。

## 列名速查（常用文件关键列）

> 对外列名已统一为「特征 / 分群维度 / 分群名称」三件套（历史 CSV 旧列名对照见 `CHANGELOG.md`）；详见 `docs/SCHEMA.md` 与 `risk_result_query/references/columns.md`（同时适用于磁盘 CSV 与内存 DataFrame）。

**`_IV分析结果_全量.csv`**：`特征` / `特征类型` / `IV值` / `预测能力` / `IV可信度` / `总样本数` / `总坏客户数`

**`_IV分析结果_分群.csv`**：`分群维度` / `分群名称` / `特征` / `IV值` / `IV可信度` / `样本数` / `坏客户数`

**`_逻辑回归系数.csv`**：`分群维度` / `分群名称` / `系数`（标准化后，**不是** `LR系数`）/ `AUC` / `AUC类型`

**`_综合特征分析结果.csv`**：`特征` / `iv_all`（**不是** `IV值`）/ `IV可信度` / `预测能力`（历史 CSV 中可能仍是旧列名 `特征名称`，`load_results()` 自动 rename）

**`_风险规则表.csv`**：`分群维度` / `分群名称`（A4 后已从「分群值」统一）/ `规则编号` / `规则条件` / `涉及特征` / `Lift` / `稳定性等级`

**`_LLM_分群画像.csv`**：`分群维度` / `分群名称` / `样本数` / `坏客户数` / `坏客户率` / `模型AUC` / `AUC类型` / `Top3_IV特征` / `Top3_风险相关特征`

**`_LLM报告数据.json`** 顶层键：`报告目标` / `分析概览` / `核心发现` / `特征有效性汇总` / `无效特征列表` / `分群画像_重点` / `分群画像_简略`

## 调用入口

CLI（推荐，agent 工作流唯一合法入口）：

```bash
python -m risk_pipeline export --project <项目名>   # 须先完成 analyze
```

Python 统一链路（notebook 调研用）：

```python
from risk_pipeline.pipeline import run_generic_pipeline

run_generic_pipeline(
    df=df, feature_cols=feature_cols, target_col='is_bad',
    project_name='<项目名>',
    category_dims=['企业规模'],
    qual_dims=[],
    steps=['univariate', 'iv', 'lr', 'export'],  # export 必须包含
    verbose=False,
)
```

直接调用脚本（高级用法，需自行管理路径）：

> `results_base` 和 `output_base` 是可配置参数，默认值为 `data/results` 和 `output`，可替换为任意可访问路径。

```python
from risk_export_report.scripts.report_analysis import export_results, build_comprehensive_table

exported = export_results(
    project_root, results,
    project_name='<项目名>',
    results_base='<结果目录路径>',   # 默认 'data/results'，可自定义
    output_base='<输出目录路径>',    # 默认 'output'，可自定义
)
```

## 本 Skill 强制规范

- CSV 使用 `utf-8-sig`；文件名不含敏感客户信息。
- 推荐特征列表**不得**包含 IV 超过可疑阈值（`IV_SUSPECT_THRESHOLD`）的条目。
- 读取结果前先确认真实文件存在；读 CSV/JSON 前先看表头/顶层键。
- 列名与预期不一致时，先修正读取逻辑，不沿用旧假设。

## 主要脚本映射

| 模块 | 作用 |
|------|------|
| `scripts/report_analysis.py` | 主路径：导出、综合表、LLM 数据、核心发现 |
| `scripts/report_export.py` | 备用路径（工商财务旧链路）：`export_results`、`build_llm_report_data_gsfc` |
