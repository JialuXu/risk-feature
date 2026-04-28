---
name: risk_result_query
description: 读取并查询 risk-feature-pipeline 已导出的风险特征分析结果（IV、LR、相关性、综合表、LLM JSON）。当用户说"查/读/解读/看 IV/LR/相关性/分群结果"、"top 特征"、"某分群表现"、"分析结果在哪"时触发。本 skill 只读文件、不重跑管线；需要新算结果才触发 risk-feature-pipeline 主 skill。
---

## 核心规矩

1. **先查再跑**：看到"查/解读/top/哪些特征"类问题，**默认用本 skill 从磁盘读 CSV**，不要调用 `run_generic_pipeline`
2. **确认结果是否存在**：`load_results(project_name)` 若抛 `FileNotFoundError`，再考虑走主 skill 重跑
3. **只取所需**：用 `top_features()` / DataFrame 过滤 + `head(N)`，禁止打印整张矩阵
4. **列名不要猜**：按本页 API 返回的对象属性访问；完整列名表见 `references/columns.md`

## 快速开始

```python
from risk_result_query.scripts.results_loader import load_results, top_features

r = load_results('舆情特征分析')        # 自动搜索 data/results/<project>/ 等多个候选路径
r.iv_full                               # 全量 IV DataFrame
r.iv_group_all                          # 分群 IV
r.corr_long / r.diff_long               # 相关性 / 均值差（长格式）
r.lr_coef_long / r.lr_auc_long          # LR 系数 / AUC（长格式）

top_features(r, kind='iv', group='小型企业', dim='企业规模', n=15)
top_features(r, kind='lr', group='小型企业', dim='企业规模', n=15, sign='positive')
top_features(r, kind='corr', group='小型企业', dim='企业规模', n=15)
```

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
