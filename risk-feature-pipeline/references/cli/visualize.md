# `visualize` —— Level 1 后只读出图（不改 level）

```bash
python -m risk_pipeline visualize --project <项目名>
# 产物：output/<project>/charts/*.png
```

面向业务报告，共 9 类图：`iv`（IV 条形）、`iv_heatmap`、`corr_heatmap`、`lr_heatmap`、`auc`、
`segment`（分群画像）、`rules`（规则 lift×coverage 散点）、`combos`（指标组合 max-lift）、`thresholds`（候选阈值图）。
各图含义与常见误读见 `risk_visualization/references/chart_types.md`。

## 雷区

- 读的是磁盘快照（与 query 同源），上游重跑后须重新出图。
- 规则散点/组合图需要 analyze 时带过 `--steps ...,rules`（见 cli/analyze.md）。
- 中文字体缺失时只 warn 不报错——fallback 字体渲染中文会变方框，交付前检查 PNG。
