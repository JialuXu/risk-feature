# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

The project content is **`risk-feature-pipeline/`** — a custom enterprise credit risk feature analysis pipeline (企业征信风险特征分析).

**Non-project directories** (reference material only, not part of the codebase):
- `skills/` — Anthropic's official Skills examples (cloned from anthropics/skills). Used only as a reference for SKILL.md authoring conventions. Do **not** edit or ship files here as part of the pipeline.
- `data/`, `output/`, `data_old/`, `衍生指标设计/` — local scratch / drafts (gitignored; not reviewed as code).
- `risk-feature-pipeline.backup-*` — historical snapshots; do not edit.
- `risk-indicator-agent/`, `risk_data_extract/`, `risk_feature_MCPServer/`, `uci_acceptance_test/`, `handbook/` — sibling projects/experiments. Touch only when the user explicitly points there.

When the user asks you to "update the project" / "review my changes" / "add a feature," scope your work to `risk-feature-pipeline/` unless they explicitly point elsewhere.

## Risk Analysis Pipeline (risk-feature-pipeline/)

A modular pipeline for mining risk characteristics across customer segments. Each step is a standalone Skill with its own `SKILL.md` and `scripts/` directory. An orchestrator SKILL.md at the pipeline root picks between three pipelines (`credit` / `gsfc` / `generic`) and execution depths (full / single-dim fast / read-existing-results).

### Directory Structure

```
risk-feature-pipeline/
├── SKILL.md                   # 顶层调度器（credit/gsfc/generic 三条链路的路由）
├── AGENTS.md                  # 本目录下 agent 的硬规矩（先查再跑、prepare_df、verbose=False 等）
├── report-prompt.md           # DOCX 报告写作约束（供 risk_docx_report 使用）
│
├── risk_pipeline/             # 共享模块 + 统一 CLI 入口
│   ├── __init__.py
│   ├── __main__.py            # python -m risk_pipeline 执行入口
│   ├── cli.py                 # 9 子命令解析（prepare/analyze/export/query/visualize/trigger/explore_thresholds/report/run）
│   ├── cli_commands.py        # 子命令实现（薄壳 wrap 现有 Python API + state 推进）
│   ├── cli_io.py              # _intermediate/ 落盘与重建、features.json、数据集指纹
│   ├── pipeline_state.py      # .pipeline_state.json：Level 推进 + 历史追加 + 阻断节点
│   ├── paths.py               # get_project_root / get_output_root（唯一定位入口）
│   ├── config.py              # 公共配置（从 YAML 加载）
│   ├── config_loader.py       # YAML 加载器（支持深度合并）
│   ├── column_mapper.py       # 字段映射器 ColumnMapper
│   ├── pipeline.py            # run_credit_pipeline / run_gsfc_pipeline / run_generic_pipeline
│   └── analysis/              # ⭐ 共享分析内核（去重后单一实现）
│       ├── __init__.py
│       ├── iv_core.py         # IV/WOE/自适应分箱/可信度：唯一实现（三个 Skill 的 iv_analysis.py 退化为 shim）
│       └── engine.py          # 分群 单变量/IV/LR 引擎：唯一实现（iv_group_diagnosis / group_logistic_regression 退化为 shim）
│
├── shared/                    # ⚠️ 兼容 shim：转发到 risk_pipeline.*；下个版本会移除
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
│       ├── config.py          # RISK_FEATURES_GSFC 默认特征配置（GSFC 主题；RISK_FEATURES 为兼容 alias）
│       └── trigger_extraction.py  # extract_triggers / compute_thresholds / evaluate_triggers
│
├── risk_threshold_explore/    # ⭐ 候选规则阈值探索：单变量 optbinning + 业务级判定
│   ├── SKILL.md
│   └── scripts/
│       ├── config.py          # 五道门槛默认值 + OPTBIN_PARAMS
│       ├── threshold_explore.py  # explore_thresholds 核心 API
│       └── io_utils.py        # pair-list 读 + 候选阈值表写 + audit 节点追加
│
├── risk_docx_report/          # 交付型子 Skill：LLM JSON → 正式 Word 报告
│   └── scripts/
│       ├── build_prompt_bundle.py     # 打包 report-prompt.md + LLM JSON
│       ├── build_docx_report.py       # Markdown 正文 → .docx
│       └── render_docx_report.js      # Node 渲染器
│
└── risk_visualization/        # ⭐ 可视化子 Skill：Level 1 后读 CSV → PNG 图表
    ├── SKILL.md
    ├── references/chart_types.md      # 各图含义、解读、常见误读
    └── scripts/
        ├── visualize.py               # generate_charts() 顶层入口
        ├── font_utils.py              # 中文字体 OS 探测
        ├── style.py                   # 调色板 / figsize / dpi
        ├── chart_iv.py                # IV 条形图 + 分群 IV 热力图
        ├── chart_corr.py              # 分群相关系数条形图
        ├── chart_lr.py                # LR 系数 + 跨分群 AUC
        ├── chart_segment.py           # 分群画像（坏客户率柱图）
        ├── chart_tree.py              # 决策树（pkl 真树 / 规则反推）
        ├── chart_rules.py             # 规则 lift × coverage 散点
        ├── chart_combinations.py      # 指标组合 + 特征共现网络
        └── chart_threshold.py         # 候选阈值分箱坏率图 + 风险倍数对比图
```

### Skill 分工概览

| Skill | 角色 | 典型触发语 |
|---|---|---|
| 顶层 `SKILL.md` | 总控调度（选链路 + 选深度） | "帮我做风险特征分析"、"分析这份宽表" |
| `risk_data_prep` | 宽表构建、打标、字段摸底 | "合并数据"、"打 is_bad 标签" |
| `risk_feature_engineering` | 比率类衍生特征 | "做特征工程" |
| `risk_segment_univariate` | 分群相关性/均值差/T 检验 | "分群单变量" |
| `risk_iv_diagnosis` | 自适应分箱 IV + 可信度 | "IV 分析"、"IV 可信度" |
| `risk_logistic_regression` | 标准化 + L2 的分群 LR | "LR"、"回归系数"、"AUC" |
| `risk_rule_mining` | 决策树规则挖掘（多变量交互） | "规则挖掘"、"预警规则"、"审批规则" |
| `risk_export_report` | 8 CSV + LLM JSON + 分群画像 | "导出结果"、"生成 LLM JSON" |
| `risk_result_query` | **只读磁盘已有结果**，不重跑 | "查/看/top X"、"解读已有分析" |
| `risk_trigger_extraction` | 把风险结论落到每个客户（触碰 + IV 加权得分） | "哪些客户触碰了风险阈值"、"生成风险预警名单"、"客户级风险扫描" |
| `risk_threshold_explore` | 候选规则阈值探索（单变量 optbinning + 风险倍数 + 卡方 p） | "候选阈值/单变量阈值评审/这几个 (分群,特征) 跑一下" |
| `risk_docx_report` | LLM JSON → `.docx` | "生成 Word 报告"、"正式报告" |
| `risk_visualization` | IV/相关性/LR/分群/决策树/指标组合 PNG 图表（Level 1 后只读出图） | "画图/可视化/IV 条形图/决策树图/指标组合图" |

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

          可视化路径（Level 1 后；不触发上面任一步骤）：
          已导出 CSV → risk_visualization.generate_charts() → output/<project>/charts/*.png

          阈值探索路径（Level 1 后；不推进 level）：
          已导出 CSV + 人工 pair 清单 → risk_threshold_explore.explore_thresholds()
                                       → 候选阈值表 + 分箱明细 + audit 追加节点
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

# ⭐ 统一链路执行
from shared.pipeline import (
    run_credit_pipeline, run_gsfc_pipeline, run_generic_pipeline,
)
run_generic_pipeline(
    df=df, feature_cols=feature_cols, target_col='is_bad',
    project_name='舆情特征分析', category_dims=['企业规模'], qual_dims=[],
    steps=['univariate', 'iv', 'lr', 'export'], verbose=False,
)

# ⭐ 查询已导出结果（不重跑链路）
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
# 默认 features=None → 走 RISK_FEATURES_GSFC（仅工商财务主题适用）。其它主题
# （征信、舆情、generic）必须传 features=YOUR_LIST 或 CLI --features-file，
# 否则若匹配率 < 50% 会抛 RuntimeError 阻断（避免输出全 0 名单）。
# 默认会从宽表 CSV 剔除 is_bad/企业规模 等元信息列防 merge 冲突；
# 需保留可传 keep_metadata_cols=['企业规模', ...]。

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

### CLI Entry (risk_pipeline)

9 子命令（含 `visualize` / `explore_thresholds` / `run`），每条对应链路里一个固定阶段；状态机：前置 → 过渡态 → Level 1 → Level 2/3。

```bash
cd risk-feature-pipeline

# 一键跑通（generic：自带宽表 + 坏客户清单）
python -m risk_pipeline run --pipeline generic \
    --wide data/raw/x.csv --id-col 客户编号 --target-col is_bad \
    --project xxx --confirmed-new-dataset

# 也支持征信/工商财务老链路（数据路径走 config/ 默认值）
python -m risk_pipeline run --pipeline credit
python -m risk_pipeline run --pipeline gsfc --steps data_prep,iv
python -m risk_pipeline run --pipeline credit --quiet

# 三步走（细控）：prepare → analyze → export
python -m risk_pipeline prepare --wide data/raw/x.csv \
    --bad-customer data/raw/bad.csv --id-col 客户编号 \
    --target-col is_bad --project xxx --confirmed-new-dataset
python -m risk_pipeline analyze --project xxx \
    --steps univariate,iv,lr,rules --category-dims 企业规模
python -m risk_pipeline export --project xxx

# 后置子命令
python -m risk_pipeline query --project xxx --kind iv --top 15
python -m risk_pipeline visualize --project xxx
python -m risk_pipeline trigger --project xxx --use-default-features --confirmed
python -m risk_pipeline explore_thresholds --project xxx --pairs-file pairs.csv
python -m risk_pipeline report --project xxx \
    --report-markdown report.md --purpose internal

python -m risk_pipeline --help          # 全局帮助
python -m risk_pipeline <子命令> --help  # 子命令帮助
```

合法 `--steps` 取值：
- `run --pipeline credit`：`data_prep`、`feature_engineering`、`univariate`、`iv`、`lr`、`export`
- `run --pipeline gsfc`：`data_prep`、`feature_eng`、`univariate`、`iv`、`lr`、`export`
- `run --pipeline generic` / `analyze`：`univariate`、`iv`、`lr`、`rules`（CLI 强制按此顺序；`export` 由独立子命令完成）

老入口 `python -m shared --pipeline ...` 仍可用，但会打印 deprecation 警告，下个版本会移除。

`risk_pipeline/` 内含统一 CLI（`cli.py` / `cli_commands.py` / `cli_io.py`）、唯一权威的路径模块 `paths.py`（见下文 Data Paths）、运行时状态 `pipeline_state.py`，以及配置入口 `config.py` / `config_loader.py` / `column_mapper.py`。`shared/` 仍保留作为旧的兼容入口。

### Tests

测试在 `risk-feature-pipeline/tests/`（pytest）。`conftest.py` 会把 `risk-feature-pipeline/` 注入 `sys.path` 并提供 `synthetic_dataframe` fixture，可直接从仓库根运行：

```bash
cd risk-feature-pipeline
pytest                                          # 全部
pytest tests/test_unit_paths.py                 # 单文件
pytest tests/test_unit_paths.py::test_env_project_root_wins   # 单用例
pytest -k smoke                                 # 仅 smoke
```

- `test_smoke_*.py` — legacy / query / generic 链路 / trigger 的端到端冒烟。
- `test_unit_paths.py` — `RISK_PROJECT_ROOT` / `RISK_OUTPUT_ROOT` 优先级、`ensure_writable_dir` 友好报错。
- `test_unit_state.py`、`test_unit_blocking.py`、`test_unit_validation.py` — pipeline_state / 阻断逻辑 / 入参校验。

### Configuration Architecture

All configuration is centralized and YAML-driven:

- **唯一 Python 配置源**: `risk-feature-pipeline/risk_pipeline/config.py` — 所有模块 `from risk_pipeline.config import *`（旧 `shared/config.py` 已是转发 shim）
- **YAML 数据源**: `config/default.yaml` + `config/column_mapping.yaml`（IV 可信度阈值见 `iv.credibility`）
- **各子模块 `scripts/config.py`**: 仅 `from risk_pipeline.config import *` + 模块专属常量
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

A4/A5 后产物列名/文件名已统一对外（旧名仍写一份兼容副本，下版本移除）：
- 列：`特征` / `分群维度` / `分群名称`（旧 `特征名称` / `分群值` 在 `load_results()` 读取时自动 rename）
- 文件：IV 按颗粒度拆分

1. `_IV分析结果_全量.csv` ⭐ — Full-sample IV (旧名 `_IV分析结果.csv` 兼容副本仍写)
2. `_特征风险相关性.csv` — Per-segment correlations
3. `_逻辑回归系数.csv` — LR coefficients + AUC + AUC type
4. `_IV分析结果_分群.csv` ⭐ — Per-segment IV with credibility (旧名 `_IV值分析.csv` 兼容副本)
5. `_IV可信度透视表.csv` — Credibility pivot
6. `_IV可信度诊断.csv` — IV reliability summary
7. `_IV值透视表.csv` — IV pivot (查 top N 最快：行=分群、列=特征)
8. `_综合特征分析结果.csv` — Consolidated
9. `_LLM报告数据.json` + `_LLM_分群画像.csv` — for LLM / docx report
10. `_audit.json` ⭐ — 机器可读自检（IV>2 过拟合特征、不稳定规则、Level 状态；agent 报回前 cat 这个文件）

`risk_result_query.load_results(project_name)` 一次性读取上述文件并暴露为长格式 DataFrame（`iv_full` / `iv_group_all` / `corr_long` / `lr_coef_long` / `lr_auc_long` / `comprehensive` / `reliability_summary` 等）。列名详情见 `docs/SCHEMA.md` 与 `risk_result_query/references/columns.md`；术语表见 `docs/GLOSSARY.md`。

## Agent Behavior (risk-feature-pipeline/AGENTS.md + .cursor rules)

`.cursor/rules/karpathy-guidelines.mdc` 设了 `alwaysApply: true`，对所有改动生效：澄清假设、保持简单、外科手术式改动、目标驱动验证。

在 `risk-feature-pipeline/` 下工作时，必须遵守 `AGENTS.md` 的硬规矩：

1. **先查再跑**：用户说"查/读/解读/top X"时默认走 `risk_result_query`，不重跑链路
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

**唯一权威的路径定位**: `risk_pipeline/paths.py`（旧仓库里散落的 9 处 `get_project_root` 已收敛到此处）。

- `RISK_PROJECT_ROOT` — 显式指定项目根（输入读自何处）。设置后跳过 `data/` 探测。
- `RISK_OUTPUT_ROOT` — 显式指定输出根（结果写到何处）。未设置时复用项目根。
- 优先级：env > 函数入参 > 自 CWD 向上找首个含 `data/` 的目录 > CWD 兜底（带一次性 `[WARN]`）。
- `ensure_writable_dir(path)` 会把 `PermissionError` 转成 `RuntimeError`，提示设置 `RISK_OUTPUT_ROOT`。

**永远不要**自己写 `os.getcwd()` 或 `__file__` 兜底路径——这正是被替换掉的反模式。新代码应 `from risk_pipeline.paths import get_project_root, results_dir, output_dir, ensure_writable_dir`。

## Reference-Only: `skills/`

`skills/` contains Anthropic's official examples cloned from `anthropics/skills`. **Treat it as read-only reference.** Useful when:

- Drafting a new SKILL.md and wanting convention examples
- Looking at `skill-creator` for the evaluation / packaging workflow
- Seeing how `docx` / `pdf` / `pptx` / `xlsx` skills structure their scripts

Do not modify files under `skills/` as part of pipeline changes, and do not copy its scaffolding scripts (evals, packaging) into `risk-feature-pipeline/` unless explicitly asked.
