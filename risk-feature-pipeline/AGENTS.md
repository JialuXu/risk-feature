# AGENTS.md — risk-feature-pipeline 硬规矩

本文件是所有在 `risk-feature-pipeline/` 下运行的 agent 的强制行为约束。SKILL.md 负责"选什么"，本文件负责"怎么做不出错"。

**执行任何步骤前必须读完本文件。** 命令模板、阻断节点全文、Level 定义、路径 env
细节已拆到 [`references/`](references/_index.md) **按任务懒加载**——先看
`references/_index.md` 知道自己该读哪张卡，不要全读。

---

## 一、绝对触发 / 绝对排斥

### 绝对触发（条件成立时，必须且只能走这条路）

| 用户意图信号 | 必须触发 | 禁止替代 |
|---|---|---|
| "查/读/看/解读/top X/已有结果" | `python -m risk_pipeline query` | 重跑链路 |
| 提供宽表路径 + 坏客户路径 | `python -m risk_pipeline prepare` | 手写合并代码 / 在 Bash 里手抄 Python |
| "哪些客户触碰阈值/风险预警名单/客户级扫描" | `python -m risk_pipeline trigger` | 自行写阈值判断逻辑 |
| "候选阈值/单变量阈值评审/给这几个 (分群,特征) 探阈值" | `python -m risk_pipeline explore_thresholds --pairs-file ...` | 手写 optbinning / 在 notebook 里散落跑 |
| "生成 Word/正式报告" | `python -m risk_pipeline report` | 直接输出 Markdown |
| 任何 IV > 2.0 的特征 | 标记"疑似数据穿越"并强制排除出结论推荐 | 正常纳入结论 |
| 代码目录与数据/输出目录分离（沙盒 / skill 安装模式） | 每条 CLI 用单行前缀 `PYTHONPATH=<本skill目录> RISK_PROJECT_ROOT=<数据根> RISK_OUTPUT_ROOT=<可写输出根> python -m risk_pipeline ...`（已 `pip install` 可省 `PYTHONPATH`；细节见 `references/paths-env.md`） | 直接在 skill 代码目录里跑、让产物写进代码树；报 `No module named risk_pipeline` 后去**猜**代码路径（必须用读到 SKILL.md 的真实目录） |

### 绝对排斥（无条件禁止，不因上下文而例外）

- **在 Bash 里 import risk_pipeline 模块直接调用**——必须走 `python -m risk_pipeline <子命令>`
- 手抄"读宽表 + merge 坏客户 + 筛特征列"逻辑——统一用 `python -m risk_pipeline prepare`
- 跨 Bash 调用依赖 Python 状态（每次 Bash 是独立进程，变量不保留）
- 整表 `print(df)` / `df.to_string()`——超过屏幕可读范围必须 `head(N)`
- 输出中出现客户姓名、客户编号、手机号任意一项
- 跳过 segment 不记录原因（必须 log "跳过：{原因}"）
- `verbose=True`（会淹没关键错误信息，默认 `verbose=False`）
- 为适配当前这份数据而**改写随包分发的默认配置** `risk_core/config/*.yaml`——列名差异走 `--id-col`/`--target-col`/`--category-dims`（预检拦截时加 `--skip-preflight`）；改 YAML 属开发仓库维护动作，不在分析会话内做

---

## 二、结果确定性层次（→ `references/levels.md`）

```
前置 → 过渡态 → Level 1（分析结论可用） → Level 2（落到客户个体） → Level 3（正式报告交付）
prepare   analyze    export                  trigger                   report
```

- **Level 1 之前的一切中间输出均属过渡态，不能作为结论引用。**
- 每级的达成条件（产物清单）与可做/不可做边界见 [`references/levels.md`](references/levels.md)——
  判断"能不能交付/能不能推名单"前必读。

---

## 三、最小无歧义工具集

```
python -m risk_pipeline prepare    进数据的唯一合法入口
python -m risk_pipeline analyze    分析（过渡态）
python -m risk_pipeline export     落 Level 1 的唯一合法入口
python -m risk_pipeline query      读已有结果的唯一合法入口
python -m risk_pipeline trigger    客户级风险落地的唯一合法入口（→ Level 2）
python -m risk_pipeline report     LLM JSON → docx（→ Level 3）
python -m risk_pipeline visualize  生成 PNG 图表（Level 1 后；不推进 level）
python -m risk_pipeline explore_thresholds  候选阈值探索（Level 1 后；不推进 level）
python -m risk_pipeline run        全流程便捷组合（generic / credit / gsfc）
```

底层 Python API（`prepare_df` / `run_generic_pipeline` / `load_results` / `extract_triggers`）仍可在 notebook 调研、单元测试中使用；**agent 工作流必须经 CLI**。

**每个子命令的完整模板与雷区见 `references/cli/<子命令>.md`**（先查
[`references/_index.md`](references/_index.md)），做哪个任务读哪张卡。

---

## 四、事实断层时的核验路径

遇到字段/文件/映射不确定时，**核验后再执行，不允许假设后继续**。

| 断层类型 | 核验方式 | 退路 |
|---|---|---|
| 字段是否存在 | 读 `df.columns` 或 CSV 表头，不猜测 | `ColumnMapper.detect_qual_cols(df.columns)` 自动推断分群维度 |
| 结果文件是否已生成 | 检查 `data/results/<project_name>/` 目录是否有 `*_IV分析结果_全量.csv` | 提示用户先跑 `export`，不允许用空结果假装有数据 |
| 列映射是否正确 | `df.columns` 与 `risk_core/config/default.yaml`/`risk_core/config/column_mapping.yaml` 中的 `customer_id` / `target` 做交集验证 | 字段对不上时硬错并提示用户，不允许悄悄回退到默认列名 |

**任何情况下不允许的退路：** 假设字段存在后继续执行。错误必须在 `prepare` 阶段暴露，不能延迟到 `analyze` / `export` 内部。

---

## 四之二、配置覆盖

本仓库为单行场景，CLI **不再**接受 `--config` / `--columns-file`。**适配当前这份数据一律走 flag**：主键/目标列差异传 `--id-col` / `--target-col` / `--bad-id-col`，分群维度差异传 `--category-dims <实际列名>`（预检拦截时加 `--skip-preflight` 放行）。编辑 `risk_core/config/default.yaml` / `risk_core/config/column_mapping.yaml` 属**开发仓库维护动作**（长期接入新银行/新数据源），不在分析会话内做——沙盒/skill 安装模式改它等于改写随包分发的默认配置，会污染其它数据集的运行。

新银行 / 新数据集接入时，prepare 阶段会自动做一次列名预检：若 `column_mapping.yaml` 中的 `segment_dims` 与 `credit_category_dims` 在宽表中均 0% 命中，CLI 直接 exit 1 并列出实际列（处理方式见 `references/cli/prepare.md` 雷区段）。

如未来真要做多 YAML 切换，新加 flag 时务必在组合根 `risk_mining/argspec.py` 单一注册表声明并在对应 `commands/<cmd>.py` 消费掉，不要再让"声明而不读"的 flag 静默吞用户输入。

**路径环境变量**（`RISK_PROJECT_ROOT` / `RISK_OUTPUT_ROOT`，沙盒/安装模式必设，
含读写产物的落点约定）→ 见 [`references/paths-env.md`](references/paths-env.md)。

---

## 五、必须物理阻断、等待人类确认的节点（→ `references/blocking-gates.md`）

三个节点 CLI 物理 exit 1，agent **原样转发文案、等用户明确回复**，不许替用户确认：

1. **首次新数据集**（prepare/run）→ `--confirmed-new-dataset`（或拆分三件套）
2. **trigger 生成预警名单** → `--confirmed`（默认特征仅 GSFC 主题；匹配率守门 70%）
3. **对外 Word 报告**（report `--purpose external`）→ `--confirmed-final-version`

确认清单全文与放行方式见 [`references/blocking-gates.md`](references/blocking-gates.md)。

---

## 六、CLI 模板（→ `references/cli/`）

命令模板已按子命令拆卡：跑链路见 `references/cli/run.md`（与 prepare/analyze/export 三张单步卡），
查询见 `references/cli/query.md`，触碰提取见 `references/cli/trigger.md`，
报告见 `references/cli/report.md`，出图/阈值探索见对应卡。**先查
[`references/_index.md`](references/_index.md) 决定读哪张，不要全读。**

---

## 七、日志规范

- 每个跳过的 segment 必须 log：`"[跳过] {segment_name}：{原因}（样本={n}，坏客户={n_bad}）"`
- AUC 必须附注类型：`交叉验证` / `训练集-样本不足` / `训练集-CV失败`
- IV 可信度标注：`可信` / `参考` / `不可信-样本不足` / `不可信-疑似数据穿越`
- 子命令完成后 CLI 自动打印 status stamp（agent **必须原样转发**给用户）：
  ```
  [analyze] OK | project=xxx | level=过渡态
    inputs:  data/processed/xxx/prepared.csv
             data/processed/xxx/features.json
    outputs: data/processed/xxx/_intermediate/
    steps=univariate,iv,lr
  ```
- 阻断节点触发时 CLI 自动 exit 1 + 打印对应阻断节点文案，agent 原样转发，等待用户回复。

---

## 八、响应前自检（每次发回复前过一遍）

- [ ] 已声明本次目标 Level（1 / 2 / 3）
- [ ] 用了 `python -m risk_pipeline <子命令>` 而非 Bash 里 import 模块手抄
- [ ] `prepare` 或 `run --pipeline generic` 首次新数据集是否传了 `--confirmed-new-dataset`（或 C15 拆分版三件套 `--confirmed-id-col / --confirmed-target-col / --confirmed-target-positive`）
- [ ] `trigger` 是否传了 `--confirmed`（默认/自定义 features 都要；默认 features 仅 GSFC 主题适用，其它主题用 `--features-file`）
- [ ] `report --purpose external` 是否传了 `--confirmed-final-version`
- [ ] **C12: `cat data/results/<project>/<project>_audit.json` 比照机器可读自检**：
  - `iv_overfit_features` 列表中的特征是否已标「疑似数据穿越」且排除出结论推荐
  - `unstable_rules` 列表中的规则是否未直接写进政策（已附人工复核标注）
- [ ] segment 跳过是否每条有原因 log
- [ ] 输出是否含客户姓名/编号/手机号（必须 0）
- [ ] 末尾是否附了 CLI status stamp（最后一行 `[<cmd>] OK | ...`）
