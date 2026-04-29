---
name: risk_visualization
description: 把 risk-feature-pipeline 已落 Level 1 的分析结果（IV / 相关性 / LR / 分群画像 / 决策树规则 / 指标组合）渲染成 PNG 图表。当用户说"画图/可视化/出图/IV 条形图/LR 系数图/决策树图/指标组合图"或在 query 之外要求"看图"时触发。本 skill 只读磁盘快照 + 出 PNG，不重跑管线、不改 CSV。
---

## 核心规矩

1. **只读后置**：所有图都基于 `data/results/<project>/` 下已经落盘的 8 张 CSV + 1 份 JSON + 可选的 `_风险规则表.csv`，与 `risk_result_query` 同源
2. **结果不存在时报错而非静默**：用 `load_results(project_name)` 找不到目录会抛 `FileNotFoundError`，由调用方决定要不要先跑 export
3. **决策树两条路**：优先读 `_intermediate/rule_tree_*.pkl`（用 `sklearn.tree.plot_tree` 出真树），找不到时自动降级为按规则文本反推的"规则路径图"
4. **中文字体**：`scripts/font_utils.py` 在模块加载时自动按 OS 探测中文字体，全部 miss 只 warn 不报错（fallback 渲染 CJK 会变方框）

## 前置条件

| 图 | 前置 |
|---|---|
| `iv` / `iv_heatmap` / `corr` / `lr` / `auc` / `segment` | `analyze --steps univariate,iv,lr` + `export`（标准 Level 1） |
| `tree` / `rules` / `combos` / `combo_network` | analyze 必须包含 `rules` 步骤：<br/>`python -m risk_pipeline analyze --project <name> --steps univariate,iv,lr,rules --category-dims <dim>`<br/>然后 `python -m risk_pipeline export --project <name>`<br/>这样 `_intermediate/rule_tree_*.pkl` + `data/results/<project>/<project>_风险规则表.csv` 才会落盘 |

**没跑 `rules` 时这 4 张图会被 visualize 自动跳过**（status stamp 里会显示 `skipped=tree,rules,combos,combo_network`），不会报错。

## 快速开始

```python
from risk_visualization.scripts.visualize import generate_charts

paths = generate_charts(
    project_name='舆情特征分析',
    kinds=None,        # None = 全部 10 类
    top_n=15,
    dim='企业规模',    # 限定单一分群维度（不传则跨维度都画）
    dpi=300,
)
# paths = {'iv': ['output/.../charts/iv_top15.png'], 'iv_heatmap': [...], ...}
```

CLI（推荐）：

```bash
python -m risk_pipeline visualize --project 舆情特征分析
python -m risk_pipeline visualize --project 舆情特征分析 \
    --kinds iv,lr,combos --top 20 --dim 企业规模
```

## 支持的图表（10 种）

| `kinds=` | 图表 | 输入 | 数量 |
|---|---|---|---|
| `iv` | 全量 IV 横向条形图（top-N，按预测能力着色） | `_IV分析结果.csv` | 1 |
| `iv_heatmap` | 分群 IV 热力图（不可信单元打 ✗） | `_IV值透视表.csv` + `_IV可信度透视表.csv` | 1 |
| `corr` | 分群相关系数条形图（每分群一张，正负双色） | `_特征风险相关性.csv` | N（分群数） |
| `lr` | LR 系数条形图（每分群一张，按 \|系数\| 排序） | `_逻辑回归系数.csv` | N |
| `auc` | 跨分群 AUC 条形图（按 AUC 类型着色） | `_逻辑回归系数.csv` | 1 |
| `segment` | 分群画像图（坏客户率柱图 + 样本数标注） | `_LLM_分群画像.csv` | 1 |
| `tree` | 决策树图（pkl 真树 / 规则反推退化） | `_intermediate/rule_tree_*.pkl` 或 `_风险规则表.csv` | 0–N |
| `rules` | 规则 lift × coverage 散点（按稳定性着色） | `_风险规则表.csv` | 1 |
| `combos` | 指标组合 max lift 条形图（按 feature_list 聚合） | `_风险规则表.csv` | 1 |
| `combo_network` | 特征共现网络（节点=特征，边=共现规则数） | `_风险规则表.csv` | 1 |

## 何时加载扩展参考（渐进式披露）

| 场景 | 再读 |
|---|---|
| 想看每张图的解读、常见误读、何时不该用 | `references/chart_types.md` |
| 想自定义调色板 / 字体 / dpi / 长宽 | 直接改 `scripts/style.py` |
| 想新增一类图 | 仿 `chart_iv.py` 加文件，并在 `visualize.py:CHART_REGISTRY` 注册 |

## 不在本 skill 的职责

- 不跑 IV/LR/单变量分析 → `risk-feature-pipeline` 主 skill
- 不读已有结果做 top-N 表 → `risk_result_query`
- 不生成 HTML / 交互式图表（PNG 静态图为唯一形态）
- 不嵌入 .docx 报告（保留给 `risk_docx_report` 自行决定要不要引用 PNG）
