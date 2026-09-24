# CLAUDE.md

本文件为 Claude Code 在本仓库工作时的指引。

## 仓库范围

项目本体是 **`risk-feature-pipeline/`**：企业征信风险特征分析流水线（IV / LR / 规则挖掘 / 客户级触碰 / Word 报告）。
用户说"更新项目 / 审查改动 / 加功能"时，默认只在这个目录里动手。

其它目录不属于项目代码：
- `subprojects/`（`risk-indicator-agent/`、`risk_data_extract/`、`risk_feature_MCPServer/`、`uci_acceptance_test/`、`handbook/`）—— 兄弟项目，用户明确指向时才碰。
- `.cursor/skills/` —— 另一个工具的 skill，与本流水线无关。
- `data/`、`output/`、`data_old/`、`衍生指标设计/` —— 本地数据与草稿（gitignore）。

## 架构（依赖单向，`tests/test_unit_kernel_boundary.py` 机器化锁定）

```
risk_core/        叶子层：paths / config / config_loader / column_mapper / contracts（磁盘契约单一真源）
                  / missing（缺失值口径）/ results_loader / io_utils / font_utils —— 不依赖任何上层
risk_mining/      挖掘内核：analysis/{engine,iv_core} · pipeline（run_generic_pipeline）
                  · pipeline_state（Level 状态机）· export（assemble_exports）—— 只依赖 risk_core
                  （导出步另调其实现 risk_export_report）
                  组合根：cli · argspec（flag 单一注册表）· commands/<子命令>.py —— 唯一可同时 import 内核与子 skill 的层
risk_legacy_chains/  credit / gsfc 黑盒老链路（归组合根层；数值由 tests/test_golden_legacy_chains.py 钉死，不改口径）
risk_<子skill>/   各自 SKILL.md + scripts/；独立子 skill（data_prep / result_query / visualization /
                  trigger_extraction / threshold_explore / docx_report）只依赖 risk_core，互不横向依赖
risk_pipeline/ · shared/   纯兼容 shim（旧导入路径的别名/再导出），生产代码不得依赖，下版本删除
```

新代码按上面分层 import：`from risk_core.paths import ...`、`from risk_mining.analysis.engine import ...`，
**不要**再写 `risk_pipeline.*` / `shared.*`，也不要在模块顶层 `sys.path.insert`。
设计与迁移史见 `docs/DECOUPLING-DESIGN.md`，版本变更代号（A1/D2/E1…）见 `CHANGELOG.md`。

## 入口

对 agent 暴露的唯一入口是 CLI（`cd risk-feature-pipeline`）：

```bash
# 一键：generic 走 prepare → analyze → export（→ Level 1）
python -m risk_pipeline run --pipeline generic --wide data/raw/x.csv --bad-customer data/raw/bad.csv \
    --id-col 客户编号 --target-col is_bad --project xxx --confirmed-new-dataset
python -m risk_pipeline run --pipeline credit        # 老链路；gsfc 同理，数据路径走随包 YAML

# 细控
python -m risk_pipeline prepare  --wide ... --bad-customer ... --id-col ... --target-col ... --project xxx
python -m risk_pipeline analyze  --project xxx --steps univariate,iv,lr,rules --category-dims 企业规模
python -m risk_pipeline export   --project xxx                       # → Level 1

# Level 1 之后（query / visualize / explore_thresholds 不推进 Level）
python -m risk_pipeline query    --project xxx --kind iv --top 15
python -m risk_pipeline visualize --project xxx
python -m risk_pipeline explore_thresholds --project xxx --pairs-file pairs.csv
python -m risk_pipeline trigger  --project xxx --features-file f.json --confirmed    # → Level 2
python -m risk_pipeline report   --project xxx --report-markdown r.md --purpose internal   # → Level 3
```

- 全局参数 `-q` / `--verbose` / `--state-dir` 写在子命令前后均可。
- `--steps` 合法值：generic/analyze = `univariate,iv,lr,rules`；credit = `data_prep,feature_engineering,univariate,iv,lr,export`；gsfc = `data_prep,feature_eng,univariate,iv,lr,export`。
- Level 状态机：前置 → 过渡态 → Level 1 → Level 2 → Level 3，记录在 `data/results/<project>/.pipeline_state.json`；prepare 输入变化会把 Level 重置为前置。阻断节点与确认参数见 `references/blocking-gates.md`，各子命令用法见 `references/cli/*.md`。
- Python API（notebook 调研用）：`risk_data_prep.scripts.prepare_df` → `risk_mining.pipeline.run_generic_pipeline`；读结果用 `risk_result_query.scripts.load_results / top_features`。

## Agent 硬规矩（详见 `risk-feature-pipeline/AGENTS.md`）

1. **先查再跑**：用户说"查/读/解读/top X"时走 `query` / `risk_result_query`，不重跑链路。
2. **用 `prepare` / `prepare_df`**，不要手抄"读宽表 + 合并坏客户 + 选特征列"。
3. 单脚本 + `verbose=False` + `head(N)`；大结果禁止整表打印。
4. 报结论前先看 `{project}_audit.json`（IV 过拟合嫌疑、不稳定规则、Level）。

## 配置与路径

- 配置单一来源：`risk_core/config.py`，数值来自随包 `risk_core/config/default.yaml` + `column_mapping.yaml`。
- **不支持运行时覆盖（单行场景，已决）**：CLI 与 Python API 都只读随包 YAML，没有 `--config`。适配某份数据走 flag（`--id-col` / `--target-col` / `--category-dims` …）；长期接入新银行属开发仓库维护动作，直接改随包 YAML。
- 路径唯一入口 `risk_core/paths.py`：`RISK_PROJECT_ROOT`（输入根）、`RISK_OUTPUT_ROOT`（输出根，缺省 = 项目根）；优先级 env > 入参 > 自 CWD 向上找 `data/` > CWD。均在调用时解析。读、写产物统一以输出根为准；读产物的子命令自动跟随 `export --output-subdir`。细节见 `references/paths-env.md`。
- **永远不要**自写 `os.getcwd()` / `__file__` 兜底路径，用 `risk_core.paths` 的 `get_project_root / get_output_root / results_dir / output_dir / ensure_writable_dir`。

## 统计口径要点

- 样本门槛（`default.yaml` `thresholds`）：MIN_SAMPLES 50、MIN_BAD_SAMPLES 10（IV）、MIN_BAD_CORR 15、MIN_BAD_LR 20 / MIN_GOOD_LR 50、MIN_SAMPLES_CV 200 / MIN_BAD_CV 30（不足则 AUC 降为训练集口径并标注）。
- IV：自适应分箱，零膨胀特征众数单独成箱，缺失单独成箱，WOE 截断 ±5；IV > 2.0 视为过拟合嫌疑、不进推荐；可信度 可信 / 参考 / 不可信-样本不足 / 不可信-过拟合嫌疑。
- 缺失值（`risk_core/missing.py`）：统计检验成对删除；LR / 规则 / 阈值用中位数填补（训练与评估同一套）；IV/WOE 缺失单独成箱；credit/gsfc 老链路保持原口径。
- 规则：训练集挖掘、留出集评估 Lift/闸门，稳定性为留出集 bootstrap；坏客户不足时回退样本内并在「评估口径」列标注。
- 触碰阈值只在适用范围内计算，并做风险方向校验。

## 产物

generic 链路写 `data/results/<project>/` 与 `output/<project>/`（credit/gsfc 结果 CSV 带 `征信/`、`工商财务/` 前缀）。
文件名 `{project}_{类型}.csv`（utf-8-sig），主要有 `_IV分析结果_全量.csv`、`_IV分析结果_分群.csv`、`_特征风险相关性.csv`、
`_逻辑回归系数.csv`、`_IV可信度诊断.csv`、`_IV值透视表.csv`、`_综合特征分析结果.csv`、`_风险规则表.csv`、
`_LLM报告数据.json`、`_LLM_分群画像.csv`、`_audit.json`。列名与 schema 见 `docs/SCHEMA.md`，术语见 `docs/GLOSSARY.md`。

## 开发与测试

```bash
cd risk-feature-pipeline
pip install -e '.[viz,dev]'
ruff check .            # 只开语法错误 + pyflakes 规则，配置在 pyproject.toml
python -m pytest -q     # 全部；-k smoke 只跑端到端冒烟
```

CI（`.github/workflows/risk-feature-pipeline.yml`）在 Python 3.10 / 3.12 上跑同样两步。关键测试：
`test_unit_kernel_boundary.py`（分层红线，含字符串式动态 import）、`test_golden_legacy_chains.py`（老链路数值钉死）、
`test_unit_skill_independence.py`（独立子 skill 隔离）、`test_smoke_*.py`（端到端）。

## 编码规范

- 交互、注释、输出一律中文；CSV 用 `utf-8-sig`。
- 输出中不得出现客户名称、编号、电话。
- 跳过的分群必须显式记录原因；AUC 必须标注类型（交叉验证 / 训练集-样本不足 / 训练集-CV失败）。
- Matplotlib 出图走 `risk_core.font_utils` 的中文字体探测。
- 改动保持外科手术式：只动任务涉及的文件，不顺手重构；改行为时补回归测试并在 `CHANGELOG.md` 记代号。
