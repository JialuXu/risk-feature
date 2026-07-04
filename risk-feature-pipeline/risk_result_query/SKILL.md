---
name: risk_result_query
description: 读取并查询 risk-feature-pipeline 已导出的风险特征分析结果（IV、LR、相关性、综合表、LLM JSON）。当用户说"查/读/解读/看 IV/LR/相关性/分群结果"、"top 特征"、"某分群表现"、"分析结果在哪"时触发。本 skill 只读文件、不重跑链路；需要新算结果才触发 risk-feature-pipeline 主 skill。
---

> **何时读我**：只有需要 Python API 级查询（`load_results`/`top_features` 直调、notebook 调研）时才读本文件；常规查询走 `python -m risk_pipeline query`（见 `references/cli/query.md`）。

## 核心规矩

1. **先查再跑**：看到"查/解读/top/哪些特征"类问题，**默认用 `query` 子命令读磁盘**，不要重跑链路（`run`/`analyze`）
2. **确认结果是否存在**：`query` 若报结果不存在（`FileNotFoundError`），再考虑走主 skill 重跑
3. **只取所需**：用 `--top N`，禁止整表打印
4. **列名不要猜**：完整列名表见 `references/columns.md`

## 快速开始（agent 走 CLI）

```bash
python -m risk_pipeline query --project 舆情特征分析 --kind iv --top 15                              # 全量 IV
python -m risk_pipeline query --project 舆情特征分析 --kind iv_group --dim 企业规模 --group 小型企业 --top 15
python -m risk_pipeline query --project 舆情特征分析 --kind lr   --dim 企业规模 --group 小型企业 --top 15 --sign positive
python -m risk_pipeline query --project 舆情特征分析 --kind corr --dim 企业规模 --group 小型企业 --top 15
# --output-format table（默认）/ csv / json
```

> `--kind`：`iv`（全量，不接受 dim/group）/ `iv_group`（分群）/ `corr`（分群相关）/ `lr`（分群 LR，可带 `--sign`）。
> 要看**整张表或 LLM JSON**（`query` 只出 top-N）：直接读对应文件——横向对比 IV 读 `_IV值透视表.csv`（行=分群、列=特征）最快，高层结论读 `_LLM报告数据.json`；文件清单见 `references/file_layout.md`。
> `query` 背后是 `results_loader.load_results` / `top_features`（仅 notebook 直接 import；agent 走 CLI）。

## 何时加载扩展参考（渐进式披露）

本 SKILL.md 只给最小调用面。以下材料**按需再 Read**：

| 场景 | 再读 |
|---|---|
| 需要 DataFrame 精确列名 / 想直接手写过滤 | `references/columns.md` |
| 需要非标准查询（透视、多分群对比、缺失模式）| `references/query_recipes.md` |
| 需要看原始 CSV 文件名与磁盘位置 | `references/file_layout.md` |
| 需要解析 `r.llm_report` / 撰写 Word 报告 | `risk_export_report/references/llm_json_schema.md` |

## 典型触发消息（agent 应识别）

- "舆情特征分析 top 10 IV"
- "看一下小型企业分群的 LR 系数"
- "相关性最高的是哪些特征"
- "读取已有分析结果"
- "分群 AUC 表现"

## 不在本 skill 的职责

- 不跑 IV/LR/单变量分析 → `risk-feature-pipeline` 主 skill
- 不做数据预处理/合并坏客户 → `risk_data_prep`
- 不生成新 CSV / 不改文件 → 只读
