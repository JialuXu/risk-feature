# risk-feature-pipeline 核心链路

`risk-feature-pipeline` 是客户级风险特征分析的核心链路，面向“主键 + 二分类目标 + 数值特征列”的宽表数据，统一通过 `python -m risk_pipeline <subcommand>` 完成数据准备、分群分析、IV/LR/规则挖掘、标准结果导出、客户级触碰、可视化和报告生成。

## 机制图

![risk-feature-pipeline 机制图](docs/risk-pipeline-mechanism.drawio.svg)

可编辑源文件见 [`docs/risk-pipeline-mechanism.drawio`](docs/risk-pipeline-mechanism.drawio)。需要调整图时，使用 draw.io / diagrams.net 打开源文件，导出同名 SVG 后保持 README 引用不变。

## 安装

本项目是**单一 pip 分发**（`risk-feature-pipeline`），装完提供一个 `risk-pipeline` 控制台命令（等价于 `python -m risk_pipeline`）：

```bash
pip install .            # 核心：分析链路（prepare/analyze/export/query/trigger/run）
pip install '.[viz]'     # 追加：visualize 出图（matplotlib）
pip install '.[dev]'     # 追加：pytest 等开发依赖
```

安装后可在**任意目录**运行；产物默认落在**当前工作目录**下的 `data/results/<project>/` 与 `output/<project>/`。要固定输入/输出位置，设两个环境变量（优先级高于自动探测）：

```bash
export RISK_PROJECT_ROOT=<数据工作区>   # 输入读自何处
export RISK_OUTPUT_ROOT=<可写输出区>    # 结果写到何处（默认复用 PROJECT_ROOT）
risk-pipeline run --pipeline generic --wide data/raw/x.csv \
  --id-col 客户编号 --target-col is_bad --project 我的项目 --confirmed-new-dataset
```

> **不做 pip 安装也能跑**（如技能包直接拷贝部署）：`PYTHONPATH=<仓库根> python -m risk_pipeline ...`，或直接在仓库根目录下 `python -m risk_pipeline ...`。代码可导入性与数据落点是两件事，详见 [`references/paths-env.md`](references/paths-env.md)。
>
> **默认配置随包分发**：`risk_core/config/default.yaml`（阈值 / IV 参数 / 路径）与 `risk_core/config/column_mapping.yaml`（字段映射）已打进 wheel，安装后自动加载，不需要仓库目录布局。
>
> **docx 报告不在 pip 范围**：`report` 子命令渲染 `.docx` 依赖 Node.js + 内置 `.js` 渲染器 + `report-prompt.md`（仓库相对布局），pip 安装不包含这些。需要正式 Word 报告时，用技能包发布（`python release/pack.py`）部署完整目录树，并另装 Node（`cd risk_docx_report && npm ci`）。分析链路与出图不受影响。

## 统一入口

所有 agent 工作流和集成调用优先使用统一 CLI：

```bash
python -m risk_pipeline <subcommand> [args]
```

核心子命令如下：

| 子命令 | 作用 | 结果层级 |
|---|---|---|
| `prepare` | 读取宽表和坏客户清单，生成 `prepared.csv` 与 `features.json` | 前置 |
| `analyze` | 按 `univariate → iv → lr → rules` 固定顺序执行分析子集 | 过渡态 |
| `export` | 将 `_intermediate/` 转成标准 CSV、LLM JSON 和分群画像 | Level 1 |
| `query` | 只读已有结果，查询 top IV / LR / 相关性 | 不推进 |
| `visualize` | Level 1 后读取结果 CSV 生成 PNG 图表 | 不推进 |
| `trigger` | 将风险结论落到客户级触碰明细 | Level 2 |
| `report` | 将 LLM JSON 与报告正文渲染为 Word | Level 3 |
| `run` | 便捷组合；`generic` 走 `prepare → analyze → export` | Level 1 |

## 典型流程

自备宽表最常见路径：

```bash
python -m risk_pipeline run --pipeline generic \
  --wide data/raw/我的宽表.csv \
  --bad-customer data/raw/坏客户清单.csv \
  --id-col 客户编号 \
  --target-col is_bad \
  --project 我的项目 \
  --confirmed-new-dataset
```

只想重跑某些分析步骤时：

```bash
python -m risk_pipeline analyze \
  --project 我的项目 \
  --steps univariate,iv,lr,rules \
  --category-dims 企业规模

python -m risk_pipeline export --project 我的项目
```

已有结果只读查询或出图时，不重跑上游：

```bash
python -m risk_pipeline query --project 我的项目 --kind iv --top 15
python -m risk_pipeline visualize --project 我的项目          # 需先装可视化依赖
```

> **可视化依赖**：matplotlib / seaborn 不在核心链路依赖里。首次出图前需要安装：
> ```bash
> pip install -e .[viz]                    # 推荐：同时声明项目可被 import
> # 或
> pip install matplotlib seaborn
> ```
> PEP 668 锁定环境（部分 macOS / CI）请先 `python -m venv .venv && source .venv/bin/activate`，或加 `--break-system-packages`。

## 集成改造要点

- 新银行或新数据源**长期接入**（开发仓库维护动作）：直接编辑 `risk_core/config/column_mapping.yaml`（字段映射）与 `risk_core/config/default.yaml`（阈值、路径、IV 参数），CLI 自动读取；**不存在** `--columns-file` / `--config` CLI 入参，也不会自动加载 `.risk_pipeline_columns.yaml` 或 `config/<bank>.yaml`。`prepare` 阶段会做一次列名预检，若 YAML 期望的分群维度在宽表中完全缺失会硬错提示。
- **一次性分析某份列名不同的数据**：不要改 YAML（沙盒/安装模式下等于改写随包分发的默认配置），走 CLI flag——`--id-col` / `--target-col` / `--category-dims <实际列名>`，预检拦截时加 `--skip-preflight` 放行。
- `prepare` 是数据进入链路的唯一标准入口；不要在外部脚本里手写“读宽表 + merge 坏客户 + 推断特征列”。
- `query` 和 `visualize` 都读取磁盘快照，不会自动感知上游数据已变化；重跑分析后需要重新 `export`，再查询或出图。
- `trigger` 会进入客户级运营结果，必须在 Level 1 后执行，并显式确认 features 配置。
- `report` 面向正式交付，`purpose=external` 时必须确认当前结果是最终版本。

更细的 agent 约束、阻断节点和日志规范见 [`AGENTS.md`](AGENTS.md)；面向自然语言调度的说明见 [`SKILL.md`](SKILL.md)。

## 文档辅助

| 文档 | 用途 |
|---|---|
| [`docs/SCHEMA.md`](docs/SCHEMA.md) | 所有 Level 1/Level 2 落盘 CSV 的列字典权威来源（A4 后统一列名、A5 后文件改名） |
| [`docs/GLOSSARY.md`](docs/GLOSSARY.md) | dim / group / scope / coverage 等术语统一表 + 列名跨表对照 + 阻断节点缩写 |
| [`docs/risk-pipeline-mechanism.drawio`](docs/risk-pipeline-mechanism.drawio) | 核心链路机制图源文件 |
