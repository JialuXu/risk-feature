# `explore_thresholds` —— 候选规则阈值探索（Level 1 后；不改 level）

对人工挑好的 (分群, 特征) 组合跑 optbinning 单变量最优切点 + 五道门槛业务判定。

```bash
python -m risk_pipeline explore_thresholds --project <项目名> \
  --pairs-file pairs.csv
```

`--pairs-file` 支持两种格式：
- `.csv`：表头必须含 `分群维度,分群名称,特征`
- `.json`：`list[dict]`，每个 dict 含同名三键

产物（`data/results/<project>/`）：`{project}_候选阈值表.csv` +
`{project}_候选阈值_分箱明细.csv`，并向 `_audit.json` 追加节点。

## 雷区

- 前置 Level 1（先 export）+ 需要 `prepared.csv` 在位（或 `--prepared` 指定）。
- 五道门槛（min-risk-ratio 等）可用同名 flag 逐项覆盖，默认值见
  `risk_threshold_explore/scripts/config.py`。
- 只读探索，不推进 level；结论进政策前仍需人工评审。
