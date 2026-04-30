---
name: risk-feature-pipeline
description: 企业风险特征分析总控技能。适用于"帮我做风险特征分析""帮我挖掘这份宽表里的风险特征""分析不同企业规模/行业/客群分群下是什么特征""读取 CSV 后输出分群画像、IV、LR、综合结论"等请求；内部自动选择 `credit` / `gsfc` / `generic` 管线，并决定走全流程、单维快路径或结果解读模式。
---

# Risk Feature Pipeline Orchestrator

## 先读这里

本 Skill 只负责**调度**，不重写分析逻辑。用户无需说出 `credit`/`IV`/`LR` 等技术词——这些由本 Skill 内部判断。

**硬规矩在 `AGENTS.md`**（绝对触发/排斥、结果层次、工具雷区、阻断节点、代码模板），本文件不重复；**执行任何步骤前必须先读 `AGENTS.md`**。

---

## 30 秒判断

### A. 先判断是否需要阻断

下列情况必须**先输出确认请求，等用户回复后再继续**（详见 `AGENTS.md` 五）：

- 用户提供的是从未见过的宽表 / 切换了银行配置 → **阻断节点 1**
- 用户要触碰提取，但未明确 features 配置 → **阻断节点 2**
- 用户要生成正式 Word 报告 → **阻断节点 3**

### B. 再选执行路径

| 用户意图 | 执行路径 |
|---|---|
| "查/读/看/解读/top X/已有结果" | `risk_result_query`（模板 B），**不重跑管线** |
| "哪些客户触碰/风险预警名单" | `risk_trigger_extraction`（模板 C），先过阻断节点 2 |
| "生成 Word/正式报告" | `risk_docx_report`，先过阻断节点 3 |
| 全流程分析 / 单维快路径 | 选管线（见下），走模板 A |

### C. 全流程时选管线

| 管线 | 适用场景 |
|------|----------|
| `credit` | 用户要跑征信主题分析 |
| `gsfc` | 用户要跑工商财务主题分析 |
| `generic` | 用户已给宽表 CSV，不想重走内置数据准备 |

**单维快路径**：用户只关心某一分群维度——仅对该维度跑 `univariate`→`iv`→`lr`→`export`，不默认把所有维度都跑。

---

## 执行策略

### 1. 全流程 / 单维快路径 → AGENTS.md 模板 A + 模板 B

严格按 `AGENTS.md` 的模板 A（跑管线）和模板 B（读结果）执行，禁止自行拼凑代码。

关键约束：
- 宽表+打标+特征列必须用 `prepare_df`，不要手写合并
- `steps=` 必须包含 `'export'`（否则结果不落盘，达不到 Level 1）
- 管线跑完立刻切模板 B 读磁盘结果，禁止读内存 `results` 对象

### 2. `generic` 缺少目标列时

不得擅自改做无监督分析，必须输出：

> "当前宽表缺少 `is_bad` 列，无法进行 IV/LR/坏客户相关性分析。请补充坏客户清单（如 `data/raw/坏客户标记.csv`），或提供含目标列的文件。"

若坏客户清单已有：优先走 `generic + prepare_df(bad_customer_path=...)`。

### 3. 只解读已有结果 → AGENTS.md 模板 B

用户说"查/读/解读/看 IV/LR/相关性"或"top 特征"时，**切勿重跑管线**：直接用 `load_results` + `top_features`。  
只有 `load_results` 抛 `FileNotFoundError` 时才考虑重跑。

### 4. 结论纳入要求（强制）

- IV > 2.0 的特征：必须标记"过拟合嫌疑"并**排除出结论推荐**，不得正常引用
- AUC 必须附注类型（交叉验证 / 训练集-样本不足 / 训练集-CV失败）
- 跳过的 segment 必须记录原因，不得静默跳过

---

## 结果确定性层次（执行前对齐用户预期）

```
Level 1 — 分析结论可用（8 张 CSV + LLM JSON 落盘）
  → 可做：查询、审阅、修改后重跑
  → 不可做：对外交付、写入预警名单

Level 2 — 客户级风险落地（触碰三张表落盘）
  → 可做：推送预警名单给业务部门
  → 不可做：底层宽表变更后不重新 extract_triggers

Level 3 — 正式报告交付（.docx 生成并交付）
  → 不可做：修改底层 CSV 而不同步重新出报告
```

开始执行前，告知用户本次目标是 Level 几，并确认数据/结论已达到前置层次。

---

## `generic` 运行前检查

运行前核验以下条件（字段不确定时读 `df.columns`，不猜）：

- 存在稳定主键（默认 `客户编号`，实际字段名需确认）
- 存在目标列（或可从坏客户清单推导）
- 至少有一批可分析的数值特征列
- 用户指定的分群维度列真实存在

---

## CLI 入口（统一走 `python -m risk_pipeline`）

```bash
cd "<pipeline_root>"

# 全流程（generic / credit / gsfc）
python -m risk_pipeline run --pipeline generic \
  --wide data/raw/<宽表>.csv \
  --bad-customer data/raw/<坏客户清单>.csv \
  --id-col 客户编号 --target-col is_bad \
  --project <项目名> --confirmed-new-dataset

python -m risk_pipeline run --pipeline credit          # 征信全流程
python -m risk_pipeline run --pipeline gsfc            # 工商财务全流程

# 单维快路径（CLI 直接接受 --category-dims）
python -m risk_pipeline analyze --project <项目名> \
  --steps univariate,iv,lr --category-dims 企业规模

# 只读已有结果
python -m risk_pipeline query --project <项目名> --kind iv --top 15

# 客户级触碰提取（默认特征仅 GSFC 主题适用；征信/舆情等用 --features-file）
python -m risk_pipeline trigger --project <项目名> \
  --use-default-features --confirmed

# 生成 Word 报告
python -m risk_pipeline report --project <项目名> \
  --report-markdown <md报告>.md --purpose internal

# 生成可视化图表（Level 1 后；--kinds 可选 iv,iv_heatmap,corr,lr,auc,segment,tree,rules,combos,combo_network）
python -m risk_pipeline visualize --project <项目名>
```

> **老入口 `python -m shared --pipeline X` 仍可工作但会打 stderr deprecation 警告**，请尽快迁移到 `python -m risk_pipeline run --pipeline X`。
>
> 复杂参数（filter / exclude_features / 自定义 features）一律走 `--xxx-file *.json` 避免 shell 转义。详细模板见 `AGENTS.md` 六。

---

## 子 Skill 路由

| 子 Skill | 触发场景 | 结果层次 |
|---|---|---|
| `risk_data_prep` | 多表合并、坏客户打标、宽表构建 | 前置 |
| `risk_feature_engineering` | 衍生比率特征、特征工程 | 前置 |
| `risk_segment_univariate` | 分群相关系数、均值差、T 检验 | 过渡态 |
| `risk_iv_diagnosis` | IV、WOE、分箱、IV 可信度 | 过渡态 |
| `risk_logistic_regression` | 分群 LR、系数、AUC | 过渡态 |
| `risk_rule_mining` | 决策树规则、预警/审批规则 | 过渡态 |
| `risk_export_report` | 标准 CSV 导出、LLM JSON、分群画像 | **→ Level 1** |
| `risk_result_query` | **只读**已有结果（top-N、分群查询） | Level 1 后 |
| `risk_trigger_extraction` | 把风险结论落到每个客户（触碰+得分） | **→ Level 2** |
| `risk_docx_report` | LLM JSON → 正式 Word 报告 | **→ Level 3** |
| `risk_visualization` | Level 1 后，IV/相关性/LR/分群/决策树/指标组合 PNG 图表 | Level 1 后 |

---

## agent 运行规范

1. **开始前说明**：本次目标 Level、选中哪条管线、计划跑哪些步骤
2. **长任务渐进汇报**：确认数据结构 → 确认目标列/分群 → 步骤进展 → 文件落地确认
3. **阻断时的输出格式**：见 `AGENTS.md` 七，必须显式输出 `⚠️ [阻断节点 N]`

---

## 调试顺序

1. 看错误在 `shared/pipeline.py` 哪个阶段
2. 确认下游函数签名与透传参数是否一致
3. 检查目标列、主键列、分群列是否真实存在（读 `df.columns`，不猜）
4. 常见错误：`KeyError: 'is_bad'`、`unexpected keyword argument 'target'`、分群字段不存在
