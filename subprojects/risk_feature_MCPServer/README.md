# risk-feature-pipeline MCP Server

把 `risk-feature-pipeline/` 这条 CLI skill 暴露为 MCP 工具，供 Claude Desktop / 任意 MCP 客户端调用。

## 设计：薄壳转发到 CLI

除只读查询外，所有**重活/有状态**的工具都薄壳转发到子进程 `python -m risk_pipeline <子命令>`（见 `tools/cli_runner.py`）。

**为什么不直调 Python API**：pipeline 的状态机、三个阻断节点、`_audit.json`、Level 推进，以及 generic 的 `prepare→analyze→export`（含规则挖掘）真实流程，全部承载在 CLI 层（`risk_pipeline.cli_commands`）。直调 `run_generic_pipeline` 会绕过这些守门并跑老的单体路径；而 CLI 的 `_err()` 走 `sys.exit()`，进程内直调会打穿 server。子进程让 MCP 自动继承全部保证，并与 pipeline 内部实现解耦——**CLI 才是稳定契约**。

只读工具（`query_results` / `list_projects` / `list_jobs` / `get_job_status`）仍走进程内，快且返回结构化数据。

## 安装

```bash
cd subprojects/risk_feature_MCPServer
pip install -r requirements.txt   # mcp + pandas/numpy/scikit-learn
```

子进程复用同一 Python 环境，因此 `risk-feature-pipeline/` 的依赖（optbinning、python-docx、Node 渲染器等）需已装在该环境里。

## 配置（claude_desktop_config.json）

```json
{
  "mcpServers": {
    "risk-feature-pipeline": {
      "command": "python",
      "args": ["/abs/path/to/subprojects/risk_feature_MCPServer/server.py"],
      "env": {
        "RISK_PIPELINE_ROOT": "/abs/path/to/risk-feature-pipeline"
      }
    }
  }
}
```

`RISK_PIPELINE_ROOT` 未设置时，server 会自动探测同级 / 上两级的 `risk-feature-pipeline/`。`setup()` 会据此锁定 `RISK_PROJECT_ROOT` / `RISK_OUTPUT_ROOT`，使子进程与进程内读写落在同一处（不再依赖 CWD 探测）。

## 工具速查（9 个）

| 工具 | 模式 | 转发到 | 说明 |
|---|---|---|---|
| `run_pipeline` | 异步 job | `run --pipeline generic` | prepare→analyze→export（默认含 rules）→ Level 1 |
| `query_results` | 同步 | 进程内 `load_results` | top-N；kind=`iv`/`iv_group`/`lr`/`corr` |
| `extract_triggers` | 异步 job | `trigger` | 客户级触碰名单 → Level 2 |
| `visualize` | 异步 job | `visualize` | IV/相关/LR/分群/规则/组合图 PNG |
| `explore_thresholds` | 异步 job | `explore_thresholds` | 候选规则阈值（optbinning + 五道门槛） |
| `report` | 异步 job | `report` | LLM JSON + Markdown → .docx → Level 3 |
| `list_projects` | 同步 | 进程内扫描 | 列已有项目 |
| `get_job_status` | 同步 | 进程内 | 查 job；error 时含 CLI stderr |
| `list_jobs` | 同步 | 进程内 | 最近 job 列表 |

## 异步 job 模式

链路耗时通常 5-10 分钟，超 MCP 默认超时，故重活走异步：
1. 调用 `run_pipeline` / `extract_triggers` / ... → 立即返回 `{"status":"submitted","job_id":"..."}`
2. 轮询 `get_job_status(job_id)` → `running` / `success`（含 `output_files`）/ `error`（含 CLI stderr）
3. job 状态持久化到 `~/.risk_feature_mcp_jobs/`，server 重启后仍可查；`list_jobs` 找回 job_id

## 阻断节点（继承自 CLI，job 会以 error 停下并透出提示）

- **节点 1**（`run_pipeline`）：首次新数据集需 `confirmed_new_dataset=true`，先核对 `id_col`/`target_col`/坏客户定义
- **节点 2**（`extract_triggers`）：需 `confirmed=true`；features 配错会直接污染预警名单
- **节点 3**（`report`）：`purpose=external` 需 `confirmed_final_version=true`，防终版报告与数据脱钩

## 典型流程

```text
run_pipeline(wide_path, project, id_col, target_col, confirmed_new_dataset=true)
  └─ get_job_status → success（Level 1）
query_results(project, kind="iv_group", dim="企业规模", n=15)
visualize(project)
extract_triggers(project, features_file="...generic.json", confirmed=true)   # 非 GSFC 必须用 features_file
explore_thresholds(project, pairs_file="pairs.csv")
report(project, report_markdown="report.md", purpose="internal")
```

> ⚠️ `extract_triggers` 作用于项目的 `prepared.csv`，**须先 `run_pipeline` 把同名 project 跑到 Level 1**。非 GSFC 主题（征信/舆情/generic）必须用 `features_file` 注入项目特征，否则默认 GSFC 特征匹配率不足会被阻断。

## 测试

```bash
cd subprojects/risk_feature_MCPServer
pytest                  # 全部冒烟（前台校验 / 工具注册 / scan 过滤等，均不依赖外部数据）
pytest -k validation    # 仅前台参数校验
```

端到端那条用例会在无已有项目时自动跳过。
