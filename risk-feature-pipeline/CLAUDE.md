# CLAUDE.md — 解耦重构作战手册（risk-feature-pipeline）

> **本文件是「解耦重构」专项作战手册**，供新会话直接接手执行计划。
> 通用项目结构 / 入口 / 数据路径见上层 `/Volumes/Xujl/Skill/CLAUDE.md` 与本目录 `AGENTS.md`（都会自动加载，本文件不重复）。
> **完整设计（唯一真源）：[`docs/DECOUPLING-DESIGN.md`](docs/DECOUPLING-DESIGN.md)** — 目标架构、依赖矩阵、契约层、不变量、10 阶段计划全在那里。本文件只做「怎么开工、铁律、进度」。
> 重构全部完成后本文件可删除。

---

## 0. 任务一句话

把「一个统一 CLI + 12 个靠 `import risk_pipeline.*` 焊死的子 skill」重构成 **`risk_core`（契约底座）← 挖掘内核 / 独立子 skill ← 组合根（路由+入口）** 的单向依赖结构，让大模型每个任务只加载最小上下文。**不改**：分析算法、对外 CSV/JSON 产物 schema、`python -m risk_pipeline <子命令>` 命令界面。

---

## 1. 启动检查清单（新会话第一件事）

1. 读 **`docs/DECOUPLING-DESIGN.md`** 全文（尤其 §4 目标架构、§5 契约层、§7 不变量、§9 计划）。
2. 读本目录 `AGENTS.md`（硬规矩：先查再跑、prepare_df、verbose=False、阻断节点）。
3. 确认绿色基线：`cd risk-feature-pipeline && python -m pytest -q` 应为 **196 passed**（见 §2）。
4. 从 §3「当前进度」找到下一个阶段，只做那一个阶段。

---

## 2. 绿色基线（Phase 0 已锚定）

- **196 passed，~5s**（`python -m pytest -q`），2 个无害 protobuf DeprecationWarning。
- 基线是在**当前工作树**上测的——工作树有若干**与本重构无关的既有未提交改动**（`AGENTS.md` / `SKILL.md` / `risk_docx_report/*` / `risk_pipeline/cli.py` / `config.py` 等）。
  → **开工前先把这些既有改动 commit 或 stash**，让重构的每个 commit 干净、可单独 revert。
- 每个阶段结束必须仍是 **196 passed（或更多，只增不减）**；任一用例变红 = 该阶段未完成，不许进下一步。

---

## 3. 当前进度

| 阶段 | 状态 |
|---|---|
| 0 基线存档 | ✅ 已完成（196 passed，见 §2） |
| 1 抽 `risk_core` + 立 `contracts.py` | ✅ 已完成（commit `b91c2a9`；196→**201 passed**，+5 不变量锁；6 底座+results_loader 平移，contracts.py 立 §5 单一真源，`risk_pipeline` 转模块别名 shim，2 条跨 skill import 消除；3 路对抗性审计通过） |
| 2 命令拆包 + 入口保号 | ⬜ **下一步（从这里开始）** |
| 3 `assemble_exports()` 去重 | ⬜ |
| 4 argspec 单一注册表 | ⬜ |
| 5 拆 `result_query`（样板） | ⬜ |
| 6 拆 docx_report / trigger / data_prep | ⬜ |
| 7 拆 visualization / threshold_explore | ⬜ |
| 8 references/ 懒加载文档（可并行） | ⬜ |
| 9（可选）修 state_dir 发散 | ⬜ |
| 10（可选·可砍）内核去重 | ⬜ |

> 完成一个阶段后，把对应行改成 ✅ 并一句话记结果（commit hash / 新增用例）。批次：**A(1→4) 必做 → B(5→7) 拆分 → C(8) 可并行 → D(9,10) 可选**。

---

## 4. 铁律（本重构不可违反，违反即回滚）

1. **每阶段 pytest 保持绿。** 改动前 `pytest -q` 对基线，改动后必须 ≥ 196 passed。**一个阶段 = 一个 commit = 可单独 revert。** 不做跨阶段大爆炸改动。
2. **不碰对外界面。** `python -m risk_pipeline <子命令>` 的命令、flag、`--help` 语义、8 张 CSV + LLM JSON 的列名/文件名、分析算法——全部保持不变（对照基线 `--help` 全文与产物）。
3. **shim 用「模块别名」，不是 `import *`。** 阶段 1 平移模块后，`risk_pipeline/__init__.py` 必须
   `import sys; from risk_core import paths; sys.modules['risk_pipeline.paths'] = paths`（逐子模块登记：paths/config/config_loader/column_mapper/io_utils/font_utils/results_loader + analysis.*）。
   原因：测试依赖**同一模块对象**与**私有名**（如 `tests/test_unit_cli_roots_stamp.py:18` 的 `paths._warned_no_data_dir.clear()`），`import *` 覆盖不到，会红。验证 `import risk_pipeline.paths is risk_core.paths`。
4. **两条 grep 红线**（拆分完成的硬验收）：
   - 挖掘内核 `risk_mining/{analyze,export,analysis,pipeline_state}` **不得** `import risk_<任何子skill>`。
   - `risk_*/scripts/` **不得**出现跨子 skill import（当前有 2 条：`visualize.py:20`、`threshold_explore.py:29` 依赖 `result_query`——阶段 1 把 `load_results`+`Results` 升 `risk_core` 后消除）。
5. **不变量零破坏**（详见设计文档 §7）：Level 状态机单向推进、3 个物理 `exit 1` 阻断节点、路径优先级 `env>入参>探测data/>CWD` + **`RISK_OUTPUT_ROOT` 须在首次 `import config` 前设置**（config 路径常量是 import-time 冻结）、`_intermediate` wire format、指纹 `schema_version=2` 向后兼容、原子落盘、**credit/gsfc 黑盒不可拆**。
6. **契约先行（P6）：** 拆某个子 skill 前，先把它读/写的磁盘契约固化进 `risk_core/contracts.py`（列名白名单、dtype、文件名模板、键集合），再拆。写点与读点分属不同 skill 后，靠 contracts 兜住。
7. **中文输出**、CSV `utf-8-sig`、跳过分群要显式记原因、AUC 标类型——沿用既有编码规范（见上层 CLAUDE.md）。

---

## 5. 每阶段标准工作流

```
1. 读 docs/DECOUPLING-DESIGN.md §9 对应阶段那一行（改什么/为什么/如何验证/回滚点）
2. git 确认工作树干净（既有改动已 commit/stash）
3. 做该阶段改动（外科手术，只动该阶段涉及的文件）
4. python -m pytest -q         # 必须 ≥ 196 passed
5. 按该阶段「验证」列补/跑新增用例（如三链路 schema 一致、prepared dtype 往返、grep 红线）
6. 对照基线：python -m risk_pipeline --help 逐字未变；一次 run --pipeline generic 产物未变
7. 单独 commit（信息写明阶段号 + 做了什么）
8. 回本文件 §3 把该阶段标 ✅
```

调试顺序（沿用 SKILL.md）：错误落在 pipeline 哪个阶段 → 函数签名/透传 → `df.columns` 核对列真实存在（不猜）。

---

## 6. 高频坑 + 一个必修的真 bug

- **阶段 1 最易翻车点**：shim 不用模块别名（见铁律 3）；`results_loader._SKILL_ROOT` 写死 `parent×3`，移进 `risk_core/` 后层级变了要改成「向上找含 `data/` 或 `risk_core/` 的目录」。
- **阶段 2 别漏入口保号**：`risk_pipeline/__main__.py` 转发 `risk_mining.cli:main`；`pyproject.toml` 的 `packages.find` 增 `risk_core*/risk_mining*`、`[project.scripts]` 改 `risk_mining.cli:main`。
- **阶段 3**：credit 补 `target_col` 是**一致性对齐**（非行为修复）；新增用例必须**真跑 credit+gsfc+generic 三链路**，否则 credit 分支零覆盖。
- **阶段 4**：run 复用 prepare∪analyze 的 flag 要**按 option-string 去重、`required` 一律降 False、`--steps` 保留 run 专属 `...,rules` 默认**，否则 argparse dest 冲突。
- **阶段 6 必修真 bug（§5.1）**：`prepared.csv` 主键写盘是 str、读回无 `dtype` → 前导零丢失 → trigger 与宽表 0 命中 → **全 0 预警名单**。用 `contracts.read_prepared/write_prepared(dtype={id_col:str})` 修掉，加往返用例。

---

## 7. 关键文件地图（重构涉及）

| 现状文件 | 行数 | 重构去向 |
|---|---|---|
| `risk_pipeline/cli_commands.py` | 1382 | 拆入组合根 `commands/*.py`（阶段 2）|
| `risk_pipeline/cli.py` | 280 | 组合根 `cli.py` + `argspec.py`（阶段 4）|
| `risk_pipeline/pipeline.py` | 976 | 三处 export 段改调 `assemble_exports()`（阶段 3）；旧 `main()`（:858）阶段 10 转调 |
| `risk_pipeline/cli_io.py` | 196 | wire/指纹函数 → `risk_core/contracts.py`（阶段 1）|
| `risk_pipeline/pipeline_state.py` | 234 | → `risk_mining/`（状态机留内核）|
| `risk_pipeline/{paths,config,config_loader,column_mapper,io_utils,font_utils}.py` | — | 平移 `risk_core/`（阶段 1）|
| `risk_result_query/scripts/results_loader.py` | — | `load_results`+`Results` 升 `risk_core/results_loader.py`（阶段 1）|

---

## 8. 完成定义

- 批次 A 完成 = CLI 界面零变化，但 flag/导出/契约已单一真源，pytest ≥ 196 绿。
- 批次 B 完成 = 6 个独立子 skill 只依赖 `risk_core`，两条 grep 红线通过。
- 全部完成 = 挖掘内核只剩 analysis+analyze+export+状态机；LLM 每任务必读上下文按 `references/_index.md` 懒加载（设计文档 §8 的前后对照达标）。

---

*执行以 `docs/DECOUPLING-DESIGN.md` §9 为准；本文件只是每次开工的操作入口与红线提醒。*
