# `analyze` —— 分析步骤（→ 过渡态；产物落 `_intermediate/`）

```bash
# 单维快路径（已有 prepared.csv）
python -m risk_pipeline analyze \
  --project <项目名> \
  --steps univariate,iv,lr \
  --category-dims 企业规模 \
  --qual-dims ""               # 空字符串 = 不算资质标签

# 带规则挖掘（供 visualize 出规则散点/组合图）
python -m risk_pipeline analyze --project <项目名> \
  --steps univariate,iv,lr,rules --category-dims 企业规模
```

后接 `python -m risk_pipeline export --project <项目名>` 才落 Level 1。

## 雷区

- CLI 强制按 `univariate→iv→lr→rules` 排序；**禁止 `--steps export`**（export 是独立子命令）。
- 产物在 `data/processed/<project>/_intermediate/`，属**过渡态**，不能作为结论引用（见 levels.md）。
- 要做决策树/规则/指标组合可视化，必须 `--steps ...,rules`——rules 步拟合树并落 pkl，
  export 阶段自动把规则表写到 `data/results/<project>/<project>_风险规则表.csv`。
- **`--steps rules` 单跑时 `--category-dims` 必须是前置 analyze 已用维度的子集**，
  否则与 `_intermediate/` 已落盘的 corr/iv_group/lr 维度错位，CLI 直接 SystemExit。
- `--category-dims` 缺省 = 自动检测（YAML 期望维度 ∩ 实际列）；prepare 阶段命中率
  为 0 时分析退化为全样本并在 stderr 提示。
