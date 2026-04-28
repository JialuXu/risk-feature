# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

The project content is **`risk-feature-pipeline/`** — a custom enterprise credit risk feature analysis pipeline (企业征信风险特征分析).

**Non-project directories** (reference material only, not part of the codebase):
- `skills/` — Anthropic's official Skills examples (cloned from anthropics/skills). Used only as a reference for SKILL.md authoring conventions. Do **not** edit or ship files here as part of the pipeline.
- `data/`, `output/` — local data scratch (gitignore-style; not reviewed as code).

When the user asks you to "update the project" / "review my changes" / "add a feature," scope your work to `risk-feature-pipeline/` unless they explicitly point elsewhere.

## Risk Analysis Pipeline (risk-feature-pipeline/)

A modular pipeline for mining risk characteristics across customer segments. Each step is a standalone Skill with its own `SKILL.md` and `scripts/` directory. An orchestrator SKILL.md at the pipeline root picks between three pipelines (`credit` / `gsfc` / `generic`) and execution depths (full / single-dim fast / read-existing-results).

### Directory Structure

```
risk-feature-pipeline/
├── SKILL.md                   # 顶层调度器（credit/gsfc/generic 三条管线的路由）
├── AGENTS.md                  # 本目录下 agent 的硬规矩（先查再跑、prepare_df、verbose=False 等）
├── report-prompt.md           # DOCX 报告写作约束（供 risk_docx_report 使用）
│
├── shared/                    # 共享模块（唯一配置源 + 统一入口）
│   ├── __init__.py
│   ├── __main__.py            # python -m shared 执行入口
│   ├── config.py              # 公共配置（从 YAML 加载）
│   ├── config_loader.py       # YAML 加载器（支持深度合并）
│   ├── column_mapper.py       # 字段映射器 ColumnMapper
│   └── pipeline.py            # run_credit_pipeline / run_gsfc_pipeline / run_generic_pipeline
│
├── config/                    # YAML 配置目录
│   ├── default.yaml           # 默认阈值、IV 参数、数据路径
│   └── column_mapping.yaml    # 字段映射模板（主键、目标列、分群维度）
│
├── risk_data_prep/            # Step 1: 数据准备
│   └── scripts/
│       ├── prepare_df.py      # ⭐ 标准 "宽表 + 坏客户 → (df, feature_cols)" 合成
│       ├── data_prep.py       # prepare_credit_wide_table
│       ├── wide_table_builder.py
│       └── io_utils.py
│
├── risk_feature_engineering/  # Step 2: 特征工程
│   └── scripts/
│       ├── financial_feature_engineering.py
│       ├── credit_feature_engineering.py
│       └── change_feature_engineering.py   # 工商变更类衍生特征
│
├── risk_segment_univariate/   # Step 3: 分群单变量
├── risk_iv_diagnosis/         # Step 4: IV 诊断
├── risk_logistic_regression/  # Step 5: 逻辑回归
├── risk_rule_mining/          # Step 5.5 (可选): 决策树规则挖掘
├── risk_export_report/        # Step 6: 标准 CSV + LLM JSON 导出
│
├── risk_result_query/         # ⭐ 查询型子 Skill：读磁盘上的已导出结果
│   ├── SKILL.md
│   ├── references/            # 按需加载的参考（列名、配方、文件布局）
│   │   ├── columns.md
│   │   ├── query_recipes.md
│   │   └── file_layout.md
│   └── scripts/
│       └── results_loader.py  # load_results / top_features
│
├── risk_trigger_extraction/   # ⭐ 触碰提取子 Skill：把风险结论落到每个客户
│   ├── SKILL.md
│   └── scripts/
│       ├── config.py          # RISK_FEATURES 默认特征配置
│       └── trigger_extraction.py  # extract_triggers / compute_thresholds / evaluate_triggers
│
└── risk_docx_report/          # 交付型子 Skill：LLM JSON → 正式 Word 报告
    └── scripts/
        ├── build_prompt_bundle.py     # 打包 report-prompt.md + LLM JSON
        ├── build_docx_report.py       # Markdown 正文 → .docx
        └── render_docx_report.js      # Node 渲染器
```

### Skill 分工概览

| Skill | 角色 | 典型触发语 |
|---|---|---|
| 顶层 `SKILL.md` | 总控调度（选管线 + 选深度） | "帮我做风险特征分析"、"分析这份宽表" |
| `risk_data_prep` | 宽表构建、打标、字段摸底 | "合并数据"、"打 is_bad 标签" |
| `risk_feature_engineering` | 比率类衍生特征 | "做特征工程" |
| `risk_segment_univariate` | 分群相关性/均值差/T 检验 | "分群单变量" |
| `risk_iv_diagnosis` | 自适应分箱 IV + 可信度 | "IV 分析"、"IV 可信度" |
| `risk_logistic_regression` | 标准化 + L2 的分群 LR | "LR"、"回归系数"、"AUC" |
| `risk_rule_mining` | 决策树规则挖掘（多变量交互） | "规则挖掘"、"预警规则"、"审批规则" |
| `risk_export_report` | 8 CSV + LLM JSON + 分群画像 | "导出结果"、"生成 LLM JSON" |
| `risk_result_query` | **只读磁盘已有结果**，不重跑 | "查/看/top X"、"解读已有分析" |
| `risk_trigger_extraction` | 把风险结论落到每个客户（触碰 + IV 加权得分） | "哪些客户触碰了风险阈值"、"生成风险预警名单"、"客户级风险扫描" |
| `risk_docx_report` | LLM JSON → `.docx` | "生成 Word 报告"、"正式报告" |

### Pipeline Flow

```
risk_data_prep → risk_feature_engineering → risk_segment_univariate
                                          → risk_iv_diagnosis
                                          → risk_logistic_regression
                                          → risk_rule_mining (optional)
                                                    ↓
                                          risk_export_report
                                                    ↓
                                          risk_docx_report (optional, for .docx)

          查询路径（不触发上面任一步骤）：
          已导出 CSV → risk_result_query.load_results() → top_features()
```

### Key Entry Points

```python
# ⭐ 标准数据准备入口（不要再每个 agent 手抄合并坏客户的代码）
from risk_data_prep.scripts import prepare_df
df, feature_cols = prepare_df(
    wide_path='...', bad_customer_path='...',
    id_col='客户编号', target_col='is_bad',
    filter={'企业规模': {'exclude': ['0']}},
    exclude_features={'授信总金额', '表内授信余额'},
)

# ⭐ 统一管线执行
from shared.pipeline import (
    run_credit_pipeline, run_gsfc_pipeline, run_generic_pipeline,
)
run_generic_pipeline(
    df=df, feature_cols=feature_cols, target_col='is_bad',
    project_name='舆情特征分析', category_dims=['企业规模'], qual_dims=[],
    steps=['univariate', 'iv', 'lr', 'export'], verbose=False,
)

# ⭐ 查询已导出结果（不重跑管线）
from risk_result_query.scripts import load_results, top_features
r = load_results('舆情特征分析')          # 自动定位 data/results/征信/<project>/
top_features(r, kind='iv', n=15)
top_features(r, kind='lr', dim='企业规模', group='小型企业', n=15, sign='positive')
top_features(r, kind='corr', dim='企业规模', group='小型企业', n=15)

# ⭐ 触碰提取（把风险结论落到每个客户）
from risk_trigger_extraction.scripts.trigger_extraction import extract_triggers
df_wide, df_long, df_threshold = extract_triggers(
    df=df,                          # 已完成特征工程的宽表
    project_name='征信触碰分析',    # 输出文件前缀
)
# 自定义特征配置时传 features= 参数（否则使用 RISK_FEATURES 默认值）

# 单步调用（高级用法，普通情况用上面的统一入口即可）
from risk_data_prep.scripts.data_prep import prepare_credit_wide_table
from risk_feature_engineering.scripts.financial_feature_engineering import feature_engineering
from risk_segment_univariate.scripts.segment_univariate import univariate_by_group
from risk_iv_diagnosis.scripts.iv_group_diagnosis import iv_by_group, reliability_diagnosis
from risk_logistic_regression.scripts.group_logistic_regression import lr_by_group
from risk_rule_mining.scripts.rule_extraction import mine_rules
from risk_export_report.scripts.report_analysis import export_results, build_llm_report_data
```

注：所有子 Skill 目录均使用下划线命名，可直接作为 Python 包导入。

### CLI Entry (shared.pipeline)

```bash
cd risk-feature-pipeline
python -m shared --pipeline credit                       # 征信全流程
python -m shared --pipeline gsfc --steps data_prep iv    # 指定步骤
python -m shared --pipeline credit --quiet               # 静默
python -m shared --help
```

合法 `--steps` 取值：`data_prep`、`feature_engineering`、`univariate`、`iv`、`lr`、`export`。

### Configuration Architecture

All configuration is centralized and YAML-driven:

- **唯一 Python 配置源**: `risk-feature-pipeline/shared/config.py` — 所有模块 `from shared.config import *`
- **YAML 数据源**: `config/default.yaml` + `config/column_mapping.yaml`
- **各子模块 `scripts/config.py`**: 仅 `from shared.config import *` + 模块专属常量
- **用户覆盖**: 只覆盖差异项的自定义 YAML；其余自动回退默认值

```python
from shared.config_loader import load_config
config = load_config()                         # 默认
config = load_config("config/my_bank.yaml")    # 深度合并

from shared.column_mapper import ColumnMapper
mapper = ColumnMapper("config/my_bank.yaml")
mapper.customer_id  # -> "CUST_NO"
mapper.target       # -> "DEFAULT_FLAG"
mapper.qual_prefix  # -> "标签_"
mapper.detect_qual_cols(df.columns)
```

### Sample Thresholds

Centralized in `config/default.yaml` (Python: `shared.config`):

| Threshold | Value | Purpose |
|-----------|-------|---------|
| MIN_SAMPLES | 50 | Skip segment if total < 50 |
| MIN_BAD_SAMPLES | 10 | Skip IV calculation |
| MIN_BAD_CORR | 15 | Skip correlation/T-test |
| MIN_BAD_LR | 20 | Skip logistic regression |
| MIN_GOOD_LR | 50 | Skip logistic regression |
| MIN_SAMPLES_CV | 200 | Downgrade to train-set AUC |
| MIN_BAD_CV | 30 | Downgrade to train-set AUC |

### IV Reliability Rules

- WOE capped to [-5.0, +5.0]
- Adaptive binning: `bins = max(3, min(n_bad // 3, n_samples // 20, 10))`
- IV > 2.0 = overfitting suspect, excluded from recommendations
- Credibility grades: 可信 / 参考 / 不可信-样本不足 / 不可信-过拟合嫌疑

### Standard Output Files

Pattern: `{project_name}_{type}.csv` (UTF-8 with BOM), written under
`data/results/征信/{project_name}/` and `output/征信/{project_name}/`.

1. `_IV分析结果.csv` — Full-sample IV
2. `_特征风险相关性.csv` — Per-segment correlations
3. `_逻辑回归系数.csv` — LR coefficients + AUC + AUC type
4. `_IV值分析.csv` — Per-segment IV with credibility
5. `_IV可信度透视表.csv` — Credibility pivot
6. `_IV可信度诊断.csv` — IV reliability summary
7. `_IV值透视表.csv` — IV pivot
8. `_综合特征分析结果.csv` — Consolidated
9. `_LLM报告数据.json` + `_LLM_分群画像.csv` — for LLM / docx report

`risk_result_query.load_results(project_name)` 一次性读取上述文件并暴露为长格式 DataFrame（`iv_full` / `iv_group_all` / `corr_long` / `lr_coef_long` / `lr_auc_long` / `comprehensive` / `reliability_summary` 等）。列名详情见 `risk_result_query/references/columns.md`。

## Agent Behavior (risk-feature-pipeline/AGENTS.md)

在 `risk-feature-pipeline/` 下工作时，必须遵守 `AGENTS.md` 的硬规矩：

1. **先查再跑**：用户说"查/读/解读/top X"时默认走 `risk_result_query`，不重跑管线
2. **用 `prepare_df`**：不要手抄"读宽表 + 合并坏客户 + 选特征列"
3. **单脚本 + `verbose=False` + `head(N)`**：Bash 之间不保留 Python 状态；大结果禁止整表打印

决策树、禁止清单、失败上报格式见 `risk-feature-pipeline/AGENTS.md`。

## Coding Standards

- All interactions, comments, outputs in Chinese (中文)
- Matplotlib: include OS-detection for Chinese font support
- Skipped segments must be logged explicitly with reason
- AUC must be labeled with type (交叉验证 / 训练集-样本不足 / 训练集-CV失败)
- No customer names, IDs, or phone numbers in any output
- CSV exports use `utf-8-sig` encoding

### Multi-Bank Support

```yaml
# config/city_bank.yaml — 仅覆盖与默认值不同的部分
thresholds:
  min_samples: 30
  min_bad_samples: 5
column_mapping:
  required:
    customer_id: "客户号"
    target: "是否不良"
  qualification:
    prefix: "标签_"
```

## Data Paths

All data paths are configurable via `config/default.yaml`. Defaults:

- `data/raw/` — Source data (read-only)
- `data/processed/` — Cleaned intermediate data
- `data/results/` — Analysis outputs (CSV)
- `output/` — Final charts, Excel, LLM JSON, docx reports

## Reference-Only: `skills/`

`skills/` contains Anthropic's official examples cloned from `anthropics/skills`. **Treat it as read-only reference.** Useful when:

- Drafting a new SKILL.md and wanting convention examples
- Looking at `skill-creator` for the evaluation / packaging workflow
- Seeing how `docx` / `pdf` / `pptx` / `xlsx` skills structure their scripts

Do not modify files under `skills/` as part of pipeline changes, and do not copy its scaffolding scripts (evals, packaging) into `risk-feature-pipeline/` unless explicitly asked.
