---
name: risk-feature-pipeline
description: 企业风险特征分析总控技能。适用于"帮我做风险特征分析""挖掘这份宽表里的风险特征""分析不同企业规模/行业/客群分群下是什么特征""读 CSV 后输出分群画像、IV、LR、综合结论"等请求；内部自动选择 `credit` / `gsfc` / `generic` 链路，并决定走全流程、单维快路径或只读结果。
---

# Risk Feature Pipeline 调度器

本 Skill 只负责**把用户意图映射到正确的 CLI 命令**，不重写分析逻辑。用户无需说出 `credit`/`IV`/`LR` 等技术词——由本 Skill 判断。

> **执行任何步骤前先读 `AGENTS.md`**：硬规矩（绝对触发/排斥、核验路径、响应自检）都在那里，本文件不重复，只做路由。命令模板/阻断节点全文/Level 定义在 `references/` 按任务懒加载——**先查 `references/_index.md` 决定读哪张卡**。
>
> **铁律**：agent 工作流一律走 `python -m risk_pipeline <子命令>`，**禁止**在 Bash 里 import 模块手抄代码（详见 `AGENTS.md` 一、三）。
>
> **沙盒/安装模式**（skill 代码目录 ≠ 数据目录）：跑任何 CLI 前先 `export RISK_PROJECT_ROOT=<数据根> RISK_OUTPUT_ROOT=<可写输出根>`，否则产物会写进代码树（详见 `references/paths-env.md`）。

---

## 第一步：是否需要阻断？

下列情况**先输出确认请求，等用户回复再继续**（文案与清单见 `references/blocking-gates.md`）：

- 用户给的是**没见过的宽表 / 切了银行配置** → 阻断节点 1（`prepare`/`run` 须带 `--confirmed-new-dataset`）
- 要做**触碰提取**但未明确 features 配置 → 阻断节点 2（`trigger` 须带 `--confirmed`）
- 要生成**正式对外 Word 报告** → 阻断节点 3（`report --purpose external` 须带 `--confirmed-final-version`）

## 第二步：用户意图 → CLI 命令

| 用户说 | 跑这条 | 说明 |
|---|---|---|
| "查/读/看/解读/top X/已有结果" | `python -m risk_pipeline query --project X --kind iv --top 15` | **不重跑链路**；详见 `risk_result_query` |
| "帮我分析这份宽表/做风险特征分析"（自带宽表） | `python -m risk_pipeline run --pipeline generic --wide … --confirmed-new-dataset` | 全流程；缺目标列见下方 |
| "跑征信主题 / 工商财务主题分析" | `python -m risk_pipeline run --pipeline credit`（或 `gsfc`） | 数据路径走 `config/` 默认 |
| "只看某个分群维度" | `python -m risk_pipeline analyze --project X --steps univariate,iv,lr --category-dims 企业规模` 然后 `export` | 单维快路径，不默认跑所有维度 |
| "要预警规则/审批红线/贷后检查项" | `run/analyze` 带 `--steps …,rules` 再 `export` | 决策树多变量规则，落 `_风险规则表.csv` |
| "这几个 (分群,特征) 探一下阈值/候选规则评审" | `python -m risk_pipeline explore_thresholds --project X --pairs-file pairs.csv` | Level 1 后只读；详见 `risk_threshold_explore` |
| "哪些客户触碰阈值/风险预警名单/客户级扫描" | `python -m risk_pipeline trigger --project X --use-default-features --confirmed` | 先过阻断节点 2；详见 `risk_trigger_extraction` |
| "画图/可视化/IV 条形图/AUC 图" | `python -m risk_pipeline visualize --project X` | Level 1 后只读出图 |
| "生成 Word/正式报告" | `python -m risk_pipeline report --project X --report-markdown r.md --purpose internal` | 先过阻断节点 3 |

> 完整命令模板（全部 flag、复杂 filter 走 `--xxx-file *.json` 等）见 `references/cli/<子命令>.md`。

## 第三步：全流程时选链路

| 链路 | 何时选 |
|---|---|
| `generic` | 用户已给宽表 CSV，不想重走内置数据准备（最常用） |
| `credit` | 跑征信主题，数据走 `config/` 默认路径；要求内置数据已按 `risk_core/config/default.yaml` 布局放在项目根下（沙盒里默认没有，只有 `generic` 开箱可用） |
| `gsfc` | 跑工商财务主题，数据走 `config/` 默认路径；同上要求内置数据存在 |

---

## 场景定位（决定怎么措辞结论）

本 Skill 服务于**贷前业务建议**与**贷后预警规则**，**不是**评分卡/模型评估。因此：

- 结论与建议落在「信号强度（IV）+ 跨分群稳定性（方向一致）→ 可操作的关注点 / 预警阈值」
- AUC、"原始 vs 衍生 AUC 对比" 只作**诊断性佐证**，不得当结论主角或排序依据
- 阈值类预警规则的有效性以**风险倍数 / lift / 覆盖率 / 卡方**为准（见 `risk_threshold_explore`）

## `generic` 运行前核验（字段不确定就读 `df.columns`，不猜）

- 有稳定主键（默认 `客户编号`，实际名需确认）
- 有目标列，或能从坏客户清单推导
- 至少一批可分析的数值特征列
- 用户指定的分群维度列真实存在

**缺目标列时**不得擅自改做无监督分析，须输出：
> "当前宽表缺少 `is_bad` 列，无法做 IV/LR/坏客户相关性分析。请补充坏客户清单（如 `data/raw/坏客户标记.csv`），或提供含目标列的文件。"
> 坏客户清单已有时：走 `generic` + `--bad-customer <清单>`（`prepare_df` 自动打标）。

---

## 子 Skill 路由

| 子 Skill | 触发场景 | 对应 CLI | 结果层次 |
|---|---|---|---|
| `risk_data_prep` | 多表合并、坏客户打标、宽表构建 | `prepare` / `run` | 前置 |
| `risk_feature_engineering` | 衍生比率特征 | `run`（step）| 前置 |
| `risk_segment_univariate` | 分群相关、均值差、T 检验 | `analyze --steps univariate` | 过渡态 |
| `risk_iv_diagnosis` | IV、WOE、分箱、IV 可信度 | `analyze --steps iv` | 过渡态 |
| `risk_logistic_regression` | 分群 LR、系数、AUC | `analyze --steps lr` | 过渡态 |
| `risk_rule_mining` | 决策树规则、预警/审批规则 | `analyze --steps …,rules` | 过渡态 |
| `risk_export_report` | 标准 CSV、LLM JSON、分群画像 | `export` | **→ Level 1** |
| `risk_result_query` | **只读**已有结果（top-N、分群查询） | `query` | Level 1 后 |
| `risk_threshold_explore` | 候选规则阈值探索（单变量 optbinning） | `explore_thresholds` | Level 1 后 |
| `risk_trigger_extraction` | 风险结论落到每个客户（触碰+得分） | `trigger` | **→ Level 2** |
| `risk_visualization` | IV/相关/LR/分群/规则 PNG 图表 | `visualize` | Level 1 后 |
| `risk_docx_report` | LLM JSON → 正式 Word 报告 | `report` | **→ Level 3** |

结果层次（Level 1/2/3）的达成条件与"能做/不能做"清单见 `references/levels.md`。**开始执行前先告诉用户本次目标是 Level 几。**

---

## 调试顺序

1. 看错误落在 `risk_pipeline/pipeline.py` 哪个阶段
2. 确认下游函数签名与透传参数一致
3. 读 `df.columns` 核对目标列/主键列/分群列真实存在（不猜）
4. 常见错误：`KeyError: 'is_bad'`、`unexpected keyword argument 'target'`、分群字段不存在
