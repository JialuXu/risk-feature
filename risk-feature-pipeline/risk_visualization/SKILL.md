---
name: risk_visualization
description: 把 risk-feature-pipeline 已落 Level 1 的分析结果（IV / 相关性 / LR / 分群画像 / 规则 / 指标组合）渲染成**面向业务报告**的 PNG 图表。当用户说"画图/可视化/出图/IV 条形图/AUC 图/指标组合图"或在 query 之外要求"看图"时触发。本 skill 只读磁盘快照 + 出 PNG，不重跑链路、不改 CSV。
---

## 核心规矩

1. **只读后置**：所有图都基于 `data/results/<project>/` 下已经落盘的 8 张 CSV + 1 份 JSON + 可选的 `_风险规则表.csv`，与 `risk_result_query` 同源
2. **结果不存在时报错而非静默**：用 `load_results(project_name)` 找不到目录会抛 `FileNotFoundError`，由调用方决定要不要先跑 export
3. **面向业务报告的取舍**：只产"全局概览 + 每个分群维度一张的热力图/对比图"，不出每分群散图与随分群数爆炸的细图。
4. **中文字体**：`scripts/font_utils.py` 在模块加载时自动按 OS 探测中文字体，全部 miss 只 warn 不报错（fallback 渲染 CJK 会变方框）
5. **依赖隔离**：matplotlib / seaborn 是本 Skill 的**硬依赖**但**不在核心链路依赖**里——`visualize.py` 顶部 try-import，缺失时给出可执行的安装命令（`pip install -e .[viz]` 或 `pip install matplotlib seaborn`）

## 前置条件

| 图 | 前置 |
|---|---|
| `iv` / `iv_heatmap` / `corr_heatmap` / `lr_heatmap` / `auc` / `segment` | `analyze --steps univariate,iv,lr` + `export`（标准 Level 1） |
| `rules` / `combos` | analyze 必须包含 `rules` 步骤：`python -m risk_pipeline analyze --project <name> --steps univariate,iv,lr,rules --category-dims <dim>` 然后 `export`，这样 `data/results/<project>/<project>_风险规则表.csv` 才会落盘 |
| `thresholds` | 先跑 `python -m risk_pipeline explore_thresholds`，产出候选阈值表 + 分箱明细 |

**前置缺失的图会被 visualize 自动跳过**（status stamp 里会显示 `skipped=...`），不会报错。

## 快速开始（agent 走 CLI）

```bash
python -m risk_pipeline visualize --project 舆情特征分析
python -m risk_pipeline visualize --project 舆情特征分析 \
    --kinds iv,lr_heatmap,combos --top 20 --dim 企业规模
```

> 底层 `generate_charts(project_name, kinds, top_n, dim, dpi)` 仅 notebook 直接 import；agent 走上面 CLI。

## 支持的图表（9 种）

| `kinds=` | 图表 | 输入 | 数量 |
|---|---|---|---|
| `iv` | 全量 IV 横向条形图（top-N，按预测能力着色） | `_IV分析结果_全量.csv` | 1 |
| `iv_heatmap` | **分群 × 特征 IV 热力图**（每维度一张；行=该维度各分群、列=特征 top-N，不可信单元打 X） | `_IV分析结果_分群.csv`（长表，带 `分群维度`） | M（分群维度数） |
| `corr_heatmap` | **分群 × 特征 相关系数热力图**（行=分群、列=特征 top-N，发散色以 0 为中心） | `_特征风险相关性.csv` | M（分群维度数） |
| `lr_heatmap` | **分群 × 特征 LR 系数热力图**（行=分群、列=特征 top-N，发散色以 0 为中心） | `_逻辑回归系数.csv` | M |
| `auc` | 跨分群 AUC 条形图（按 AUC 类型着色） | `_逻辑回归系数.csv` | 1 |
| `segment` | 分群画像图（坏客户率柱图 + 样本数标注） | `_LLM_分群画像.csv` | 1 |
| `rules` | 规则 lift × coverage 散点（按稳定性着色） | `_风险规则表.csv` | 1 |
| `combos` | 指标组合 max lift 条形图（按 feature_list 聚合） | `_风险规则表.csv` | 1 |
| `thresholds` | 候选阈值分箱坏率图 + 风险倍数对比图 | `_候选阈值表.csv` + `_候选阈值_分箱明细.csv` | 0–N |

> **业务视角**：`iv_heatmap` / `corr_heatmap` / `lr_heatmap` 三张图都把"分群"放纵轴、"特征"放横轴。
> 一行 = 一个分群（如 `企业规模 = 小型企业`）的横向画像，从左到右扫一眼就能比较"同一指标在不同分群的表现是否一致"。
> 一列里出现红蓝切换 = 该特征跨分群符号冲突，往往不能直接进入通用规则。

## 何时加载扩展参考（渐进式披露）

| 场景 | 再读 |
|---|---|
| 想看每张图的解读、常见误读、何时不该用 | `references/chart_types.md` |
| 想自定义调色板 / 字体 / dpi / 长宽 | 直接改 `scripts/style.py` |
| 想新增一类图 | 仿 `chart_iv.py` 加文件，并在 `visualize.py` 的 `ALL_KINDS` + `generate_charts` 分支里注册 |

## 不在本 skill 的职责

- 不跑 IV/LR/单变量分析 → `risk-feature-pipeline` 主 skill
- 不读已有结果做 top-N 表 → `risk_result_query`
- 不生成 HTML / 交互式图表（PNG 静态图为唯一形态）
- 不嵌入 .docx 报告（保留给 `risk_docx_report` 自行决定要不要引用 PNG）
