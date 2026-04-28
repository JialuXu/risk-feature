# 企业征信风险特征工程体系

> 一个围绕"**风险特征挖掘 → 衍生指标设计 → 工具与文档集成**"组织的多组件工程仓库。
> 本文件是顶层引导，详细文档分散在各子目录的 `README.md` / `SKILL.md` 中。

---

## 一、仓库定位

本仓库不是单一管线，而是一个**生态**：

- **核心**：模块化的风险特征分析流水线（IV / LR / 规则挖掘 / 客户级触碰）
- **上层**：基于 LLM 的衍生指标设计 Agent（把挖掘结果翻译成元表里的指标）
- **接口**：MCP Server，把管线包装成异步工具供 LLM 客户端（Claude Desktop / Cursor 等）调用
- **文档**：HonKit 手册站点，把仓库内的 `README.md` / `SKILL.md` 聚合并导出 PDF / DOCX
- **验收**：UCI Credit Card 数据集端到端测试剧本

> 默认所有交互、注释、输出使用**中文**。

---

## 二、顶层目录总览

```
risk-feature-pipeline/                # 仓库根
├── CLAUDE.md                         # Claude Code 工作规约（项目级）
├── README.md                         # 本文件（顶层综述与引导）
│
├── risk-feature-pipeline/            # ① 核心管线（Skills 集合 + 统一 CLI）
├── risk-indicator-agent/             # ② LLM 衍生指标 Agent（5 步流水线）
├── risk_feature_MCPServer/           # ③ MCP Server（异步工具封装）
├── handbook/                         # ④ HonKit 文档手册（聚合 + 导出）
└── uci_acceptance_test/              # ⑤ UCI 端到端验收测试
```

| # | 目录 | 角色 | 入口 |
|---|---|---|---|
| ① | `risk-feature-pipeline/` | 风险特征挖掘核心管线 | `python -m risk_pipeline <子命令>` |
| ② | `risk-indicator-agent/` | LLM 把特征结果翻译成衍生指标 | `python -m indicator_pipeline --step N --batch-id X` |
| ③ | `risk_feature_MCPServer/` | MCP 协议封装核心管线 | `python server.py`（stdio） |
| ④ | `handbook/` | 本地文档站 + PDF/DOCX 导出 | `npm run serve` / `npm run pdf` |
| ⑤ | `uci_acceptance_test/` | 公开数据集回归验证 | `source setup.sh` 后按 README 执行 |

---

## 三、组件关系

```
                 ┌──────────────────────────────────┐
                 │   原始宽表 + 坏客户清单（CSV）    │
                 └──────────────────┬───────────────┘
                                    │
                 ┌──────────────────▼───────────────┐
                 │ ① risk-feature-pipeline           │
                 │   prepare → analyze → export      │
                 │     ↘ trigger（客户级触碰）       │
                 │     ↘ report（Word 报告）         │
                 └──────────────────┬───────────────┘
                                    │ 标准 CSV + LLM JSON
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
┌─────────────────┐      ┌─────────────────────┐      ┌─────────────────┐
│ ③ MCP Server     │      │ ② indicator-agent    │      │ ④ handbook       │
│ 把 ① 包装成      │      │ 5 步 LLM 流水线 →    │      │ 聚合所有 README   │
│ MCP 工具，供     │      │ 衍生指标提案 →       │      │ / SKILL.md，可    │
│ Claude/Cursor    │      │ 元表注册（SCD2）     │      │ 本地浏览/导出     │
│ 等客户端调用     │      │                      │      │ PDF / DOCX       │
└─────────────────┘      └──────────┬──────────┘      └─────────────────┘
                                    │ 元表（SQLite + CSV）
                                    ▼
                          下次特征分析回写 IV → 触发优先级升降

  ⑤ uci_acceptance_test：以 UCI Credit Card 公开数据为输入跑 ①，
                         覆盖 prepare → analyze → export → query → trigger 全链路
```

---

## 四、快速路由（"我想做 X 该看哪里"）

| 我想…… | 去这里 | 关键命令 |
|---|---|---|
| 跑一次完整的风险特征分析（IV / LR / 触碰 / 报告） | `risk-feature-pipeline/README.md` | `python -m risk_pipeline run --pipeline credit` |
| 已经跑过一次，只是想查 top IV / 分群结果 | `risk-feature-pipeline/risk_result_query/SKILL.md` | `python -m risk_pipeline query --project X --kind iv --top 15` |
| 把分析结果翻译成衍生指标设计稿 | `risk-indicator-agent/README.md` | `python -m indicator_pipeline --step 1 --batch-id YYYYMMDD_X` |
| 在 Claude Desktop / Cursor 里调用管线 | `risk_feature_MCPServer/server.py` 顶部说明 | 配置 MCP server 后用 `run_pipeline` / `query_results` / `extract_triggers` |
| 本地浏览 / 导出全套文档 | `handbook/USAGE.txt` | `cd handbook && npm install && npm run serve` |
| 验证管线是否在你的环境里能跑通 | `uci_acceptance_test/README.md` | `source setup.sh` 后按章节顺序执行 |
| 适配新银行的字段名 | `risk-feature-pipeline/config/column_mapping.yaml` | 创建 `config/my_bank.yaml` 仅覆盖差异项 |

---

## 五、组件简介

### ① `risk-feature-pipeline/` — 核心管线

模块化的特征挖掘 Skills 集合，每一步都是一个独立的子目录（带 `SKILL.md` + `scripts/`）：

```
risk_data_prep        → 宽表合并 + 打 is_bad 标签 + 字段摸底
risk_feature_engineering → 比值类衍生特征
risk_segment_univariate  → 分群相关性 / T 检验
risk_iv_diagnosis        → 自适应分箱 IV + 可信度评级
risk_logistic_regression → 标准化 + L2 的分群 LR
risk_rule_mining         → 决策树多变量交互规则（可选）
risk_export_report       → 8 张标准 CSV + LLM 友好 JSON
risk_trigger_extraction  → 客户级风险触碰（宽表/长表/阈值表）
risk_result_query        → 只读已导出结果，不重跑管线
risk_docx_report         → LLM JSON → 正式 Word 报告
```

**统一 CLI**：`python -m risk_pipeline <subcommand>`，7 个子命令——`prepare` / `analyze` / `export` / `query` / `trigger` / `report` / `run`。

**Python API**：

```python
from risk_pipeline.pipeline import (
    run_credit_pipeline, run_gsfc_pipeline, run_generic_pipeline,
)
from risk_data_prep.scripts import prepare_df  # 标准 "宽表 + 坏客户 → (df, feature_cols)"
```

> 旧的 `python -m shared` / `from shared.X import Y` 仍可工作（兼容 shim），下一版会移除。

详细文档：`risk-feature-pipeline/README.md`、`risk-feature-pipeline/SKILL.md`、`risk-feature-pipeline/AGENTS.md`。

### ② `risk-indicator-agent/` — LLM 衍生指标 Agent

把 ① 的 IV / LR 挖掘结果"翻译"成符合元表 schema 的衍生指标设计稿，5 步流水线：

| Step | 职责 | 是否调 LLM |
|---|---|---|
| ① 候选筛选 | 从 results/ + 元表 + 字段清单挑 seeds | 否 |
| ② LLM 提案 | 写指标名、口径、计算公式 | **是** |
| ③ 校验 | 命名、去重、语义校验 → review packet | 部分 |
| **闸口 1** | 人审 sentinel：`touch APPROVED` | — |
| ④ Shadow IV | 出工单 + SQL 骨架交数仓 | 否 |
| **闸口 2** | 数仓回填 + 人审 → `STEP5_APPROVED` | — |
| ⑤ 注册 | 元表 SCD2 + CSV 快照 + delivery docx | 否 |

**与 ① 的关系**：单向只读上游（消费 `risk-feature-pipeline/data/results/{project}/`），下游写入元表后下次 ① 重跑时把 P3-观察 指标加入验证。

详细文档：`risk-indicator-agent/README.md` / `SKILL.md` / `AGENTS.md`。

### ③ `risk_feature_MCPServer/` — MCP Server

把 ① 包装成 6 个 MCP 工具，让 Claude Desktop / Cursor 等 LLM 客户端能直接调：

| 工具 | 用途 |
|---|---|
| `run_pipeline` | 异步跑完整分析，立即返回 `job_id` |
| `query_results` | 读已有结果（top-N / 分群） |
| `extract_triggers` | 异步生成客户级触碰清单 |
| `list_projects` | 列出已有项目 |
| `get_job_status` | 查异步 job 状态 |
| `list_jobs` | 列最近 jobs |

启动：`RISK_PIPELINE_ROOT=/path/to/risk-feature-pipeline python server.py`（默认 stdio transport）。

### ④ `handbook/` — HonKit 文档手册

把仓库内分散的 `README.md` / `SKILL.md` 聚合成一本可浏览 / 可导出的手册：

```bash
cd handbook
npm install
npm run serve           # 本地预览（http://localhost:4000）
npm run build           # 静态站点 → handbook/_book/
npm run pdf             # 导出 PDF（需 Calibre）
npm run docx            # 导出 DOCX（需 pandoc）
```

合并顺序由 `handbook/scripts/export-order.txt` 控制，新增/删除章节时改这个文件。

### ⑤ `uci_acceptance_test/` — 端到端验收

用 UCI Credit Card 公开数据集（30000 行 × 25 列，违约率 22.12%）跑通 ① 的 5 个核心命令（prepare / analyze / export / query / trigger），适合：

- 本地环境装好后做"冒烟"
- 改了 ① 的关键代码后做回归
- 给新同事演示完整数据 → 结果链路

入口：`uci_acceptance_test/README.md`，从 `source setup.sh` 开始按章节顺序执行即可。

---

## 六、典型工作流

### 工作流 A：从原始数据到正式 Word 报告

```bash
cd risk-feature-pipeline

python -m risk_pipeline run --pipeline credit \
  --project 我的征信项目 --quiet            # ① 跑完 prepare→analyze→export

python -m risk_pipeline trigger \
  --project 我的征信项目 --use-default-features  # 客户级触碰

python -m risk_pipeline report \
  --project 我的征信项目 \
  --report-markdown ./report.md \
  --purpose internal                           # → output/docx-report/*.docx
```

### 工作流 B：分析结果 → 衍生指标元表

```bash
# 前置：工作流 A 已经产出 data/results/我的征信项目/
cd risk-indicator-agent

BATCH=$(date +%Y%m%d)_first
python -m indicator_pipeline --step 1 --batch-id $BATCH
python -m indicator_pipeline --step 2 --batch-id $BATCH    # 调 LLM
python -m indicator_pipeline --step 3 --batch-id $BATCH

# 人审 review packet → 通过后：
touch data/processed/$BATCH/APPROVED
python -m indicator_pipeline --step 4 --batch-id $BATCH    # 出工单给数仓
# 数仓回填 shadow_iv_response.json → 人审通过：
touch data/processed/$BATCH/STEP5_APPROVED
python -m indicator_pipeline --step 5 --batch-id $BATCH    # 写元表
```

### 工作流 C：在 LLM 客户端里直接驱动管线

1. 启动 ③ MCP Server，配置到 Claude Desktop / Cursor 的 MCP server 列表
2. 在对话里直接说"用 `run_pipeline` 跑分析、用 `query_results` 看 top IV"
3. Server 异步处理，返回 `job_id`，再用 `get_job_status` 轮询

---

## 七、环境与依赖

| 组件 | 关键依赖 |
|---|---|
| ① `risk-feature-pipeline` | Python 3.10+；`pandas` `numpy` `scipy` `scikit-learn` `pyyaml` |
| ② `risk-indicator-agent` | Python 3.10+；`anthropic` `rapidfuzz`；SQLite；需 `ANTHROPIC_API_KEY` |
| ③ `risk_feature_MCPServer` | Python 3.10+；`mcp>=1.0.0`；继承 ① 的依赖 |
| ④ `handbook` | Node.js + `honkit`；可选：Calibre（PDF）、pandoc（DOCX） |
| ⑤ `uci_acceptance_test` | 仅依赖 ①；UCI Credit Card 数据 |

> 各组件的精确依赖见各自的 `requirements.txt` / `pyproject.toml` / `package.json`。

---

## 八、约定与规范

- **代码与输出**：全部中文（注释、日志、CSV 表头、报告正文）
- **CSV 编码**：`utf-8-sig`（保证 Excel 直接打开不乱码）
- **数据脱敏**：客户姓名、证件号、手机号不得出现在日志或导出文件中
- **样本不足自动跳过**：低于阈值时显式记录原因，不静默降级
- **AUC 必须标类型**：`交叉验证` / `训练集-样本不足` / `训练集-CV失败`
- **Agent 行为规约**：
  - 仓库根 `CLAUDE.md`：Claude Code 项目级规约
  - `risk-feature-pipeline/AGENTS.md`：先查再跑、用 `prepare_df`、`verbose=False` + `head(N)`
  - `risk-indicator-agent/AGENTS.md`：不写 ETL、不动上游、人审闸口不可绕过

---

## 九、文档地图

| 你想看 | 文档 |
|---|---|
| 顶层综述（本文件） | `README.md` |
| 项目级 Claude Code 规约 | `CLAUDE.md` |
| 核心管线总览 | `risk-feature-pipeline/README.md` |
| 核心管线调度规则 | `risk-feature-pipeline/SKILL.md` |
| 各步骤 Skill 文档 | `risk-feature-pipeline/<step>/SKILL.md` |
| 列名 / 查询配方 / 文件布局 | `risk-feature-pipeline/risk_result_query/references/` |
| LLM Agent 总览 | `risk-indicator-agent/README.md` |
| LLM Agent 5 步路由 | `risk-indicator-agent/SKILL.md` |
| MCP 工具说明 | `risk_feature_MCPServer/server.py`（docstring） |
| 文档站点构建 | `handbook/USAGE.txt` |
| 端到端验收剧本 | `uci_acceptance_test/README.md` |

---

## 十、常见问题

**Q1：要不要每次都重跑管线才能看 top 特征？**
不需要。`python -m risk_pipeline query --project X --kind iv --top 15` 直接读磁盘上的 CSV。

**Q2：旧代码里 `from shared.pipeline import ...` 还能用吗？**
能。`shared/` 是兼容 shim，会打 `DeprecationWarning`，请尽快改为 `from risk_pipeline.pipeline import ...`。

**Q3：换银行需要改多少代码？**
通常零代码。新建 `config/my_bank.yaml` 只覆盖字段名 / 阈值差异项即可，其余自动回退默认值。

**Q4：LLM 提案出错会污染元表吗？**
不会。② 有两道人审闸口（sentinel 文件机制），不通过流水线不前进；写入元表用 SCD2 拉链，旧版本永远保留。

**Q5：`skills/` 目录是什么？**
若本地存在，是从 `anthropics/skills` 克隆的官方参考样例，**不属于本工程**，不要修改或复制其中文件。

---

## 十一、贡献与扩展

- 新增子 Skill：参考 `risk-feature-pipeline/<step>/SKILL.md` 结构（`SKILL.md` + `scripts/`）
- 新增管线：在 `risk_pipeline/pipeline.py` 里加 `run_xxx_pipeline`，在 `risk_pipeline/cli.py` 里挂 `run --pipeline xxx`
- 新增 LLM 步骤：参考 `risk-indicator-agent/step{N}_*/` 的 `SKILL.md` + `scripts/` + 闸口约定
- 新增 MCP 工具：在 `risk_feature_MCPServer/tools/` 加文件，再去 `server.py` 注册 `@mcp.tool()`

> 提交代码前请同步更新对应目录的 `SKILL.md` / `README.md`，否则 `handbook/` 聚合后会缺章。
