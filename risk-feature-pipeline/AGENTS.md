# AGENTS.md — risk-feature-pipeline 硬规矩

本文件是所有在 `risk-feature-pipeline/` 下运行的 agent 的强制行为约束。SKILL.md 负责"选什么"，本文件负责"怎么做不出错"。

**执行任何步骤前必须读完本文件。**

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
| 任何 IV > 2.0 的特征 | 标记"过拟合嫌疑"并强制排除出结论推荐 | 正常纳入结论 |

### 绝对排斥（无条件禁止，不因上下文而例外）

- **在 Bash 里 import risk_pipeline 模块直接调用**——必须走 `python -m risk_pipeline <子命令>`
- 手抄"读宽表 + merge 坏客户 + 筛特征列"逻辑——统一用 `python -m risk_pipeline prepare`
- 跨 Bash 调用依赖 Python 状态（每次 Bash 是独立进程，变量不保留）
- 整表 `print(df)` / `df.to_string()`——超过屏幕可读范围必须 `head(N)`
- 输出中出现客户姓名、客户编号、手机号任意一项
- 跳过 segment 不记录原因（必须 log "跳过：{原因}"）
- `verbose=True`（会淹没关键错误信息，默认 `verbose=False`）
- 老入口 `python -m shared --pipeline X` 仍可工作但**会打 deprecation 警告**——新代码必须用 `python -m risk_pipeline run --pipeline X`

---

## 二、结果确定性层次

结论处于哪个层次，决定了可以做什么动作、承担什么责任。

```
Level 1 — 分析结论可用（内部流转）
  达成条件：risk_export_report 完成，以下文件全部落盘：
    *_IV分析结果_全量.csv ⭐ / *_IV分析结果_分群.csv ⭐
    *_特征风险相关性.csv / *_逻辑回归系数.csv
    *_IV可信度透视表.csv / *_IV可信度诊断.csv
    *_IV值透视表.csv / *_综合特征分析结果.csv
    *_LLM报告数据.json + *_LLM_分群画像.csv
    *_audit.json ⭐（C12 机器可读自检：IV>2 过拟合 + 不稳定规则）
  注：旧名 *_IV分析结果.csv / *_IV值分析.csv 仍写一份兼容副本，下版本移除
  可做：risk_result_query 查询、人工审阅、修改后重跑
  不可做：对外交付、写入预警名单

Level 2 — 结论落到客户个体（可运营，对内不可随意撤回）
  达成条件：risk_trigger_extraction 完成，以下三张表全部写出：
    {project}_风险触碰明细_宽表.csv
    {project}_风险触碰明细_长表.csv
    {project}_触碰阈值说明.csv
  可做：推送预警名单给业务部门、客户经理使用
  不可做：修改底层宽表后不重新 extract_triggers（结果将与名单失去一致性）

Level 3 — 正式报告交付（对外不可撤回）
  达成条件：risk_docx_report 的 .docx 渲染完成并交付
  不可做：此后修改底层 CSV 而不同步重新出报告（报告与数据将失去一致性）
```

**任何 Level 1 之前的中间输出（单步 univariate/IV/LR）均属过渡态，不能作为结论引用。**

---

## 三、最小无歧义工具集与雷区

```
python -m risk_pipeline prepare    进数据的唯一合法入口
python -m risk_pipeline analyze    分析（过渡态）
python -m risk_pipeline export     落 Level 1 的唯一合法入口
python -m risk_pipeline query      读已有结果的唯一合法入口
python -m risk_pipeline trigger    客户级风险落地的唯一合法入口（→ Level 2）
python -m risk_pipeline report     LLM JSON → docx（→ Level 3）
python -m risk_pipeline visualize  生成 PNG 图表（Level 1 后；不推进 level）
python -m risk_pipeline run        全流程便捷组合（generic / credit / gsfc）
```

底层 Python API（`prepare_df` / `run_generic_pipeline` / `load_results` / `extract_triggers`）仍可在 notebook 调研、单元测试中使用；**agent 工作流必须经 CLI**。

### 各工具雷区

| 工具 | 雷区 |
|---|---|
| `prepare` | `--id-col`/`--target-col` 传错会静默通过但目标列语义错误；`--filter-file` 的 `exclude`/`include` 逻辑相反；首次新数据集**必须传 `--confirmed-new-dataset`**（阻断节点 1） |
| `analyze` | CLI 强制按 `univariate→iv→lr→rules` 排序；禁止 `--steps export`（export 是独立子命令）；落产物到 `data/processed/{project}/_intermediate/`（过渡态）。**要做决策树/规则/指标组合可视化，必须 `--steps univariate,iv,lr,rules`** —— rules 步骤会拟合树并把 pkl + 规则 pkl 落 `_intermediate/`，`export` 阶段会自动把规则表写到 `data/results/<project>/<project>_风险规则表.csv`。**`--steps rules` 单跑时 `--category-dims` 必须是前置 analyze 已用维度的子集**（不允许引入新维度，否则与 `_intermediate/` 中已落盘的 corr/iv_group/lr 维度错位，CLI 会直接 SystemExit 并提示"不在前置维度中"） |
| `export` | 必须先有 `_intermediate/`；产出 8 张 CSV + LLM JSON + 推进到 Level 1 |
| `query` | 读的是**磁盘快照**——上游重跑后若不重新跑，查询到的是旧结果；`--sign positive` 在坏客户定义反转的项目中方向反转 |
| `trigger` | **必须传 `--confirmed`**（阻断节点 2）；`--use-default-features` 是通用配置，项目专属特征必须 `--features-file` |
| `report` | `--purpose external` **必须传 `--confirmed-final-version`**（阻断节点 3）；title 由 purpose 自动选择 |
| `run --pipeline credit/gsfc` | 不可中段独立调用（state.json 黑盒一项）；不接受 `--wide` 等 generic 参数；`--steps` 不含 `export` 时不会推进 Level 1 |
| `visualize` | 读的是磁盘快照（与 `query` 同源），上游重跑后须重出图；中文字体缺失时只 warn 不报错（fallback 字体渲染中文会变方框）；只产面向业务报告的概览+每维度热力图，**不再出**每分群散图/决策树图/共现网络/箱形图 |

---

## 四、事实断层时的核验路径

遇到字段/文件/映射不确定时，**核验后再执行，不允许假设后继续**。

| 断层类型 | 核验方式 | 退路 |
|---|---|---|
| 字段是否存在 | 读 `df.columns` 或 CSV 表头，不猜测 | `ColumnMapper.detect_qual_cols(df.columns)` 自动推断分群维度 |
| 结果文件是否已生成 | 检查 `data/results/<project_name>/` 目录是否有 `*_IV分析结果_全量.csv`（A5 新名）或旧名 `*_IV分析结果.csv` 兼容副本 | 提示用户先跑 `risk_export_report`，不允许用空结果假装有数据 |
| 列映射是否正确 | `df.columns` 与 `config/default.yaml`/`config/column_mapping.yaml` 中的 `customer_id` / `target` 做交集验证 | 字段对不上时硬错并提示用户，不允许悄悄回退到默认列名 |

**任何情况下不允许的退路：** 假设字段存在后继续执行。错误必须在 `prepare` 阶段暴露，不能延迟到 `analyze` / `export` 内部。

---

## 四之二、配置覆盖

本仓库为单行场景，CLI **不再**接受 `--config` / `--columns-file`。需要调整阈值 / 字段映射 / IV 参数时，直接编辑 `config/default.yaml` 与 `config/column_mapping.yaml` 后重跑；prepare 时如有差异通过 `--id-col` / `--target-col` / `--bad-id-col` 直接传。

新银行 / 新数据集接入时，prepare 阶段会自动做一次列名预检：若 `column_mapping.yaml` 中的 `segment_dims` 与 `credit_category_dims` 在宽表中均 0% 命中，CLI 直接 exit 1 并列出实际列。处理方式（任选其一）：
- 编辑 `config/column_mapping.yaml`，把 `segment_dims` 改成实际列名后重跑（最常用）
- 显式给 `analyze` 传 `--category-dims <实际列名>`（仅本次有效）
- 若有意只跑全样本（无任何分群对比），加 `--skip-preflight`

如未来真要做多 YAML 切换，新加 flag 时务必同步在 `cli_commands.py` 里把它消费掉，不要再让"声明而不读"的 flag 静默吞用户输入。

---

## 五、必须物理阻断、等待人类确认的节点

以下三个节点必须**停止执行，输出确认请求，等待用户明确回复后才继续**。

### 阻断节点 1 — 首次运行新数据集之前

**触发条件：** 用户提供从未见过的宽表路径，或切换了银行/项目配置。

**阻断原因：** `id_col`、`target_col`、坏客户定义一旦跑错，后续 8 张 CSV 全部污染，无法从结果层面发现。

**必须确认：**
- [ ] 主键字段名（默认 `客户编号`，实际是？）
- [ ] 坏客户标签列名与定义（1=坏客户还是其他？）
- [ ] 是否需要 `filter` 排除某些企业规模/行业

---

### 阻断节点 2 — extract_triggers 使用非默认 features 配置时

**触发条件：** 用户要求触碰提取，但项目专属特征集与 `RISK_FEATURES_GSFC`（默认特征别名 `RISK_FEATURES`）存在差异，或用户未明确表态用默认。

**阻断原因：** 触碰阈值计算的特征集错误会直接导致预警名单错误，是可运营决策的上游，一旦推送给业务部门不可撤回。**A1 后**默认特征仅适配 GSFC（工商财务）主题；其它主题（征信/舆情/generic）若误用默认会被匹配率守门拦下（< 50% 抛 RuntimeError），不会输出全 0 名单——但仍要求 agent 在阻断节点显式确认。

**必须确认：**
- [ ] 当前数据是否 GSFC 主题？是 → 可用默认 `RISK_FEATURES_GSFC`；否 → 必须 `--features-file`
- [ ] 如用专属列表，请用户确认 `features=` 参数中每个特征的 `risk_direction` 和 `iv`

---

### 阻断节点 3 — risk_docx_report 生成之前（Level 3 临界点）

**触发条件：** 用户要求"生成正式报告/Word 报告"。

**阻断原因：** `.docx` 一旦生成并交付，报告与底层数据的一致性承诺即成立；此后修改 CSV 须同步重新出报告，否则存在数据与报告不一致的合规风险。

**必须确认：**
- [ ] 当前的 `*_LLM报告数据.json` 是最终版本（无数据更新计划）？
- [ ] 报告用途（内部传阅 vs 对外交付）？

---

## 六、CLI 模板

### 模板 A — 跑链路（全流程 / 单维快路径）

**全流程 generic（最常用）**：
```bash
python -m risk_pipeline run --pipeline generic \
  --wide data/raw/<宽表>.csv \
  --bad-customer data/raw/<坏客户清单>.csv \
  --id-col 客户编号 --target-col is_bad \
  --project <项目名> \
  --confirmed-new-dataset      # 首次跑该数据集时必带
```

**单维快路径**（CLI 直接接受 `--category-dims`）：
```bash
# 已有 prepared.csv（之前 run 过）
python -m risk_pipeline analyze \
  --project <项目名> \
  --steps univariate,iv,lr \
  --category-dims 企业规模 \
  --qual-dims ""               # 空字符串 = 不算资质标签

python -m risk_pipeline export --project <项目名>
```

**带规则挖掘的全流程一把梭**（推荐；run 内部已串好 prepare→analyze→export）：
```bash
python -m risk_pipeline run --pipeline generic \
  --wide data/raw/<宽表>.csv \
  --bad-customer data/raw/<坏客户清单>.csv \
  --id-col 客户编号 --target-col is_bad \
  --project <项目名> \
  --steps univariate,iv,lr,rules \
  --confirmed-new-dataset

# 出图（可视化是独立 Level-1-后步骤，不在 run 中）
python -m risk_pipeline visualize --project <项目名>
```

**何时不用 `run` 一把梭，而拆三步**：
- 想在 analyze 跑完后人工核对 `_intermediate/` 里的 IV/LR 中间结果再决定是否 export
- 想换不同 `--category-dims` / `--qual-dims` 反复 analyze（数据已 prepare 过一次）
- prepare 阶段 filter 复杂，需要分阶段调试

```bash
# 拆三步版本（分阶段调试用）
python -m risk_pipeline analyze \
  --project <项目名> \
  --steps univariate,iv,lr,rules \
  --category-dims 企业规模

python -m risk_pipeline export --project <项目名>
python -m risk_pipeline visualize --project <项目名>
```

**复杂 filter / exclude_features 用 JSON 文件**（避免 shell 转义）：
```bash
echo '{"企业规模": {"exclude": ["0"]}}' > /tmp/filter.json
echo '["授信总金额", "表内授信余额"]' > /tmp/exclude.json
python -m risk_pipeline prepare --wide ... --bad-customer ... \
  --id-col 客户编号 --target-col is_bad --project <项目名> \
  --filter-file /tmp/filter.json \
  --exclude-features-file /tmp/exclude.json \
  --confirmed-new-dataset
```

同一组 `--filter-file / --exclude-features-file / --bad-id-col` 以及 C15 拆分确认三件套（`--confirmed-id-col / --confirmed-target-col / --confirmed-target-positive`）也可直接传给 `python -m risk_pipeline run --pipeline generic`，不必拆成 prepare→analyze→export 三步：
```bash
python -m risk_pipeline run --pipeline generic \
  --wide data/raw/<宽表>.csv --bad-customer data/raw/<坏客户清单>.csv \
  --id-col 客户编号 --target-col is_bad --project <项目名> \
  --filter-file /tmp/filter.json \
  --exclude-features-file /tmp/exclude.json \
  --confirmed-new-dataset
```

### 模板 B — 读已有结果（不重跑链路）

```bash
# 全量 IV top 15
python -m risk_pipeline query --project <项目名> --kind iv --top 15

# 分群 LR 正向系数 top 15
python -m risk_pipeline query --project <项目名> \
  --kind lr --dim 企业规模 --group 小型企业 \
  --top 15 --sign positive

# 分群相关性 top 15
python -m risk_pipeline query --project <项目名> \
  --kind corr --dim 企业规模 --group 小型企业 --top 15

# 输出格式：table（默认）/ csv / json
python -m risk_pipeline query --project <项目名> --kind iv --top 15 --output-format csv
```

**速查捷径**：横向对比同一特征在多个分群下的 IV，**直接读 `_IV值透视表.csv`** —— 行 = 分群名称，列 = 特征名，值 = IV，一眼能看完，比写 query 反复传 `--dim/--group` 更快。

```bash
# 看 IV 透视表（行=分群, 列=特征）
head -1 data/results/<项目名>/<项目名>_IV值透视表.csv | tr ',' '\n' | head -20
```

### 模板 C — 触碰提取（须先过阻断节点 2）

```bash
# 默认 RISK_FEATURES_GSFC 配置（用户已确认数据为工商财务主题）
python -m risk_pipeline trigger --project <项目名> \
  --use-default-features --confirmed

# 项目专属特征配置（用户已确认每个特征的方向和 IV）
python -m risk_pipeline trigger --project <项目名> \
  --features-file project_features.json --confirmed
```

`project_features.json` 必须是 JSON 数组，每条特征至少含：
```json
[
  {"report_name": "feat_name", "source_col": "源列名",
   "risk_direction": "positive|negative", "iv": 0.5,
   "category": "分类", "scope": "full"}
]
```

### 模板 D — 生成 Word 报告（→ Level 3，须先过阻断节点 3）

```bash
# internal 用途（内部审阅）
python -m risk_pipeline report --project <项目名> \
  --report-markdown <已写好的 md 报告.md> \
  --purpose internal

# external 用途（对外交付）必须额外加 --confirmed-final-version
python -m risk_pipeline report --project <项目名> \
  --report-markdown <已写好的 md 报告.md> \
  --purpose external --confirmed-final-version
```

---

## 七、日志规范

- 每个跳过的 segment 必须 log：`"[跳过] {segment_name}：{原因}（样本={n}，坏客户={n_bad}）"`
- AUC 必须附注类型：`交叉验证` / `训练集-样本不足` / `训练集-CV失败`
- IV 可信度标注：`可信` / `参考` / `不可信-样本不足` / `不可信-过拟合嫌疑`
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
  - `iv_overfit_features` 列表中的特征是否已标「过拟合嫌疑」且排除出结论推荐
  - `unstable_rules` 列表中的规则是否未直接写进政策（已附人工复核标注）
- [ ] segment 跳过是否每条有原因 log
- [ ] 输出是否含客户姓名/编号/手机号（必须 0）
- [ ] 末尾是否附了 CLI status stamp（最后一行 `[<cmd>] OK | ...`）
