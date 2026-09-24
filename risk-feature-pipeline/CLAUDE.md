# CLAUDE.md — risk-feature-pipeline 开发约定

仓库根 `CLAUDE.md` 已覆盖架构、入口、配置、路径与测试命令；agent 的操作硬规矩见本目录 `AGENTS.md`。
本文件只补充**在本目录改代码时**必须遵守的约定。设计与迁移史见 `docs/DECOUPLING-DESIGN.md`，
逐项变更见 `CHANGELOG.md`。

## 改动前后

- 基线：`ruff check . && python -m pytest -q` 全绿后再动手；提交前再跑一次，用例只增不减。
- 改变产物数值或列名 = 行为变更：补回归测试，并在 `CHANGELOG.md` 记一个代号（A/B/C/D/E 系列）。
- 对外界面冻结：`python -m risk_pipeline <子命令>` 的命令与 flag 语义、产物文件名与列名。确需改动时同步
  `references/cli/*.md`、`docs/SCHEMA.md` 与 CHANGELOG。

## 放哪儿、怎么 import

| 要做的事 | 落点 |
|---|---|
| 路径、配置常量、磁盘契约（列名/dtype/白名单/文件名模板/wire schema）、缺失值口径 | `risk_core/`（叶子，不得 import 任何上层） |
| 分析算法、Level 状态机、导出装配、generic 编排 | `risk_mining/analysis`、`pipeline_state`、`export`、`pipeline`（只依赖 risk_core） |
| 新 CLI flag | `risk_mining/argspec.py` 单一注册表声明一次，并在对应 `commands/<cmd>.py` 中读取；run 会自动继承 prepare∪analyze 的 flag |
| 新子命令逻辑 / 需要同时调用内核与子 skill | 组合根 `risk_mining/commands/` |
| 独立子 skill 的功能 | 该 skill 的 `scripts/`，只依赖 `risk_core` |

- 子 skill 读写的磁盘契约先固化进 `risk_core/contracts.py`，写端与读端都引用它，不各自手拼文件名/列名。
- 不写 `risk_pipeline.*` / `shared.*`（兼容 shim），不在模块顶层 `sys.path.insert`，不用 `os.getcwd()` / `__file__` 找数据路径。
- 分层红线由 `tests/test_unit_kernel_boundary.py` 与 `tests/test_unit_skill_independence.py` 检查（含
  `importlib.import_module('risk_x…')` 这类字符串导入），红了就是放错了层，不要改测试放行。

## 不能碰的

- **credit / gsfc 黑盒链路**（`risk_legacy_chains/` 及其调用的 `risk_segment_univariate` 等老实现）：用户决定保留原口径，
  数值由 `tests/test_golden_legacy_chains.py` 钉死。共享函数加新口径时用参数区分（如 `missing_policy=MISSING_POLICY_LEGACY_ZERO`），
  不要让老链路的 golden 值漂移。
- **阻断节点**（新数据集确认 / trigger 特征确认 / external 报告终版确认）与 Level 单向推进规则：见 `references/blocking-gates.md`、`references/levels.md`。
- **配置不支持运行时覆盖**（单行场景，已决）：不要加 `--config` / 覆盖文件入口。

## 调试顺序

错误落在链路哪个阶段 → 函数签名与参数透传 → 用 `df.columns` 核对列真实存在（不猜列名）。
