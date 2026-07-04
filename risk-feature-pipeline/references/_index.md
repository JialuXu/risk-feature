# references/ 索引 —— 按任务懒加载，别全读

> 本目录是 AGENTS.md 拆出的按需上下文（解耦重构阶段 8，DECOUPLING-DESIGN §8）。
> **AGENTS.md 常驻必读**（绝对触发/排斥、核验路径、日志规范、自检）；本目录各卡
> **只在做对应任务时读**，做 query 不要读 trigger 的卡。

## 入口约定（blessed entry）

对 agent 暴露的唯一入口是 `python -m risk_pipeline <子命令>`。部分子 skill 自带
`python -m <子skill>` 薄入口（如 `python -m risk_result_query`），**仅供人工/测试
直跑**，不是 agent 路径——不要在工作流里用它，不要纠结"用哪个"。

## 子命令 → 必读卡

| 任务/子命令 | 必读 | 视情况加读 | 无需读 |
|---|---|---|---|
| `run`（全流程） | [cli/run.md](cli/run.md) | 首次新数据集 → [blocking-gates.md](blocking-gates.md)；沙盒/安装模式 → [paths-env.md](paths-env.md)；列名预检 exit 1 → [cli/prepare.md](cli/prepare.md) 雷区段 | 其它 cli 卡 |
| `prepare` | [cli/prepare.md](cli/prepare.md) | 同上两张 | — |
| `analyze` | [cli/analyze.md](cli/analyze.md) | — | — |
| `export` | [cli/export.md](cli/export.md) | [levels.md](levels.md)（Level 1 产物清单） | — |
| `query`（查已有结果） | [cli/query.md](cli/query.md) | — | blocking/paths（只读不触发） |
| `trigger`（预警名单） | [cli/trigger.md](cli/trigger.md) + [blocking-gates.md](blocking-gates.md) 节点 2 | [levels.md](levels.md) | — |
| `report`（Word 报告） | [cli/report.md](cli/report.md) + [blocking-gates.md](blocking-gates.md) 节点 3 | — | — |
| `visualize`（出图） | [cli/visualize.md](cli/visualize.md) | — | — |
| `explore_thresholds`（候选阈值） | [cli/explore_thresholds.md](cli/explore_thresholds.md) | — | — |
| 判断"现在处于哪个 Level / 能不能交付" | [levels.md](levels.md) | — | — |
| 沙盒 / skill 安装模式跑任何命令 | [paths-env.md](paths-env.md) | — | — |

## 下钻子 SKILL 的时机

各 `risk_*/SKILL.md` 顶部有"何时读我"一行：**只有** CLI 卡覆盖不了
（要 Python API 级用法 / 该 skill 的领域细节）时才下钻，常规任务止步于 cli 卡。
