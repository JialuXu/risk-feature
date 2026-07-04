# risk-feature-pipeline 业务需求文档（PRD）

> 文档类型：用户视角的功能需求说明
> 适用范围：`risk-feature-pipeline/` 整个项目（顶层调度器 + 统一 CLI + 12 个子 Skill）
> 文档版本：v1.0（2026-04-30）

---

## 1. 总体定位

### 1.1 业务背景

银行风险管理团队在做"风险特征分析"时，长期面临三类痛点：

1. **流程零散**：从原始多源数据到可交付的 Word 报告，要走数据合并、特征工程、单变量、IV、LR、规则挖掘、导出、可视化、客户级触碰、报告生成等十余个环节，每个环节由不同脚本完成、参数零散、容易跑错。
2. **黑盒难复盘**：跑完之后只剩一堆 CSV，无法回答"用的是哪份数据、用的什么阈值、跑到了哪一步、产物在哪里"。
3. **误操作代价高**：把"对外报告"基于错误数据集生成、推送给业务后即不可撤回；目前却没有任何机制要求用户在关键节点显式确认。

### 1.2 产品目标

`risk-feature-pipeline` 是一套**模块化的风险特征分析工具集**，每个分析步骤独立成 Skill，通过统一 CLI 串联：

- **覆盖全链路**：从多表合并 → 特征工程 → 多视角分析 → 结果导出 → 可视化 → 客户级触碰 → Word 报告交付。
- **三种执行深度**：全流程 / 单维快路径 / 只读已有结果，按用户意图自动切换。
- **三种主题链路**：`credit`（征信）、`gsfc`（工商财务）、`generic`（通用宽表）。
- **四级成熟度状态**：前置 → Level 1 → Level 2 → Level 3，每一级对应明确的可交付物与不可逆性。
- **三处阻断式确认**：首次新数据集、客户级触碰、对外报告，强制留下审计痕迹。

### 1.3 用户角色

| 角色 | 关心什么 | 主要使用方式 |
|---|---|---|
| **风险分析师** | 一次跑通、产物正确、可控 | 命令行手敲子命令 / Python 直接调用 |
| **审批策略产品** | 拿到客户级触碰名单、规则可读 | `trigger` + `query` |
| **风险报告交付人员** | 最终输出 .docx 报告、用途分内/外 | `report` + 阻断节点 3 |
| **AI Agent**（如 Claude Code） | 状态可读、自检可机器消费 | 全部子命令 + `_audit.json` |
| **平台/运维** | 路径可移植、产物落到指定目录 | 环境变量 `RISK_PROJECT_ROOT` / `RISK_OUTPUT_ROOT` |
| **多银行接入方** | 字段映射可配置、不改代码即可适配 | YAML 覆盖 + ColumnMapper |

---

## 2. 整体业务流

### 2.1 模块全景

`risk-feature-pipeline/` 由 **1 个顶层调度器 + 1 个统一 CLI + 12 个子 Skill** 组成：

| # | 模块 | 业务定位 | Level 推进 |
|---|---|---|---|
| 0 | 顶层 `SKILL.md` + `AGENTS.md` | 总控调度 / Agent 行为规则 | — |
| 1 | `risk_pipeline/` | 9 子命令 + 状态机 + 配置加载 | 编排 |
| 2 | `risk_data_prep/` | 多表合并、坏客户打标、宽表构建 | 前置 |
| 3 | `risk_feature_engineering/` | 比率/占比/效率类衍生特征 | 前置 |
| 4 | `risk_segment_univariate/` | 分群相关性、均值差、T 检验 | 过渡态 |
| 5 | `risk_iv_diagnosis/` | IV 自适应分箱 + 可信度评级 | 过渡态 |
| 6 | `risk_logistic_regression/` | 分群标准化 LR + AUC + 特征对比 | 过渡态 |
| 7 | `risk_rule_mining/` | 决策树规则挖掘（多变量交互） | 过渡态 |
| 8 | `risk_export_report/` | 8 张标准 CSV + LLM JSON + 分群画像 | → Level 1 |
| 9 | `risk_result_query/` | 只读已落盘结果，top-N / 分群查询 | Level 1 后 |
| 10 | `risk_trigger_extraction/` | 客户级触碰扫描 + IV 加权得分 | → Level 2 |
| 11 | `risk_visualization/` | 12 类 PNG 图表（IV/相关/LR/规则/组合） | Level 1 后 |
| 12 | `risk_docx_report/` | LLM JSON + Markdown → 正式 Word 报告 | → Level 3 |

### 2.2 四级状态模型

把整个流水线产物按"成熟度"划成 4 级，每级对应一类可交付物：

| Level | 名称 | 含义 | 推进者 |
|---|---|---|---|
| 0 | 前置 | 项目刚建，宽表 + 特征工程已完成 | `prepare` + `feature_engineering` |
| · | 过渡态 | `_intermediate/` 已落，但还未合并出标准 CSV | `analyze` |
| 1 | Level 1 | 8 张 CSV + LLM JSON 全部到位 | `export` |
| 2 | Level 2 | 客户级触碰名单 3 张表到位 | `trigger`（须 ≥ Level 1） |
| 3 | Level 3 | 正式 .docx 报告交付 | `report`（须 ≥ Level 1） |

> Level 2 与 Level 3 是**并列分支**，互不依赖，但都要求 Level 1 已完成。

### 2.3 用户旅程

```
[原始多源数据]
        │
        ▼
[risk_data_prep + risk_feature_engineering]
        │  ← 阻断节点 1（首次新数据集必须确认）
        ▼
[prepared.csv + features.json]
        │
        ▼
[risk_segment_univariate + risk_iv_diagnosis +
 risk_logistic_regression + risk_rule_mining]   ← 过渡态
        │
        ▼
[risk_export_report]                             ← Level 1
        │   ▶ 8 CSV + LLM JSON + audit.json
        │
   ┌────┼────┬────────────┬───────────┐
   ▼    ▼    ▼            ▼           ▼
[query] [viz] [trigger]   [docx report]
            (Level 2)     (Level 3)
            ↑              ↑
            阻断节点 2     阻断节点 3
```

---

## 3. 子 Skill 业务需求

> 每个模块按 **功能说明 / 功能逻辑 / 预期输出结果** 三段陈述。

---

### 3.1 顶层调度器（`SKILL.md` + `AGENTS.md`）

#### 功能说明

用户的请求往往是模糊的——"帮我做风险特征分析"、"分析一下这份宽表"、"看一下分群表现"。顶层调度器负责把模糊请求映射到正确的执行路径，并约束 Agent 在关键节点的行为。

#### 功能逻辑

1. **意图识别**：识别用户消息中的关键词，区分四类意图：
   - 全流程分析（"做风险特征分析" / "分析这份宽表"）
   - 单维快路径（"只看企业规模" / "对小型企业的分析"）
   - 只读已有结果（"查 / 读 / 看 top X"）
   - 客户级触碰 / 报告交付（"哪些客户触碰" / "生成 Word 报告"）
2. **链路路由**：在全流程意图下选择 `credit` / `gsfc` / `generic` 三种主题链路之一。
3. **阻断守门**：在三个关键点强制让用户先确认（详见 §4.2）。
4. **Agent 行为约束**：通过 `AGENTS.md` 强制要求："先查再跑"、"用 `prepare_df` 不手抄"、"单脚本 + verbose=False + head(N)"。

#### 预期输出结果

不直接产出文件，但确保：

- 用户的每个请求都被正确路由到子 Skill。
- 关键节点的阻断信息以 `⚠️ [阻断节点 N]` 格式显式输出，包含原因 + 当前参数 + 解除方式三段。
- 执行前对齐"本次目标 Level"，避免误用 Level 1 结论做对外交付。

---

### 3.2 `risk_pipeline/`：统一 CLI 与流水线编排层

#### 功能说明

提供统一的命令行入口（`python -m risk_pipeline ...`），把分散的分析步骤封装为 7 个标准子命令 + 1 个一键组合命令。维护项目状态档案、配置加载、路径解析、阻断节点等横切能力。

#### 功能逻辑

7+1 个子命令各司其职：

| 子命令 | 职责 | Level |
|---|---|---|
| `prepare` | 构建 `prepared.csv` + `features.json`，阻断节点 1 守门 | 前置 |
| `analyze` | 跑 `univariate / iv / lr / rules` 子集到 `_intermediate/` | 过渡态 |
| `export` | 合并 `_intermediate/` 为标准 CSV + LLM JSON + audit.json | Level 1 |
| `query` | 只读已有结果，top-N / 分群查询 | 不改 Level |
| `visualize` | 渲染 12 类 PNG 图表 | 不改 Level |
| `trigger` | 客户级触碰，阻断节点 2 守门 | Level 2 |
| `report` | 渲染 .docx，阻断节点 3 守门 | Level 3 |
| `run` | 一键组合：`generic` 走 `prepare→analyze→export`；`credit/gsfc` 转发既有链路 | — |

横切机制：

1. **项目状态档案 `.pipeline_state.json`**：记录每次执行的参数、产物、Level 推进、数据集指纹。
2. **配置驱动**：所有阈值（IV 切档、样本量门槛、规则深度等）来自 `config/default.yaml`，用户 YAML 深度合并覆盖。
3. **路径可移植**：`RISK_PROJECT_ROOT` / `RISK_OUTPUT_ROOT` 环境变量优先；写盘失败时给出清晰解决路径。
4. **三处阻断节点**：在不可逆动作前强制确认。

#### 预期输出结果

每个子命令完成后打印**状态印章**：
```
[<cmd>] OK | project=<name> | level=<...>
  <额外信息>
  inputs:  <输入路径>
  outputs: <输出路径>
```

项目根下生成 `.pipeline_state.json`，记录完整执行历史。Level 不可逆推进（既到 Level 1 后再跑 `analyze` 不会回退）。

---

### 3.3 `risk_data_prep/`：数据准备

#### 功能说明

用户提交一份原始宽表（CSV）+（可选）坏客户清单，希望系统：

1. 把目标列（`is_bad`）拼到宽表上；
2. 按用户规则过滤掉不需要的样本；
3. 自动识别可分析的特征列；
4. 阻止"误把陌生数据集当老数据集"导致的灾难性误用。

#### 功能逻辑

1. **接收输入**：宽表路径、坏客户清单（可省）、主键、目标列名。
2. **按规则过滤**：
   - 类别过滤：`exclude` / `include`。
   - 数值过滤：`min` / `max` / `range`，自动 `pd.to_numeric` 强转。
   - 缺失过滤：`drop_na: true`。
3. **首次数据集守门**（阻断节点 1）：
   - 用"文件大小 + 前 1MB SHA256"指纹比对项目历史档案。
   - 首次出现必须显式确认（`--confirmed-new-dataset` 或拆分版三连传）。
4. **打 `is_bad` 标签**：宽表已有则保留；只有坏客户主键清单时按 `主键 ∈ 清单 → 1，否则 → 0` 打标。
5. **自动选特征列**：剔除主键、目标列、零方差列、用户黑名单后剩下的数值型列。
6. **持久化**：`prepared.csv` + `features.json`（含数据集指纹、过滤规则、确认方式）。

主题特化能力：

- **征信主题**：`prepare_credit_wide_table`，自动清洗千分位金额、按主键去重取最新。
- **工商财务主题**：`build_wide_table`，融合工商 + 财务 + 产业侧表。
- **通用主题**：直接用 `prepare_df` 一行合成，不走主题特化。

#### 预期输出结果

| 产物 | 路径 | 用途 |
|---|---|---|
| 准备好的宽表 | `data/processed/<project>/prepared.csv` | 后续 analyze / trigger 共用 |
| 特征清单 + 元数据 | `data/processed/<project>/features.json` | 含 id_col / target_col / 数据集指纹 / 确认方式 |

**强制规范**：
- 合并后必须打印总样本 / 好坏客户数 / 坏率。
- 不在日志输出客户姓名 / 证件号 / 手机号等敏感字段。
- 跳过的样本必须打印原因。

---

### 3.4 `risk_feature_engineering/`：特征工程

#### 功能说明

把原始度量指标（绝对量）转换为对规模不敏感的**比率 / 占比 / 效率类**衍生特征，让下游 IV / LR 在不同规模客户间可比。

#### 功能逻辑

1. **接收同粒度宽表 + 原始度量列**。
2. **按主题构造衍生特征**：
   - 征信主题：机构数 / 渠道占比 / 笔数交叉（`create_credit_features`）。
   - 财务主题：偿债 / 周转 / 杠杆等比率（`feature_engineering`）。
   - 工商变更主题：变更频次、集中度、近期占比（`feature_engineering_gsbb`）。
3. **安全除法**：所有除法走 `safe_divide`，分母为 0 或 NaN 时返回 NaN（避免 Inf）。
4. **缩尾**：对比率列 Winsorize（默认 1%/99%），排除营运资金 / 自由现金流等少数例外列。
5. **筛选可分析列**：`get_feature_cols` 按"非零方差 + 数值型 + 非主键 / 非目标"过滤出最终 `feature_cols`。
6. **重复构造防护**：衍生列已存在时跳过，避免覆盖。

#### 预期输出结果

返回拓展后的宽表 DataFrame + `feature_cols` 列表（不直接落盘）。

**强制规范**：
- 参与风险分析的连续特征以**比率 / 效率 / 占比**为主，绝对量不进入推荐特征集。
- 必须能说明衍生列规模与缩尾影响范围。

---

### 3.5 `risk_segment_univariate/`：分群单变量

#### 功能说明

在每个分群（如行业、企业规模）内，对每个特征单独跑统计检验，回答"这个特征在这个分群里到底跟坏率有没有关系"。

#### 功能逻辑

1. **接收宽表 + 目标列 + `feature_cols` + 分群列。**
2. **分群摸底**：每个分群内的样本数、坏客户数、坏率。
3. **样本准入**：分群总样本 ≥ `MIN_SAMPLES`（默认 50），坏客户 ≥ `MIN_BAD_CORR`（默认 15）才进入计算，否则跳过并记录原因。
4. **三类计算**：
   - **点二列相关系数**：连续特征 vs 二分类目标。
   - **T 检验**：好 / 坏客户均值差 + p-value。
   - **跨分群方差**：同一特征在不同分群的相关系数离散度（识别"普遍信号"vs"分群专属信号"）。
5. **二值标签对比**（可选）：用户可指定 `qual_dims` 把"是否上市 / 是否高新"等二值列也参与对比。

#### 预期输出结果

| 产物 | 形态 | 用途 |
|---|---|---|
| 相关系数表 | DataFrame（长格式） | 供下游 LR / 导出消费 |
| 均值差 / p-value 表 | DataFrame | 同上 |
| 分群元信息表 | DataFrame | 含 `n_total` / `n_bad` / 坏率 |
| 跨分群方差表 | DataFrame | 识别稳定特征 |

**强制规范**：
- 跳过的分群必须逐条记录原因。

---

### 3.6 `risk_iv_diagnosis/`：IV 诊断

#### 功能说明

IV（Information Value）是风控领域用来衡量"特征对好坏区分力"的核心指标。本模块负责：

1. 对每个特征算 IV 值（自适应分箱 + WOE 截断 + 缺失分离）。
2. 在每个分群内单独算 IV（识别"在哪个分群最有用"）。
3. 给每条 IV 结果打**可信度等级**（避免小样本虚高 / 过拟合特征被误用）。

#### 功能逻辑

1. **自适应分箱**：根据样本量与坏客户数动态决定分箱数（`bins = max(3, min(n_bad // 3, n_samples // 20, 10))`），避免小样本下"坏客户数为 0 的箱"用 0.5 校正导致 IV 虚高。
2. **WOE 截断**：所有 WOE 截到 `[-5.0, +5.0]`，避免极端值主导 IV。
3. **缺失分离**：缺失值单独成箱，IV 贡献与非缺失部分分别统计。
4. **IV 预测能力分档**：
   - 弱 / 中 / 强：按 `IV_THRESHOLD` 配置切档（默认 0.02 / 0.1 / 0.3）。
   - **疑似数据穿越**：IV > 2.0 直接标黄，**不进入推荐特征**。
5. **可信度评级**：综合样本量 + IV 大小判断：
   - 可信 / 参考 / 不可信-样本不足 / 不可信-疑似数据穿越。
6. **分群 IV**：在每个分群内独立计算，识别分群专属强信号。
7. **可选业务阈值**：`calc_feature_thresholds` 可基于 optbinning 给出业务可解释的切分点。

#### 预期输出结果

| 产物 | 形态 | 用途 |
|---|---|---|
| 全量 IV 表 | DataFrame | 喂给 export 写 `_IV分析结果_全量.csv` |
| 分群 IV 明细 | DataFrame | 写 `_IV分析结果_分群.csv` |
| IV 可信度透视表 | DataFrame | 写 `_IV可信度透视表.csv` |
| 可信度诊断 | DataFrame | 写 `_IV可信度诊断.csv` |
| 警告列表 | List | 流入 LLM 报告数据 |

**强制规范**：
- IV > 2.0 必须标记"疑似数据穿越"，**不得**作为推荐特征。
- WOE 必须截断到 `[-5.0, +5.0]`。
- 跳过的特征 / 分群必须记录原因。

---

### 3.7 `risk_logistic_regression/`：逻辑回归

#### 功能说明

在每个分群内训练标准化 + L2 惩罚的逻辑回归，回答两个业务问题：

1. **多变量下哪些特征真的有用**（系数大小，剔除多重共线性后的"净效应"）。
2. **这个分群整体的可分性如何**（AUC，且必须诚实标注 AUC 类型）。

#### 功能逻辑

1. **样本准入**：分群坏客户 ≥ `MIN_BAD_LR`（默认 20）+ 好客户 ≥ `MIN_GOOD_LR`（默认 50）才拟合。
2. **标准化 + L2**：`StandardScaler` + `LogisticRegression(C=1.0, solver='lbfgs')`（默认 L2 正则），系数以**标准化后尺度**解释。
3. **AUC 类型自动选择**：
   - 样本数 ≥ `MIN_SAMPLES_CV`（200）+ 坏 ≥ `MIN_BAD_CV`（30）：5 折分层交叉验证 AUC。
   - 样本不足：降级为训练集 AUC，**且必须显式标注**。
   - CV 失败：训练集 AUC + "CV 失败"标注。
4. **特征集对比**（`compare_feature_sets`）：可比较两组特征列表（如"原始 vs 衍生"、"司法 vs 非司法"）的 AUC 提升。

#### 预期输出结果

| 产物 | 形态 | 用途 |
|---|---|---|
| LR 系数长表 | DataFrame | 写 `_逻辑回归系数.csv` |
| AUC 长表 | DataFrame | 含 `AUC类型`，写入同一 CSV |
| 特征集对比表 | DataFrame | 写入综合特征分析结果 |

**强制规范**：
- AUC 必须标注类型（交叉验证 / 训练集-样本不足 / 训练集-CV 失败）。
- 拟合异常须捕获并记入跳过原因。

---

### 3.8 `risk_rule_mining/`：规则挖掘（可选步骤）

#### 功能说明

用决策树挖掘"多变量交互规则"，补充 IV（单变量）和 LR（加性）的盲区。每条规则是若干"特征 op 阈值"的合取（AND），如：

> 资产负债率 > 0.75 且 利息覆盖倍数 < 2.0 → 坏账率 32%（Lift = 3.4）

可直接用作预警触发条件、审批红线规则、贷后检查清单。

#### 功能逻辑

1. **样本准入**：与 LR 一致（`MIN_BAD_LR=20`、`MIN_GOOD_LR=50`）。
2. **特征预筛**：用 IV ≥ `IV_THRESHOLD['medium']` 且可信度可信/参考的特征作为树输入；剔除 IV > `IV_SUSPECT_THRESHOLD`（2.0）的疑似数据穿越特征。
3. **决策树拟合**：
   - `max_depth = 3`（限制规则可读性）。
   - `min_samples_leaf_ratio = 0.05`（防过拟合）。
   - `min_bad_in_leaf = 5`。
   - `class_weight = 'balanced'`（处理样本不平衡）。
4. **规则提取**：从根到叶的完整路径即为一条规则。
5. **规则筛选**：满足 `min_coverage = 0.01` + `min_lift = 1.5` + `min_bad_in_leaf = 5` 三道闸门。
6. **规则去重**：按 `(特征集合, 阈值四舍五入)` 去重，避免不同树路径产生等价规则。
7. **稳定性评估**：5 折交叉验证，记录每条规则在 holdout 的坏账率均值/标准差，出现 ≥ `stability_min_folds`（默认 3）折视为稳定。
8. **业务语言格式化**：
   - 规则条件中文化（`资产负债率 大于 0.75`，避免技术符号）。
   - 阈值精度自适应：比率类 → 2 位小数；金额类 → 整数 + 千分位；其他 → `:.4g`。
9. **建议用途分配**：
   - Lift ≥ 3 + 稳定 → 预警 / 审批红线。
   - 1.5 ≤ Lift < 3 + 稳定 → 参考。
   - 不稳定 → 必须人工复核（export 阶段会显式提示）。

#### 预期输出结果

| 产物 | 形态 | 用途 |
|---|---|---|
| 规则表 DataFrame | 含覆盖率 / 坏账率 / Lift / 稳定性 / 建议用途 | 流入 export，写 `_风险规则表.csv` |
| 决策树 pkl | `_intermediate/rule_tree_*.pkl` | 供可视化出真树图 |
| 规则 pkl | `_intermediate/rules.pkl` | 供 export 与可视化共用 |

**强制规范**：
- 阈值文本以中文业务语言呈现，避免技术符号。
- 不稳定规则必须在 export 时显式提示，并写入 `_audit.json`。

---

### 3.9 `risk_export_report/`：结果导出

#### 功能说明

把上游分析步骤的内存结果合并为对外约定的"8 张标准 CSV + LLM JSON + 分群画像 + 自检文件"。这是项目从「过渡态」推进到 Level 1 的唯一通道，也是所有下游模块（query / visualize / trigger / report）的契约源头。

#### 功能逻辑

1. **重建 results 字典**：从 `_intermediate/` 读所有 CSV 与 manifest，恢复内存结构。
2. **构建对外标准产物**：
   - 全量 IV 表（`_IV分析结果_全量.csv`，旧名 `_IV分析结果.csv` 兼容副本同时写入）。
   - 分群 IV 表（`_IV分析结果_分群.csv`，旧名 `_IV值分析.csv` 兼容副本）。
   - IV 透视表 + 可信度透视表 + 可信度诊断。
   - 特征风险相关性 + LR 系数 + AUC + 综合特征分析结果。
3. **构建 LLM 报告数据**（`_LLM报告数据.json`）：
   - `分析概览` / `核心发现` / `特征有效性汇总` / `无效特征列表` / `分群画像_重点` / `分群画像_简略`。
4. **构建分群画像 CSV**：每分群一行，含样本数 / 坏率 / 模型 AUC / Top3预测特征_IV / Top3风险特征_相关性。
5. **可选：导出风险规则表**：若 `_intermediate/rules.pkl` 存在，写 `_风险规则表.csv` 并扫不稳定规则。
6. **写 audit.json**：扫已落盘产物，记录：
   - IV > 2.0 的疑似数据穿越特征。
   - 不稳定规则列表。
   - 当前 Level / 产物文件数 / 时间戳。
7. **列名统一**（A4 后）：所有对外列名为「特征 / 分群维度 / 分群名称」三件套；旧列名通过 `load_results()` 自动 rename 兼容。

#### 预期输出结果

**结果目录**（默认 `data/results/<project>/`）：

| 文件 | 用途 |
|---|---|
| `_IV分析结果_全量.csv` ⭐ | 全量 IV 表 |
| `_IV分析结果_分群.csv` ⭐ | 分群 IV + 可信度 |
| `_特征风险相关性.csv` | 分群相关系数 + 元信息 |
| `_逻辑回归系数.csv` | 分群 LR 系数 + AUC + AUC类型 |
| `_IV值透视表.csv` | 行=分群、列=特征（查 top N 最快） |
| `_IV可信度透视表.csv` | 行=分群、列=特征 |
| `_IV可信度诊断.csv` | 分群层面样本/坏率/可信率概况 |
| `_综合特征分析结果.csv` | 全局 IV + 跨分群一致性 + 综合评级 |
| `_风险规则表.csv` | 决策树规则（仅在跑了 rules 后） |
| `_audit.json` ⭐ | 机器可读自检 |

**输出目录**（默认 `output/<project>/`）：

| 文件 | 用途 |
|---|---|
| `_LLM报告数据.json` | 喂给 LLM 写 Markdown 正文 |
| `_LLM_特征有效性汇总.csv` | LLM 视角重点特征 |
| `_LLM_分群画像.csv` | 每分群一行画像 |

**强制规范**：
- CSV 使用 `utf-8-sig` 编码（兼容 Excel 直接打开）。
- 推荐特征列表**不得**包含 IV > 可疑阈值的条目。
- 列名必须与 `docs/SCHEMA.md` 完全一致。

---

### 3.10 `risk_result_query/`：结果查询（只读后置）

#### 功能说明

用户已经把项目跑到 Level 1 后，最常见的诉求是"查一下 X 维度下 IV top 15 的特征是哪些"。`risk_result_query` 提供这条只读查询路径，**不重跑、不改 Level、不写 state**。

#### 功能逻辑

1. **加载已落盘的 8 张 CSV**：自动处理新旧文件名 / 列名（向后兼容）。
2. **多候选路径搜索**：自动在 `data/results/<project>/`、`data/results/征信/<project>/`、`data/results/工商财务/<project>/` 等多个候选位置查找。
3. **列名规范化**：旧列名 `特征名称` → `特征`，`分群值` → `分群名称`，读时自动 rename。
4. **统一 API**：
   - `load_results(project_name)` 返回 `Results` 对象，包含 `iv_full` / `iv_group_all` / `corr_long` / `lr_coef_long` / `lr_auc_long` / `comprehensive` 等长格式 DataFrame。
   - `top_features(r, kind='iv'|'iv_group'|'corr'|'lr', dim=..., group=..., n=15, sign=...)` 一行返回 top N。
5. **误参告警**：当 `kind='iv'` 时如果用户传了 `dim` / `group`，发出 UserWarning 提醒应改用 `kind='iv_group'`。

#### 预期输出结果

不落盘，直接返回 DataFrame 给上层（CLI 时通过 `--output-format table/csv/json` 打印到 stdout）。

**典型输出**：
```
   特征               IV值    预测能力等级
   逾期总笔数         0.42    强
   担保替代率         0.28    中
   ...
```

**强制规范**：
- 不重跑、不改 Level、不写 state。
- `load_results` 找不到目录时抛 `FileNotFoundError`，由调用方决定是否触发重跑。

---

### 3.11 `risk_trigger_extraction/`：客户级触碰提取

#### 功能说明

风险分析的最终落地之一是"哪些客户触碰了哪些风险阈值"。`risk_trigger_extraction` 把 Level 1 的 IV / LR 结论"落到每个客户身上"，输出客户级宽表 + 长表 + 阈值说明三件套，并按 IV 加权得分排名。

#### 功能逻辑

1. **前置校验**：项目当前 Level ≥ Level 1。
2. **加载 prepared.csv** + features 配置。
3. **二选一选取特征配置**：
   - 默认 `RISK_FEATURES_GSFC`：仅工商财务主题适用（30+ 项默认特征）。
   - 用户提供 JSON：项目专属特征列表，含 `report_name` / `source_col` / `risk_direction` / `iv` / `category` / 可选 `explicit_threshold` 与 `scope`。
4. **匹配率守门**：默认特征匹配宽表实际列名 < 70% 时直接 `RuntimeError` 阻断（避免输出全 0 名单；数值单一真源 = `MIN_DEFAULT_FEATURE_MATCH_RATE`，历史上为 50%，已收紧）。
5. **scope 维度筛选**：每个特征支持 4 种 scope 形态：
   - `'full'`（默认）：全量客户。
   - `'waist'`：仅腰部企业（兼容旧写法）。
   - `{'dim': X, 'value': Y}`：单值维度筛选。
   - `{'dim': X, 'values': [Y1, Y2]}`：多值维度筛选。
6. **阈值策略**（优先级从高到低）：
   - 显式阈值（`explicit_threshold`）：业务专家给出。
   - 坏客户均值：以坏客户均值作为触碰线（保守且有风控意义）。
   - 兜底：好/坏样本不足时用全量中位数。
7. **触碰评估**：每个客户对每个特征算"是否触碰（0/1/NaN）"。
8. **IV 加权风险得分**：`得分 = Σ(触碰_i × IV_i) / Σ(IV_i) × 100`，按降序排列。
9. **元信息列防撞**：默认从输出宽表中剔除 `is_bad` / `企业规模` 等元信息列，避免与 `prepared.csv` merge 撞列；用户可用 `keep_metadata_cols` 显式保留任意列（不限白名单）。

#### 预期输出结果

| 产物 | 路径 | 用途 |
|---|---|---|
| 客户级宽表 | `output/<project>/<project>_风险触碰明细_宽表.csv` | 每客户一行 |
| 客户级长表 | `output/<project>/<project>_风险触碰明细_长表.csv` | 每条触碰一行 |
| 阈值说明 | `output/<project>/<project>_触碰阈值说明.csv` | 每条阈值的来源与方向 |

**宽表列结构**：
- `{id_col}`：主键
- `{特征}_值`：原始数值
- `{特征}_触碰`：1 / 0 / NaN
- `触碰特征总数`、`IV加权风险得分`、`触碰特征清单`
- `触碰数_{类别前缀}`：各业务类别下的触碰数

**强制规范**：
- 阻断节点 2：必须传 `--confirmed`。
- 默认特征匹配率 < 70% 必须阻断。
- 不在输出中暴露客户姓名 / 证件号 / 手机号。

---

### 3.12 `risk_visualization/`：可视化（只读后置）

#### 功能说明

Level 1 完成后，把 IV / 相关性 / LR / 分群画像 / 决策树 / 规则散点 / 指标组合 / 共现网络等渲染成 PNG，便于报告插图与人工审阅。

#### 功能逻辑

1. **加载 Level 1 产物**：与 `query` 同源，纯只读。
2. **支持 12 类图表**：

| `kinds=` | 图表 | 数量 |
|---|---|---|
| `iv` | 全量 IV 横向条形图 | 1 |
| `iv_heatmap` | 分群 × 特征 IV 热力图（每维度一张） | M（维度数） |
| `corr_heatmap` | 分群 × 特征 相关系数热力图 | M（维度数） |
| `lr_heatmap` | 分群 × 特征 LR 系数热力图 | M |
| `auc` | 跨分群 AUC 条形图 | 1 |
| `segment` | 分群画像（坏率柱图 + 样本数） | 1 |
| `rules` | 规则 lift × coverage 散点 | 1 |
| `combos` | 指标组合 max lift 条形图 | 1 |
| `thresholds` | 候选阈值分箱坏率 + 风险倍数 | 0–N |

> 已下线（对最终业务报告无增量价值、且随分群数量爆炸）：每分群一张的 `corr`/`lr` 散图
> （看对应热力图即可）、决策树图 `tree`、特征共现网络 `combo_network`、单变量箱形图。

3. **依赖隔离**：matplotlib / seaborn 缺失时给出友好提示（`pip install -e .[viz]`），不抛 traceback。
4. **中文字体自动探测**：按 OS 探测中文字体，全 miss 时只 warn 不报错。
5. **缺前置自动跳过**：未跑 rules 时 `rules/combos` 自动跳过、未跑 explore_thresholds 时 `thresholds` 跳过（status stamp 显示 `skipped=...`），不报错。

#### 预期输出结果

| 产物 | 路径 |
|---|---|
| PNG 图集 | `output/<project>/charts/*.png` |

**强制规范**：
- 不重跑链路、不改 CSV、不改 Level。
- PNG 是唯一形态，不出 HTML / 交互式图表。

---

### 3.13 `risk_docx_report/`：Word 报告生成

#### 功能说明

LLM 已基于 `_LLM报告数据.json` 写好一份 Markdown 正文；`risk_docx_report` 把 Markdown + LLM JSON 渲染成正式的 .docx 报告，并强制区分"内部审阅版"与"对外交付版"。

#### 功能逻辑

1. **前置校验**：项目 Level ≥ Level 1。
2. **三步工作流**：
   - **打包写作上下文**：`build_prompt_bundle.py` 把 `report-prompt.md` + LLM JSON 合成单个 Markdown 文件，喂给大模型生成正文。
   - **大模型生成 Markdown 正文**（不在本模块职责）。
   - **渲染 .docx**：`build_docx_report.py` 把 Markdown + LLM JSON 渲染为 .docx。
3. **必填用途**：`--purpose internal` 或 `--purpose external`。
4. **阻断节点 3**：`--purpose external` 必须额外传 `--confirmed-final-version`。
5. **按用途自动加标题前缀**：
   - 内部：`内部审阅版-<project>风险特征分析报告`。
   - 外部：`<project>风险特征分析报告`。
6. **附录模式**（`--appendix-mode`）：`both / feature / segment / none / compact`。
7. **报告写作约束**：以仓库根的 `report-prompt.md` 为唯一模板，定义章节、风格、引用要求、业务建议口径。
8. **可选校验**：调用 `skills/skills/docx/scripts/office/validate.py` 检查 .docx 结构。

#### 预期输出结果

| 产物 | 路径 | 用途 |
|---|---|---|
| 报告任务包 | `output/<project>/<project>_报告任务包.md` | 喂给大模型 |
| 正式报告 | `output/<project>/<project>.docx` | 内部审阅或对外交付 |

报告结构：
- 封面（标题 + 用途水印）
- 目录
- 正文（Markdown 原样保留标题 / 列表 / 表格）
- 附录（分析概览 / 特征有效性 / 分群画像 / 风险规则表）

**强制规范**：
- `external` 必须双确认。
- .docx 一旦交付，CSV 改动须同步重新出报告（合规要求）。
- 报告附录仅作"解释性增强"，不替代正文业务分析。

---

## 4. 横切能力

### 4.1 项目状态档案

每个项目维护一份 `.pipeline_state.json`：

- `current_level`：当前 Level。
- `known_datasets`：已确认过的数据集指纹（避免重复阻断）。
- `history[]`：每次子命令的参数摘要、产物路径、耗时、执行后的 Level。
- `created_at` / `updated_at`：审计时间戳。

**业务价值**：用户中断后可随时查看进度；Agent 可读 `current_level` 决定下一步；审计可追溯到"用什么数据、什么参数、产出哪些文件"。

### 4.2 三处阻断节点

| 节点 | 触发场景 | 解除方式 |
|---|---|---|
| 节点 1 | `prepare` 检测到首次新数据集 | `--confirmed-new-dataset` 或拆分版三连传 |
| 节点 2 | `trigger` 即将基于 features 配置生成预警名单 | `--confirmed` |
| 节点 3 | `report --purpose external` | `--confirmed-final-version` |

每个阻断报错必含**原因 + 当前参数 + 解除方式**三段。

### 4.3 配置驱动

- **唯一 Python 配置源**：`risk_pipeline/config.py`。
- **YAML 数据源**：`config/default.yaml` + `config/column_mapping.yaml`。
- **多银行适配**：用户写一份覆盖 YAML，深度合并默认值。
- **字段映射**：`ColumnMapper` 屏蔽不同银行的字段命名差异。

```yaml
# config/city_bank.yaml — 仅覆盖差异
thresholds:
  min_samples: 30
  min_bad_samples: 5
column_mapping:
  required:
    customer_id: "客户号"
    target: "是否不良"
```

### 4.4 路径可移植

| 环境变量 | 含义 | 优先级 |
|---|---|---|
| `RISK_PROJECT_ROOT` | 输入读自何处 | 最高 |
| `RISK_OUTPUT_ROOT` | 结果写到何处 | 最高（若未设则复用项目根） |

默认行为：从 CWD 向上找首个含 `data/` 的目录。写盘失败（无权限）时把 `PermissionError` 转成 `RuntimeError`，提示设置 `RISK_OUTPUT_ROOT`。

### 4.5 样本量阈值统一

所有样本准入门槛集中在 `config/default.yaml`：

| 阈值 | 默认 | 用途 |
|---|---|---|
| `MIN_SAMPLES` | 50 | 分群进入统计 |
| `MIN_BAD_SAMPLES` | 10 | IV 计算 |
| `MIN_BAD_CORR` | 15 | 相关 / T 检验 |
| `MIN_BAD_LR` | 20 | LR 拟合 |
| `MIN_GOOD_LR` | 50 | LR 拟合 |
| `MIN_SAMPLES_CV` | 200 | 升级到交叉验证 AUC |
| `MIN_BAD_CV` | 30 | 升级到交叉验证 AUC |

### 4.6 全局开关

每个 CLI 子命令都接受：
- `--quiet`：静默回执。
- `--verbose`：打印底层 pipeline 详细日志。
- `--state-dir`：自定义 state.json 位置（多实例隔离）。

---

## 5. 异常与边界

### 5.1 错误信号

- **退出码 0**：成功。
- **退出码 1**：业务校验失败（路径不存在 / 阻断节点拒绝 / 参数非法），错误信息走 stderr。
- **stderr 警告（非阻断）**：audit.json 写入失败、不稳定规则提示、LLM 报告数据构建失败、可视化跳过项。

### 5.2 跳过规则

跳过任何分群 / 特征 / 步骤都必须**记录原因**：

- 样本不足 → 报告样本数 + 阈值。
- 全为常数列 → 显示该列为常数。
- 特征不在宽表 → 列出缺失字段。
- 拟合异常 → 捕获后写入跳过原因。

### 5.3 数据脱敏

所有产物（CSV / JSON / 日志）都**禁止**包含：
- 客户姓名、证件号、手机号。
- 任何可以直接定位到个人的字段。

主键列（`客户编号`等）只作为关联用，不作为分析维度展示。

### 5.4 向后兼容承诺

- **旧列名**（`特征名称` / `分群值`）：读时自动 rename，写时同时落新旧两份。
- **旧文件名**（`_IV分析结果.csv` / `_IV值分析.csv`）：兼容副本写一个版本，下版本移除。
- **旧 Python 入口**（`from shared.pipeline import ...`）：保留 shim 一个版本。
- **旧 CLI 入口**（`python -m shared --pipeline X`）：仍可用，但 stderr 打 deprecation 警告。

---

## 6. 验收标准

### 6.1 功能验收

| 场景 | 期望 |
|---|---|
| 新数据集首跑未加确认 flag | 阻断节点 1 报错，列出两条确认路径 |
| 项目 Level 1 后跑 `query` | 不重跑、不改 Level、stdout 输出表格 |
| `analyze` 含 `rules` 后跑 `visualize` | 决策树 / 规则散点 / 指标组合都生成 |
| `trigger` 默认特征匹配率 < 70% | RuntimeError 阻断，提示主题不匹配 |
| `report --purpose external` 未加 final 确认 | 阻断节点 3 报错 |
| 设置 `RISK_OUTPUT_ROOT=/tmp/out` 后跑全流程 | 所有产物落到 `/tmp/out/` 下 |
| matplotlib 未安装时跑 `visualize` | 友好提示安装命令，不抛 traceback |
| IV > 2.0 的特征出现在推荐列表 | **不允许**，必须标黄并排除 |
| 报告 AUC 不附 AUC 类型 | **不允许**，必须显式标注 |
| 跳过分群未打印原因 | **不允许**，必须逐条记录 |

### 6.2 体感与一致性

- 子命令完成后必须打印一条状态印章，包含：cmd / project / level / inputs / outputs。
- audit.json 必须在 `export` 完成前落盘，且 `level` 字段反映正确层级。
- 任何阻断节点的报错必须包含**原因 + 当前参数 + 解除方式**三段。
- CSV 列名必须与 `docs/SCHEMA.md` 完全一致；术语必须与 `docs/GLOSSARY.md` 一致。
- 12 个子 Skill 的 SKILL.md 内 CLI 示例必须与 `cli.py` 实际支持的参数对齐。

### 6.3 性能与可观测

- `prepare` 50K 行宽表应在 30 秒内完成。
- `run --pipeline generic` 全流程含 rules，50K × 80 列宽表应在 5 分钟内完成。
- 每个步骤的耗时记录到 `.pipeline_state.json` 的 `history[].duration_sec`。

---

## 7. 典型用户故事

### 故事 A：风险分析师跑首个项目

> 我拿到一份新行业的客户宽表（5 万行 × 80 列），希望出 IV/LR + 客户级触碰名单。

```bash
# Step 1. 一键跑通分析（首次必加 --confirmed-new-dataset）
python -m risk_pipeline run --pipeline generic \
    --wide data/raw/new_industry.csv \
    --bad-customer data/raw/bad.csv \
    --id-col 客户编号 --target-col is_bad \
    --project 新行业_v1 --confirmed-new-dataset

# → 自动 prepare → analyze（含 rules）→ export → Level 1

# Step 2. 客户级触碰（需要项目专属特征）
python -m risk_pipeline trigger --project 新行业_v1 \
    --features-file features_new_industry.json --confirmed

# → Level 2

# Step 3. 出图
python -m risk_pipeline visualize --project 新行业_v1
```

### 故事 B：审批策略产品看 top 特征

> 我要回答业务："小型企业里 IV 最高的 15 个特征是哪些"。

```bash
python -m risk_pipeline query --project 新行业_v1 \
    --kind iv_group --dim 企业规模 --group 小型企业 --top 15
```

→ 不重跑链路，0.5 秒内 stdout 出表。

### 故事 C：报告交付人员出对外报告

> 我已经看过内部审阅版没问题，现在要出对外报告。

```bash
# Step 1. 大模型先写正文
python -m risk_docx_report.scripts.build_prompt_bundle \
    --llm-json output/新行业_v1/新行业_v1_LLM报告数据.json
# → 喂给 LLM，得到 report_v3.md

# Step 2. 内部审阅版
python -m risk_pipeline report --project 新行业_v1 \
    --report-markdown report_v3.md --purpose internal

# Step 3. 对外交付（须双确认）
python -m risk_pipeline report --project 新行业_v1 \
    --report-markdown report_v3.md \
    --purpose external --confirmed-final-version
```

### 故事 D：Agent 自检后向用户回报

> 跑完后我（Agent）必须先 cat audit.json 才能告诉用户结果是否可信。

```bash
cat data/results/新行业_v1/新行业_v1_audit.json
```
```json
{
  "level": "Level 1",
  "n_exported": 14,
  "iv_overfit_features": [],
  "unstable_rules": [
    {"分群": "企业规模.大型企业", "规则编号": "rule_3", "CV有效折数": 2}
  ]
}
```

→ Agent 据此回报："Level 1 已完成，14 个产物落盘，但有 1 条规则在 5 折交叉验证里只命中 2 折，建议人工复核。"

### 故事 E：多银行接入

> 我们行的字段命名跟默认不一样，主键叫"客户号"、目标列叫"是否不良"。

**CLI 路径（推荐）**：直接覆盖 `config/column_mapping.yaml` / `config/default.yaml` 即可，CLI 不接受 `--config` / `--columns-file` 运行时切换。

```yaml
# 直接编辑 config/column_mapping.yaml
required:
  customer_id: "客户号"
  target: "是否不良"

# 或编辑 config/default.yaml
thresholds:
  min_samples: 30
```

prepare 阶段除阻断节点 1 之外，还会做一次列名预检：若 `column_mapping.yaml` 中的 `segment_dims` / `credit_category_dims` 在宽表中完全缺失，CLI 会硬错并列出实际列名，避免下游分群分析全空跑。

**Python API 路径（高级用法）**：当不走 CLI、直接在 notebook 调研时，可以传入自定义路径深度合并：

```python
# 仅 Python API 可用；CLI 入口不接受 --config，请走上方"CLI 路径"
from risk_pipeline.config_loader import load_config
config = load_config("config/my_bank.yaml")  # 自动深度合并默认值
```

→ 所有下游 Skill 自动用新映射，不改一行代码。
