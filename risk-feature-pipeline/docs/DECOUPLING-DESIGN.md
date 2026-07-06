# risk-feature-pipeline 解耦重构设计文档

> 状态：**设计草案 v2（已过对抗性核验）** ｜ 范围：架构解耦，不含业务逻辑改动
> 关联文档：需求见 [`PRD-risk-feature-pipeline.md`](PRD-risk-feature-pipeline.md)，列/文件 schema 见 [`SCHEMA.md`](SCHEMA.md)，术语见 [`GLOSSARY.md`](GLOSSARY.md)，硬规矩见 [`../AGENTS.md`](../AGENTS.md)。本文只描述**重构目标架构与迁移路线**，不重述上述内容。
> v2 修订：依据 5 路对抗性核验（拿真实代码逐条验），修正依赖矩阵（新增"组合根/路由层"）、补齐 6 类漏掉的读契约、写实 shim/入口保号机制、订正 2 处行号数字。

---

## 0. 一句话目标

把当前"一个统一 CLI + 12 个靠 `import risk_pipeline.*` 焊在一起的子 skill"，重构成 **`risk_core`（稳定契约底座）← 挖掘内核 / 独立子 skill ← 组合根（路由 + 唯一入口）** 的单向依赖结构；挖掘内核只保留"数据挖掘"本身，其余子功能（数据准备、结果查询、可视化、触碰、阈值探索、Word 报告）成为**只依赖 `risk_core` 的独立单元**，让大模型每个任务只需加载最小上下文。

**本次重构不追求**：改分析算法、改对外 CSV/JSON 产物 schema、改 CLI 对用户的命令界面。这些是必须保持不变的**不变量**（见 §7）。

---

## 1. 背景与问题陈述

### 1.1 现状规模（实测）

| 类型 | 数量 |
|---|---|
| Python（.py，排缓存） | 120 |
| SKILL.md | 13（1 顶层 + 12 子 skill） |
| 其它文档（.md） | 43 |
| YAML 配置 | 10 |
| 测试（tests/） | 25 |
| **实质文件合计** | **149** |

核心枢纽文件：`risk_pipeline/cli_commands.py`（1382 行，9 个 `cmd_*`）、`risk_pipeline/pipeline.py`（976 行，`run_credit/gsfc/generic_pipeline`）、`risk_pipeline/cli.py`（280 行 argparse）。

### 1.2 大模型为什么在这个项目上高频出错（4 个结构性根因，均已核验到 file:line）

1. **CLI 三方对齐 + 手工 `Namespace` 透传。** `cli.py:220-258` 把同一批 flag 在 `prepare` 与 `run` 两个子解析器**各声明一遍**；`cli_commands.py:1338-1376` 的 `cmd_run` 又用手工拼装的 `argparse.Namespace` **逐字段**（prepare/analyze/export 各 19/10/6 个字段，含 quiet/verbose/state_dir）透传，全程 `getattr(args,'x',None)` 兜底。给 prepare 加一个 flag 要同步**三处**，漏一处静默变 `None` 不报错。`cli_commands.py:1349-1353` 的 C15 注释、`cli.py:242` 注释是这类 bug 的两次历史存证。

2. **导出装配 4 份平行副本。** `build_corr_export/build_comprehensive_table/build_llm_report_data` 调用序列在 `pipeline.py:258-277`（credit）、`:518-535`（gsfc）、`:728-747`（generic）、`cli_commands.py:721-738`（cmd_export）各抄一份，credit 那份漏传 `target_col`（`build_llm_report_data` 用 `df[target_col].sum()` 数坏客户）。三链路各自 `try/except` 吞异常，字段分叉在运行期静默降级。

3. **命令间"磁盘传状态"无 schema 校验、落盘根发散。** `cli_io.py:81-98` 的 `_SIMPLE_KEYS`(8)/`_WIDE_DICT_KEYS`(4) 是 analyze 产键 / dump 落盘 / load 重建的三方字符串约定，缺表一律静默 `continue`（`:119`）；落盘根在 `cli_commands.py:43-70`、`pipeline_state.py:159-166`、`config.py:43-58` 三处各自读 `RISK_OUTPUT_ROOT`；`cli_commands.py:1290` 把 credit 状态特判到 `data/results/征信/credit/`，而 `analyze/export/query` 默认落 `data/results/<project>/`（无"征信"前缀）——同一 project 的 `.pipeline_state.json` 在子命令间发散。

4. **文档每任务必读 ~26KB、无"何时下钻"信号。** `SKILL.md`（6.8KB）+ `AGENTS.md`（19.3KB）顶部都写"必读全文"，连只读 query 都被迫全量加载；意图→CLI、阻断 flag、路径 env 在 3-4 处重复，trigger 匹配率还有 50% vs 70% 自相矛盾（`AGENTS.md` 阻断节点2 vs trigger 子 SKILL）。

### 1.3 反直觉的关键发现

- **状态机耦合不在子 skill 里。** `require_level` / `pipeline_state` / `append_history` 在 12 个子 skill 的 `scripts/*.py` 中**出现 0 次**（`_intermediate` 仅 `visualize.py:4` docstring 提及一次，读取可选 pkl，非状态耦合）——它们全在 `cli_commands.py` 的 `cmd_*` 包壳层。子 skill 的"库代码"本身早已是干净的。
- **真正的焊点只有一条 import。** 每个子 skill 都 `import risk_pipeline.*`，于是任何"拆出去"的 skill 仍会把整个 `risk_pipeline`（CLI+编排+内核+状态机）拖进来。**拆分的前提是切断这条 import，而不是搬目录。**
- **`result_query` 已是事实上的公共读取器。** `risk_visualization/scripts/visualize.py:20` `from risk_result_query.scripts.results_loader import load_results, Results`；`risk_threshold_explore/scripts/threshold_explore.py:29` `import Results`——它被两个下游 skill 横向依赖。
- **推进 Level 的命令直接 import 子 skill。** `cmd_prepare`(`:164` import `risk_data_prep`)、`cmd_query`(`:819` import `result_query`)、`cmd_visualize`/`cmd_trigger`/`cmd_report` 都在推进状态的同时直接 import 对应子 skill——所以"编排/推进"与"叶子功能"当前是搅在一起的（这决定了 §4 必须引入独立的"组合根"层）。

---

## 2. 设计目标与原则

| # | 原则 | 含义 |
|---|---|---|
| P1 | **单一真源（Single Source of Truth）** | 每个约束（flag 声明、导出装配、wire schema、阻断门、阈值、列名白名单）在代码/文档里只有一处权威定义，其余全部派生或引用 |
| P2 | **依赖单向、无环** | `risk_core ← 挖掘内核 / 独立子 skill ← 组合根`；子 skill 之间**零横向依赖**；挖掘内核**不 import 任何子 skill**；`risk_core` 不反向依赖任何上层 |
| P3 | **LLM 上下文最小化** | 每个任务只需加载"该任务的 skill + core 契约"，而非全量 26KB 顶层文档 |
| P4 | **增量、每步 pytest 绿** | 无大爆炸重写；每个阶段单独可停、可回滚、可发版 |
| P5 | **不变量零破坏** | Level 状态机、三个阻断门、路径优先级与读取时序、wire format、对外 schema、原子落盘不受影响（§7） |
| P6 | **契约先行** | 拆分前先把"磁盘传状态"的隐式约定（含**读取端**列名/dtype/白名单）固化为 `risk_core` 显式契约，否则拆开后写点与读点分属不同 skill、假设漂移无处约束 |

---

## 3. 现状架构快照（依赖分层，实测）

```
┌─ LLM-facing 层 ── SKILL.md(6.8KB) + AGENTS.md(19.3KB) + 12×子 SKILL.md
│                     每任务强制全量加载，无下钻信号
├─ CLI 分发层 ───── cli.py(参数) → cli_commands.py(9×cmd_*，1382行) → pipeline.py(run_*_pipeline，976行)
│                     ⚠ 状态机/阻断门/落盘路径都在这层的壳里；cmd_* 又直接 import 子 skill
├─ 分析内核 ─────── risk_pipeline/analysis/{iv_core, engine}   ← export/iv/lr/(export_report) 复用
├─ 底座层 ───────── risk_pipeline/{paths, config, config_loader, io_utils, column_mapper, font_utils}
└─ 12 子 skill ──── 各自 scripts/，但全部 import risk_pipeline.*（焊点）
                     result_query.load_results 被 visualization/threshold_explore 横向 import
```

三个"耦合枢纽"：① `risk_pipeline` 底座（人人依赖）② `result_query.results_loader`（事实公共读取器）③ `analysis` 内核（挖掘/导出复用）。第四个隐藏问题：**编排层 `cmd_*` 与叶子子 skill 搅在一起**（推进 Level 的命令直接 import 子 skill）。

---

## 4. 目标架构

### 4.1 分层与依赖规则（v2 修正：引入"组合根/路由层"）

核验发现原矩阵的错误：推进 Level 的 `cmd_prepare/query/visualize/trigger/report` 本就直接 import 子 skill，若把它们塞进挖掘内核，内核会静态依赖 5 个子 skill、违反 P2。**修正：把"路由 + 转发 + argspec + 阻断门校验"独立成一个物理层"组合根"（composition root），它是唯一允许同时 import 挖掘内核与所有子 skill 的地方；挖掘内核本身保持纯净、不 import 任何子 skill。**

```
                      ┌──────────────────────────────────────────┐
                      │  组合根 / 路由层（唯一 blessed 入口）        │
                      │  argspec + cmd_* 转发 + require_level 阻断门 │
                      └───┬───────────┬───────────────┬────────────┘
             import ▼     │ import     │ import        │ import
         挖掘内核 ◄───────┘   子skill×6 ◄┘               │
             │  import                │  import          │
             ▼                        ▼                  ▼
         ┌──────────────────── risk_core（叶子：谁都能依赖，它谁都不依赖） ─────────────────┐
         │ paths / config / config_loader / column_mapper / io_utils / font_utils /       │
         │ results_loader / contracts（wire schema + 列名/dtype/白名单单一真源）           │
         └────────────────────────────────────────────────────────────────────────────────┘
```

**依赖矩阵（允许 = ✓，禁止 = ✗）：**

| 依赖方 ↓ \ 被依赖 → | risk_core | 挖掘内核 | 某子 skill | 组合根/路由 |
|---|---|---|---|---|
| **risk_core** | — | ✗ | ✗ | ✗ |
| **挖掘内核**（analyze/export/analysis/pipeline_state） | ✓ | — | ✗（不 import 子 skill） | ✗ |
| **独立子 skill** | ✓ | ✗ | ✗（零横向） | ✗ |
| **组合根/路由**（cli + commands + argspec） | ✓ | ✓ | ✓（转发，函数直调） | — |

要点：**"挖掘内核 → 子 skill = ✗"和"子 skill 间零横向 = ✗"是本次重构的两条硬约束**，用 §7 的 grep 红线验收。组合根是唯一的"什么都能 import"的组合点（依赖倒置的正确落法）。

### 4.2 目标目录树

```
risk-feature-pipeline/
├── SKILL.md                    # 瘦身：意图→skill/CLI 分诊表 + 3 阻断门 + 下钻指针
├── AGENTS.md                   # 瘦身：core-rules（先查再跑/prepare_df/verbose=False）+ 卡片索引
├── references/                 # 【新增】按需懒加载的参考卡（LLM 下钻目标）
│   ├── _index.md               #   子命令/意图 → 必读哪张卡 / 无需读哪些 + blessed 入口约定
│   ├── blocking-gates.md       #   ← AGENTS.md:146-186（节点1/2/3）
│   ├── paths-env.md            #   ← AGENTS.md:112-145（RISK_*_ROOT + 读取时序，见 §7）
│   ├── levels.md               #   ⚠ 需新撰（无现成源，Level 1/2/3 达成条件）
│   └── cli/<子命令>.md          #   ← AGENTS.md:187-328（模板 A/B/C/D）按命令切分
│
├── risk_core/                  # 【新抽·叶子】稳定契约底座（无编排、无状态机、无算法）
│   ├── paths.py config.py config_loader.py column_mapper.py io_utils.py font_utils.py   # ← 平移
│   ├── results_loader.py       #   load_results + Results（dataclass 一并迁；修 _SKILL_ROOT 深度）
│   └── contracts.py            #   ⭐ §5 全部 wire/列名/dtype/白名单/文件名模板的单一真源
│
├── risk_mining/                # 【挖掘内核】唯一推进 Level 的地方；不 import 任何子 skill
│   ├── analysis/{iv_core, engine}.py     # 挖掘内核（不动）
│   ├── analyze.py              #   univariate/iv/lr/rules → _intermediate/
│   ├── export.py               #   assemble_exports()：唯一导出装配（内核耦合，留此）
│   ├── pipeline_state.py       #   Level 状态机（推进/校验，留内核；组合根调用它）
│   └── cli.py argspec.py commands/       # ⚠ 见下：物理上属"组合根"，可同包不同子目录
│       ├── argspec.py          #   ⭐ 每 flag 单条声明，parser 与 run 透传都派生
│       ├── cli.py              #   顶层薄 CLI：遍历 argspec 构建 + 分发/转发
│       └── commands/           #   cmd_prepare/analyze/export/run/query/visualize/trigger/report/explore
│                               #     转发命令函数直调子 skill；先 require_level 再转发
│
├── risk_data_prep/             # 独立：产出标准 prepared.csv + features.json（前置契约生产者）
├── risk_result_query/          # 独立：只读；核心读逻辑升 core，这里剩 top_features 等查询糖
├── risk_visualization/         # 独立：CSV → PNG（依赖 core.results_loader）
├── risk_trigger_extraction/    # 独立：Level 2
├── risk_threshold_explore/     # 独立：Level 1 后（依赖 core.results_loader）
├── risk_docx_report/           # 独立：Level 3（LLM JSON → Word）
│
├── risk_feature_engineering/   # 挖掘内核的输入侧算法：改依赖 risk_mining.analysis（或随 shim 保留）
├── risk_segment_univariate/    # 同上；§10 阶段收敛其与 engine 的重复 univariate_by_group
├── risk_iv_diagnosis/          # 目前是 analysis 内核的 shim：随 risk_pipeline shim 保留一个版本
├── risk_logistic_regression/   #   同上
├── risk_rule_mining/           #   规则挖掘：改依赖 risk_mining.analysis
└── risk_export_report/         # ✗ 不拆：用 IV 内核、是 export 步的实现，归 risk_mining.export 调用
```

> **6 个未在"独立子 skill"之列的目录的归宿**（核验补齐）：`risk_iv_diagnosis`/`risk_logistic_regression`/`risk_export_report` 当前是 `from risk_pipeline.analysis.* import *` 的转发 shim，随 `risk_pipeline` 兼容 shim 一并保留一个版本周期；`risk_feature_engineering`/`risk_segment_univariate`/`risk_rule_mining` 是挖掘内核的算法实现，改依赖 `risk_mining.analysis`，不作为"独立可拆子 skill"。它们的库代码不动，只跟随包名迁移。

> **包命名与入口保号**（核验补齐，属阶段 1/2 必做）：`risk_pipeline` 保留为**兼容 shim 包**——`risk_pipeline/__init__.py` 用 `sys.modules['risk_pipeline.paths'] = risk_core.paths` 式**模块别名登记**（不是 `from ... import *`，因测试依赖同一模块对象与私有名，见 §9 阶段1）；`risk_pipeline/__main__.py` 转发 `from risk_mining.cli import main`；`pyproject.toml` 的 `[tool.setuptools.packages.find] include` 增加 `risk_core*`/`risk_mining*`（保留 `risk_pipeline*`），`[project.scripts]` 目标改 `risk_mining.cli:main`。对 agent 而言 `python -m risk_pipeline <子命令>` 命令一字不变。

### 4.3 顶层路由、"唯一 blessed 入口"与 argspec 归属

- **入口策略**：顶层 `python -m risk_pipeline <子命令>` 是唯一对 agent 暴露的入口，组合根内部**用函数直调**（非 subprocess）转发到对应子 skill；子 skill 的独立 `__main__` 仅供人工/测试直接调用，**不写进面向 agent 的 SKILL.md 模板**。该约定写进 `references/_index.md`，避免 LLM 纠结"用哪个"（上一轮策略 C 评审的主要扣分项）。
- **argspec 归属（核验补齐，避免复活 C15）**：flag 声明的单一真源是组合根的 `argspec.py`。子 skill **不**重声明 flag（否则又是三方对齐）；子 skill 只暴露纯 Python 函数（现状已如此：`extract_triggers`/`load_results`/`generate_charts`/`explore_thresholds`/`build_docx_report`），组合根的 `cmd_*` 用 argspec 定义的 flag 包裹这些函数。子 skill 若需一个"薄 `__main__`"供人工直跑，允许其自带一份**最小 argparse**（少量位置参数），但它**不是** agent 路径、也不参与 argspec 的单一真源——两者互不牵连。

---

## 5. 契约层（本设计的核心交付 · v2 大幅补齐"读契约"）

拆分能否成立，取决于把下列隐式契约固化为 `risk_core/contracts.py` 的显式单一真源。**核验发现原 v1 只覆盖了"写了哪些字段"，漏掉了决定成败的"读取端"约定**（列名白名单 / dtype / 元信息集合 / 文件名模板 / 读取时序）。以下为实测的完整契约，写点与读点必须都从 contracts.py import：

### 5.1 `prepared.csv`（⚠ 含一条真潜在 bug）
- 写：`cli_commands.py:274` `to_csv(index=False, encoding='utf-8-sig')`；读：analyze(`:421`)/export(`:736`)/trigger(`:960`) 均 `read_csv(encoding='utf-8-sig')` **且无 `dtype`**。
- `prepare_df.py:113/160` 内部把主键 `astype(str)` 规避前导零；但落盘后字符串性丢失，读回被推断为数值。
- **契约**：`contracts.PREPARED_CSV = {encoding:'utf-8-sig', index:False, id_col_dtype:str}` + 唯一 `read_prepared()/write_prepared()`，读时强制 `dtype={id_col:str}`。
- **失败场景**：带前导零的客户编号经 CSV 往返变 int → trigger 与客户宽表 merge（`:986`）0 命中 → 匹配率 < 50% 抛 RuntimeError 或输出全 0 名单。拆 data_prep 独立后写/读分属不同 skill，更无处对齐——**此重构应顺手修掉它**。

### 5.2 `features.json`（15 键 + audit 子 schema）
- `cli_commands.py:283-299` 实写 15 键。下游硬读：analyze 读 `column_mapping_audit['segment_dims']['actual'/'expected']`、`['credit_category_dims']`（`:389,405`）；trigger 读 `id_col`/`target_col`（`:960+`）。
- **契约**：contracts 固化 features.json 必备键集合 + `column_mapping_audit` 子 schema + 唯一 read/write。
- **失败场景**：data_prep 独立后改 audit 键名/结构 → analyze 诊断 hint 静默失效（读取被 try 包住）；trigger 读不到 `id_col` → 回落默认列名"客户编号" → 匹配率骤降。

### 5.3 `_intermediate/`（analyze → export 唯一数据通道，`cli_io.dump/load_intermediate`）
- `manifest.json`（`schema_version=1`）：`project_name / target_col / category_dims / qual_dims / feature_cols / raw_features / derived_features / wide_dim_keys`。
- **8 个简单表**（`_SIMPLE_KEYS`）：`iv_full, iv_group_all, reliability_summary, feature_set_comparison, corr_long, lr_coef_long, lr_auc_long, comprehensive` → `{key}.csv`（`utf-8-sig`，`index=False`）。
- **4 个宽矩阵**（`_WIDE_DICT_KEYS`）：`corr_wide/corr_results`、`lr_coef_wide/lr_coef_results`、`lr_auc/lr_auc_results`、`meta/meta_results` → `{prefix}_{safe(dim)}.csv`（`utf-8-sig`，`index=True`，回读 `index_col=0`）。
- 特判：`qual_dims` 非空时 `wide_dim_keys` 追加 `'资质标签'`（`cli_io.py:184`）。
- **⚠ 核验补齐**：`load_intermediate` 返回的 results dict **不含 `target_col`**（`cli_io.py:169-176`）；`target_col` 只在 `manifest.json`（export 从 `:754` `manifest.get('target_col')` 单独取）。**契约**：任何 `_intermediate` 消费方必须同时读 manifest，不能只吃 results dict——否则 `target_col` 静默回落 `is_bad`，坏客户计数/LLM 报告算错不报。

### 5.4 对外 results 产物（列名 = 跨 skill 读契约，⚠ 核验重点补齐）
- 通用三列：`特征 / 分群维度 / 分群名称`。
- **元信息列白名单（新增单一真源）**：`results_loader._KNOWN_META_COLS`（reader，`:118-122`）与 `build_corr_export`（writer，`report_analysis.py:1037` 写 `['分群维度','分群名称','样本数','坏客户数','坏客户率']`）、`build_lr_export`（`:1063` 写 `['分群维度','分群名称','AUC','AUC类型','样本数','坏客户数']`）是**两份独立拷贝**，当前恰好对齐但无约束。**契约**：contracts 固化 `CORR_EXPORT_META_COLS`/`LR_EXPORT_META_COLS`，writer（mining）与 reader（core）都 import。**失败场景**：export 新增一列（如"好客户数"）未同步白名单 → `_melt_wide_to_long`（`:125-156`）把它当特征列 → query/visualization 的 top-N 混入伪特征且不报错。
- **完整列名常量表（新增）**：`top_features`/透视表硬依赖 `IV值`(`:306/316`)、`|相关系数|`/`相关系数`(`:326`)、`系数`(`:340`)、`AUC`/`AUC类型`/`样本数`/`坏客户数`(`:163-169`)、`IV可信度`（`report_analysis.py:608` `=='可信'`、`:180-182` 透视表）。**契约**：contracts 增一张完整列名常量表，query/visualization/export 全部引用。**失败场景**：export 改任一列名 → query 路径 KeyError 或 melt 静默漏列 → 用户拿到空 top-N 无告警。
- **三链路一致**：credit/gsfc/generic 必须产出同一套列名/文件名——`load_results/visualize/query` 的读取前提。

### 5.5 数据集指纹（`cli_io.dataset_fingerprint`，`schema_version=2`）
- `sha256_head(256KB) + sha256_tail(256KB) + size_bytes + mtime`；`pipeline_state._fingerprint_matches`（`:29-49`）需同时兼容老格式（`sha256_first_1mb + size_bytes`）。

### 5.6 `.pipeline_state.json`（`pipeline_state.py`，⚠ 派生全文补齐）
- 内容：`project_name / current_level / known_datasets / history`；原子落盘（`tmp(PID+time_ns)→fsync→os.replace→flock`）；append-only；不入 git。
- **目录派生全文**（`_resolve_state_dir` `:159-166`）：设 `RISK_OUTPUT_ROOT` 时 `get_output_root()/data/results/{project}`，否则 `project_root/data/results/{project}`，**均无"征信"前缀**；而 credit 结果目录带"征信"前缀（`config.RESULTS_DIR_CREDIT`）、`cmd_run` credit 分支 state 又特判到 `data/results/征信/credit/`（`:1290`）。**契约**：contracts 固化 state_dir 派生函数全文，并标注 credit/gsfc 前缀发散为**已知偏差**（对应 §9 阶段 9 修复）。

### 5.7 配置 / YAML 语义 + 产物文件名（新增）
- **YAML 覆盖语义**（`config_loader.py:30-42`）：`_deep_merge` 对 dict 递归深合并、对 **list 整体替换**（非并集）；`:19-27` `_expand` 对所有字符串值做 `expandvars + expanduser`（`${VAR}`/`~` 加载时展开）。**契约**：写进 contracts/references，防止多银行用户覆盖 list 型配置（如 `credit_raw_features`）时误以为并集。
- **产物文件名模板**：`{project}_{type}.csv` 全表 + `_intermediate/rule_tree_*.pkl`（`cli_commands.py:560` 产物，visualization 读）+ pair-list / `_audit.json` schema（threshold_explore 读）。visualization/threshold_explore 除走 `results_loader` 外还**直接按文件名拼读**（`visualize.py:_load_rules_csv`、`threshold_explore/io_utils.py`），故文件名模板须为单一真源。

> **归属**：5.1–5.7 全部迁入 `risk_core/contracts.py`（schema 常量 + 白名单 + 读写函数），`risk_mining` 与各子 skill 只从这里 import，杜绝各处自拼键名/列名/路径。

---

## 6. 拆分可行性矩阵（实测依赖 → 结论）

| 子功能 | 依赖 `risk_pipeline.*` | 碰状态机 | 用内核 | 横向依赖 | 结论 |
|---|---|---|---|---|---|
| **结果查询** result_query | 仅 `paths` | 否 | 否 | 无 | ★ 最易，几乎已独立（3 py），**首拆样板** |
| **docx 报告** docx_report | 仅 `paths` | 否 | 否 | 无（无真实 import） | ★ 最易，干净可拆（5 py） |
| **触碰提取** trigger | `config`+`paths` | 否 | 否 | 无 | ★★ 易，自带 features 配置 |
| **数据准备** data_prep | `config`+`io`+`paths` | 否 | 否 | 无 | ★★ 易，但**输出即契约**（§5.1/5.2），须先立 contracts |
| **阈值探索** explore_thresholds | `config` | 否 | 否 | `result_query.Results` | ★★★ 中，需 loader 先升 core |
| **可视化** visualization | `config`+`font`+`paths` | 读1处 | 否 | `result_query.load_results` | ★★★ 中，同上 + 直接读文件名（§5.7） |
| **CSV 导出（export 步）** export_report | 底座 + **`analysis` 内核×3** | 壳层 | **是** | 无 | ✗ **不拆**：用 IV 内核（`calc_iv`/`_assess_iv_reliability`/`iv_power_label`/`_adaptive_bins`）且是 Level-1 推进步，归 `risk_mining.export` |

> ⚠ **"报告导出"拆两半**：`docx_report`（JSON→Word）干净可拆；`export_report`（`_intermediate/`→8 CSV，→ Level 1）用挖掘内核、是核心下游步，**留在 `risk_mining`**。拆它只是把内核缝挪位，风险大、无收益。

---

## 7. 迁移全程绝不能破坏的不变量

| 不变量 | 契约 | 验收方式 |
|---|---|---|
| **Level 状态机单向推进** | 前置→过渡态→Level1→Level2→Level3；`_maybe_promote` 只升不降；partial `--steps` 不谎报 Level 1 | 现有 state 单测 |
| **三个阻断节点物理 `exit 1`** | 节点1（`--confirmed-new-dataset`/拆分三件套 + `_validate_split_confirmation`）、节点2（trigger `--confirmed`）、节点3（report external `--confirmed-final-version`）；组合根转发前校验，直调子 skill 路径不兜此门 | validation 单测 |
| **挖掘内核不 import 子 skill** | `analyze/export/analysis/pipeline_state` 中 grep 无 `import risk_<skill>` | **grep 红线**（新增） |
| **子 skill 零横向 import** | `risk_*/scripts/` 中 grep 无跨子 skill import | **grep 红线**（阶段 7 验收） |
| **路径优先级 + 读取时序** | `env > 入参 > 探测 data/ > CWD`；裸 `os.getcwd()/__file__` 只允许 `risk_core/paths.py` 一处；**且 `RISK_OUTPUT_ROOT` 须在首次 `import config` 前设置**——config 路径常量是 import-time 冻结（`config.py:43-58`），paths/state 是 call-time 实时（`paths.py:81`/`pipeline_state.py:164`） | paths 单测 + 新增时序用例 |
| **`_intermediate` wire format** | §5.3 全部键名 + `utf-8-sig` + 宽表 `index` 往返 + `'资质标签'` 特判 + `target_col` 仅在 manifest | export smoke |
| **对外 schema 一致 + 读契约** | §5.4 三列 + 元信息白名单 + 完整列名常量，三链路同一套 | 新增三链路 schema 用例 |
| **原子落盘 + 指纹向后兼容** | §5.5/5.6，`schema_version=2` 与老格式并存 | 指纹用例（红线） |
| **credit/gsfc 黑盒不可拆** | `run_*_pipeline` 无中间落盘，不得拆成三段 | legacy smoke |

---

## 8. LLM 每任务必读上下文：解耦前 vs 解耦后

| 任务 | 解耦前 | 解耦后 | 改善 |
|---|---|---|---|
| 只读 query | SKILL 6.8KB + AGENTS 19.3KB ≈ **26KB** | SKILL 4KB + `_index` + `cli/query.md` ≈ **7KB** | **−73%** |
| 首跑 generic（带阻断） | ≈26KB + 可能下钻子 SKILL | 4KB + `_index` + `cli/run.md` + `blocking-gates.md` + `paths-env.md` ≈ **12KB** | **−54%** |
| 非 GSFC trigger | ≈26KB + trigger 子 SKILL（含 50/70 矛盾） | 4KB + `cli/trigger.md`（单一阈值） | **−60%** |
| 加 prepare flag（代码侧） | 改 2 处手工点，漏则静默 None | 改 `argspec.py` 1 处 | 结构性根除 |
| 改导出 schema（代码侧） | 改 4 份副本 + 白名单/列名常量另有拷贝，漏则分叉被吞 | 改 `assemble_exports()` + `contracts.py` 各 1 处 | 结构性根除 |

---

## 9. 分阶段实施计划（Plan · v2 已按核验补齐规避动作）

> 基线（阶段 0）：`cd risk-feature-pipeline && pytest` 全绿存档；记录 `--help` 全文、一次 `run --pipeline generic` 的 state/CSV 产物、grep 统计（阻断 flag / 意图→CLI 表 / 50-70 字面量位置）。每阶段以此为 checkpoint。

| 阶段 | 目标 | 关键动作（含核验补齐的规避点） | effort | risk | 验证（pytest 保持绿） | 回滚点 |
|---|---|---|---|---|---|---|
| **0** | 基线存档 | 见上 | 低 | — | — | — |
| **1** | **抽 `risk_core` + 立 `contracts.py`** | 底座 6 模块 + `results_loader`（含 `Results` dataclass）平移进 `risk_core`；§5 契约固化为 `contracts.py`。**shim 用模块别名**：`sys.modules['risk_pipeline.paths']=risk_core.paths` 逐子模块登记（清单：paths/config/config_loader/column_mapper/io_utils/font_utils/results_loader + analysis.*），保证 `import risk_pipeline.paths` 与 `risk_core.paths` 是**同一对象**、私有名（如 `paths._warned_no_data_dir`）可达。**修 `results_loader._SKILL_ROOT`**：由写死 `parent×3` 改为向上找含 `data/` 或 `risk_core/` 的目录 | 中 | 中 | 全量 pytest 逐用例一致（重点：`test_unit_cli_roots_stamp.py:18` 私有名、20 个测试的 `from risk_pipeline.* import`）；`import risk_pipeline.paths is risk_core.paths` | 单 commit revert |
| **2** | **命令拆包 + 入口保号（零行为变更）** | `cli_commands.py`(1382) 的 9 `cmd_*` + helper 搬进组合根 `commands/*.py`；原文件降 re-export。**入口保号**：`risk_pipeline/__main__.py` 转发 `risk_mining.cli:main`；`pyproject.toml` packages.find 增 `risk_core*/risk_mining*`、`[project.scripts]` 改 `risk_mining.cli:main` | 低 | 低 | pytest 逐用例一致；`--help` 逐字不变；`python -m risk_pipeline --help` 正常 | revert 回单文件 |
| **3** | **`assemble_exports()` 去重** | 4 份导出装配收敛为 1（`risk_mining/export.py`）；credit **补 `target_col`（一致性对齐，非行为修复）**；`build_comprehensive_table` 的 `raw_features/derived_features` 默认 `[]` 以逐字保住 credit/gsfc 行为 | 中 | 低-中 | 新增用例**真跑 credit+gsfc+generic 三链路** end-to-end，断言导出 schema 一致（否则 credit 分支零覆盖） | 逐调用点 revert |
| **4** | **argspec 单一注册表** | `argspec.py` 每 flag 一条；`cli._build_parser` 遍历构建；**run 从 argspec 取 prepare∪analyze 并集、按 option-string 去重、`required` 一律降 False、`--steps` 保留 run 专属 `...,rules` 默认**；删 `cli.py:220-258` 重复声明 + `cmd_run` 手工 Namespace | 中 | 中 | 新增用例：prepare 每 flag 在 run 路径真到达 cmd_prepare；`--help` 与基线比对；无 argparse dest 冲突 | 保留 run 分叉原样，回退阶段 3 |
| **5** | **拆 `result_query`（样板）** | 独立 skill：只依赖 `risk_core`；组合根 `cmd_query` 函数直调；薄 `__main__` 可选（不进 agent 模板） | 低 | 低 | 现有 query smoke 绿；新增独立调用用例 | 删独立入口即回原状 |
| **6** | **拆 `docx_report` + `trigger` + `data_prep`** | 三者改依赖 `risk_core`；`data_prep` 用 `contracts.read/write_prepared`+`features.json` schema（**顺手修 §5.1 前导零 bug**） | 中 | 中 | 各自 smoke 绿；prepared.csv dtype 往返用例 + features.json 契约用例 | 逐 skill commit |
| **7** | **拆 `visualization` + `explore_thresholds`** | 改用 `risk_core.results_loader`（横向依赖解除）；文件名走 `contracts` 模板 | 中 | 中 | 出图/阈值 smoke 绿；**grep 红线：`risk_*/scripts` 无跨子 skill import** | 逐 skill commit |
| **8** | **信息架构懒加载**（可与 2-7 并行） | 建 `references/` 树，**按迁移映射搬**：`blocking-gates.md`←AGENTS:146-186、`paths-env.md`←AGENTS:112-145、`cli/*.md`←AGENTS:187-328、`levels.md`（新撰）；瘦身 SKILL/AGENTS；消 50/70 漂移（收口到 `blocking-gates.md`）；子 SKILL 顶部加"何时读我" | 中 | 低 | `test_docs_single_source`（纯 grep）+ 人工 eval 抽样 | 删 `references/` 即回原状 |
| **9（可选）** | 修 state_dir 发散 | 统一 credit 与 analyze/export/query 的 `.pipeline_state.json` 目录；不做全面路径合一 | 低 | 中 | run credit 后 query 读到同一 state；指纹兼容用例为红线 | 单 commit，可跳过 |
| **10（可选·可砍）** | 内核去重 + 旧入口收敛 | `segment_univariate` 收敛为 `engine` shim；`pipeline.py:858` 旧 `main()` 转调 + deprecation | 中 | 中 | 三处 5 元组解包用例；`test_smoke_legacy` 有警告不报错 | 逐项 revert |

### 关键顺序约束
- **阶段 1（抽 core + 契约）是一切拆分的前提**，必须先做——它同时是"保留统一 CLI"和"拆独立 skill"两条路的共同地基。shim 用**模块别名**（非 `import *`）是本阶段成败关键。
- 阶段 3/4（`assemble_exports` + `argspec`）与拆分**互不阻塞**，可并行推进。
- 阶段 5（`result_query`）是**独立-skill 模式的试金石**：先用最干净的一个跑通"依赖 core、组合根函数直调、grep 无横向"整套模式，再照单剥离 6/7。阶段 7 依赖阶段 5 已把 `results_loader` 升 core。
- 阶段 8（IA 文档）**不碰运行时代码**，可与任何代码阶段并行、由不同人推进。
- **前 8 阶段已覆盖全部 4 类高危出错源**；阶段 9/10 是可延后/可砍的尾声。

### 建议落地批次
1. **批次 A（地基，必做）**：阶段 1 → 2 → 3 → 4。拿到"单一真源"主体收益，CLI 界面零变化。
2. **批次 B（拆分，验证独立-skill 模式）**：阶段 5 → 6 → 7。
3. **批次 C（体验，可并行）**：阶段 8。
4. **批次 D（收尾，可选）**：阶段 9、10。

---

## 10. 风险与开放问题

| 风险/问题 | 缓解 |
|---|---|
| 双入口困惑（顶层 vs 子 skill CLI） | §4.3 blessed 入口策略写进 `_index.md`；子 skill 独立 CLI 不进 agent 模板 |
| 状态机跨 skill（trigger/report 需 Level 1） | `require_level` 留 `risk_mining.pipeline_state`；**由组合根转发命令在 import 子 skill 前调用**；子 skill 直调路径不兜此门（人工/测试用，可接受） |
| wire/读契约漂移 | 阶段 1 先立 `contracts.py` 单一真源（含元信息白名单、列名常量、dtype、文件名模板），再拆（P6） |
| shim 覆盖不全导致测试红 | 阶段 1 用**模块别名**登记，逐子模块 + 私有名可达；以 20 个测试文件的现有 import 面为验收清单 |
| 包改名影响外部引用/入口 | `risk_pipeline` re-export shim + `__main__` 转发 + pyproject 保号，保留一个版本周期 + CHANGELOG 标注 |
| IA 懒加载把"全文必读"换成"按索引下钻"→ 欠读风险 | "绝对排斥清单 + 3 阻断门存在性 + env 前置"保留为 SKILL/AGENTS 常驻 always-on 对冲 |
| **开放问题 → 已决（2026-07-05）** | 是否长期保留 `credit`/`gsfc` 两条黑盒链路，还是统一到 `generic`？ → **保留黑盒，不并入 generic，不加特殊化**（见下决策）。 |

> **决策（2026-07-05，用户拍板）**：`credit`/`gsfc` 黑盒链路服务某些用户的常用路径，**保留、不并入 generic、不为其在 generic 里加过多特殊化处理**。依据（实测）：
> - 「统一到 generic」的真实成本不在删 ~450 行 `run_credit/gsfc_pipeline`（那是机械的），而在：把 `prepare_credit_wide_table` 多表合并 + `create_credit_features`/`feature_engineering_gsbb` 重新安置成 generic 前置步骤；且会**破坏 `load_results` 向后兼容**——`results_loader.py:49-50/195-196` 硬编码 `data/results/征信`、`工商财务` 搜索路径，磁盘已有历史导出会读不出。
> - 后果：`risk_segment_univariate/scripts/{segment_univariate,univariate}.py` 因 gsfc 是唯一活跃消费者（`pipeline.py:346,381`）而**仍存活、非死代码**；结果 CSV「征信/工商财务」前缀特判（`config.py:51-62` 等）保留不动；阶段 10 的「segment→engine 收敛」据此判为**可砍**（详见 `CLAUDE.md` §3 行 10）。

> **后续执行（2026-07-05，commit `c58c698`）**：在「保留黑盒」前提下进一步把两条黑盒链路**从共享 `pipeline.py` 抽取为独立 skill `risk_legacy_chains`**（逐字迁移、行为不变、前端/内核靠 `_load_module` 名字串复用），使 credit/gsfc 不再与 generic 混在同一模块——闭合「内核物理仍在 risk_pipeline」这处 done-gap 的编排部分。先补 `tests/test_golden_legacy_chains.py`（两链路 IV/AUC/LR/单变量值级锁）作安全前提，244→246 passed。

---

*本文档为设计草案 v2（已过对抗性核验），经评审确认后据此实施；实施以本文 §9 计划为准，每阶段单独提交、单独验证。*
