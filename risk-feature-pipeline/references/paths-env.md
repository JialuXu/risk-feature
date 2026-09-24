# 路径环境变量（沙盒 / skill 安装模式必设）

路径定位的唯一权威是 `risk_core/paths.py`（旧 import 路径 `risk_pipeline.paths` 是同一模块的兼容别名），行为由两个环境变量控制：

| 变量 | 作用 | 未设置时的行为 |
|---|---|---|
| `RISK_PROJECT_ROOT` | 输入读自何处（`data/raw/...` 的根） | 自 CWD 向上找首个含 `data/` 的目录，找不到回落 CWD（带一次性 WARN） |
| `RISK_OUTPUT_ROOT` | 产物写到何处（`data/results/`、`output/` 的根） | 复用 `RISK_PROJECT_ROOT` 的解析结果 |

优先级：**env > 函数入参 > 自 CWD 探测 `data/` > CWD 兜底**。

当 skill 代码目录与用户数据目录**不是同一个目录**（典型：skill 被安装/拷贝到沙盒里，代码目录可能只读），必须在会话开始时设置一次：

```bash
export RISK_PROJECT_ROOT=<用户数据所在工作区>
export RISK_OUTPUT_ROOT=<可写的输出工作区>    # 通常与上面同值
```

## 代码位置 vs 数据位置（两件事，别混）

上面两个 env 只解决**数据/产物在哪**；`python -m risk_pipeline` 能不能跑是另一件事——取决于 `risk_pipeline` 包是否在 Python 模块搜索路径上。可导入的途径只有三种：

| 途径 | 何时成立 |
|---|---|
| CWD 恰好是 skill 代码根 | `python -m` 会把 CWD 加进 `sys.path`（开发机常态） |
| 已 `pip install`（可 `-e`）本包 | 任意 CWD 可跑，且多一个 `risk-pipeline` 控制台命令 |
| `PYTHONPATH` 包含 skill 代码根 | 沙盒未安装时的标准做法（见下） |

沙盒里 skill 往往只是**拷贝**（未 `pip install`），而数据又在别的目录——此时从数据目录跑会报 `No module named risk_pipeline`。**标准调用模板**（单行三 env，每条 Bash 都带）：

```bash
PYTHONPATH=<skill代码根> RISK_PROJECT_ROOT=<数据根> RISK_OUTPUT_ROOT=<输出根> \
  python -m risk_pipeline run --pipeline generic --wide <绝对路径> ...
```

- `<skill代码根>` = 本 skill 的 `SKILL.md` / `pyproject.toml` 所在目录。你就是从那里读到本文档的——**用已知的真实路径，不要猜**。报 `No module named risk_pipeline` 时先核对这个值，不要去别处找代码。
- 若环境允许写入，也可一次性 `python -m pip install -e <skill代码根>`，之后任意 CWD 直接 `python -m risk_pipeline ...`（或 `risk-pipeline ...`），无需 `PYTHONPATH`。
- 每条 Bash 是新 shell：`export` 不跨命令保留，单行前缀最稳。

## 读取时序（⚠ 最易踩的坑）

- `RISK_PROJECT_ROOT` / `RISK_OUTPUT_ROOT` 均在**调用时**解析（`risk_core.paths`、
  state 目录、`risk_core.config.RESULTS_DIR*` 等路径常量都一样），Python API 里先
  import 后设 env 也生效。CLI 下推荐单行前缀：`RISK_OUTPUT_ROOT=... python -m risk_pipeline ...`。
- 写产物（export/trigger/visualize）与读产物（query/visualize/explore_thresholds/report、
  `load_results()`）都以**输出根**为准；`export --output-subdir X` 之后，读产物的
  子命令自动跟随到 `X/`（依据 state 历史里最近一次 export）。
- `--wide` / `--bad-customer` 等文件参数**按 CWD 解析，不按项目根**；
  沙盒模式建议一律传绝对路径。
- 每条 CLI 子命令启动时会打印一行 `[路径] 项目根=... 输出根=...`，
  **报结果前先核对这行**，确认产物落点符合预期。
- docx 校验脚本（可选依赖）默认找本机开发布局的兄弟目录 `skills/skills/docx`；
  沙盒中如需校验，用 `RISK_DOCX_VALIDATE_SCRIPT=<validate.py 路径>` 指定，
  未指定且不存在时自动跳过（WARN）。
