# risk-feature-pipeline 术语表

跨子 Skill 与产物 CSV 的核心词定义。**写代码/读 CSV/解读结果时以此为准，与 `docs/SCHEMA.md` 互补**——SCHEMA.md 描述每张表的列字典，本文件定义跨表共享的核心概念。

---

## 核心四词

### `dim`（分群维度，Chinese: 分群维度）

业务上的**分群依据**列，如：
- `企业规模`、`所属行业`、`客户分层`、`赛道`
- 也可以是衍生标签列，如 `是否腰部企业`、`是否高风险变更`

**约定**：
- 在 CSV 中列名固定为 `分群维度`
- 在 Python API 中参数名固定为 `dim` 或 `category_dims`（多个时 list）
- `analyze --category-dims 企业规模,所属行业` CLI 透传

### `group`（分群名称，Chinese: 分群名称）

某个 `dim` 下的**具体取值**，如 `dim='企业规模'` 时 `group ∈ {'大型企业', '中型企业', '小型企业'}`。

**约定**：
- 在 CSV 中列名固定为 `分群名称`（A4 后统一；旧名 `分群值` 仅在历史 CSV 中存在）
- 在 Python API 中参数名为 `group`
- `query --dim 企业规模 --group 小型企业` CLI 透传

### `scope`（触发范围，Chinese: 适用范围）

特征触发是否限定到某个 `(dim, group)`，仅用于 `risk_trigger_extraction`。支持 4 种形态（详见 `risk_trigger_extraction/SKILL.md`）：

| scope 形态 | 含义 |
|---|---|
| `'full'` | 全量客户（默认） |
| `'waist'` | 仅腰部企业（兼容旧写法） |
| `{"dim": "X", "value": "Y"}` | 单值维度筛选 |
| `{"dim": "X", "values": [...]}` | 多值维度筛选 |

**和 `dim`/`group` 的关系**：scope 是「触发范围限定」，dim/group 是「分群分析依据」。同一份 features.json 里：
- 若 `feat.scope = {"dim": "企业规模", "value": "大型企业"}`：仅大型企业客户在该特征触发
- 若 `--category-dims 企业规模`：分析阶段会按企业规模分群分别算 IV/LR/规则

### `coverage`（覆盖率）

**仅出现在规则表**（`*_风险规则表.csv`）：

- `覆盖样本数` = 命中规则的客户数
- `覆盖率` = 覆盖样本数 / 全样本数（不是坏客户数 / 总坏客户数，那是 `规则坏账率`/整体坏账率 的 lift）

不要把 `覆盖率` 误读为「坏客户占比」。

---

## 列名跨表对照

A4 后统一对外列名：

| 概念 | 对外列名 | 历史列名（兼容读） | 出现位置 |
|---|---|---|---|
| 单特征 | `特征` | `特征名称` | IV / LR / corr / comprehensive |
| 特征列表 | `涉及特征` | （不变） | 风险规则表 |
| 分群维度 | `分群维度` | （不变） | IV / LR / corr / 规则 |
| 分群名称 | `分群名称` | `分群值` | IV / LR / corr / 规则 |
| 分群标识 | `分群` | （不变） | iv_full 内部表（值 = `'全量'` / `'<dim>.<group>'`） |
| 适用范围 | `适用范围` | （不变） | trigger 长表 / 阈值说明 |

`risk_result_query.load_results()` 读取时自动 normalize 历史列名 → 新列名，故消费 DataFrame 时统一按新列名访问。

---

## 文件名约定

| 模式 | 含义 | 示例 |
|---|---|---|
| `<project>_<语义>.csv` | Level 1 标准产物（8 张） | `舆情_IV分析结果_全量.csv` |
| `<project>_LLM_<语义>.csv` | LLM 报告辅助产物 | `舆情_LLM_分群画像.csv` |
| `<project>_LLM报告数据.json` | LLM 报告 JSON | 同上 |
| `<project>_风险触碰明细_<宽表/长表>.csv` | Level 2 trigger 输出 | `舆情_风险触碰明细_宽表.csv` |
| `<project>_audit.json` | C12 机器可读自检 | `舆情_audit.json` |
| `<project>_风险规则表.csv` | 决策树规则（analyze --steps rules 后） | 同上 |

---

## 阻断节点缩写

| 节点 | 名称 | 必传 flag |
|---|---|---|
| 阻断节点 1 | 首次新数据集 | `--confirmed-new-dataset` |
| 阻断节点 2 | trigger features 配置 | `--confirmed`（trigger 子命令） |
| 阻断节点 3 | external 报告 | `--confirmed-final-version`（report 子命令） |

详见 `AGENTS.md` 五。

---

## 状态层级

| Level | 意义 | 进入条件 |
|---|---|---|
| 前置态 | prepared.csv + features.json 已生成 | `prepare` 完成 |
| 过渡态 | `_intermediate/` 下有中间产物 | `analyze` 完成 |
| **Level 1** | 8 张 CSV + LLM JSON 已落盘 | `export` 完成 |
| **Level 2** | trigger 三件套已落盘 | `trigger` 完成 |
| **Level 3** | 正式 .docx 已生成 | `report` 完成 |

**任何 Level 1 之前的中间结果不能作为结论引用**（详见 `AGENTS.md` 二）。
