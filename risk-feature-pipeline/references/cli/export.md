# `export` —— 落 Level 1 的唯一合法入口

```bash
python -m risk_pipeline export --project <项目名>
```

从 `_intermediate/` 重建结果 → 8 张 CSV + LLM JSON + `_audit.json`，推进到 **Level 1**。
完整产物清单见 [levels.md](../levels.md)。

## 雷区

- 必须先有 `_intermediate/`（analyze 产出），否则 exit 1 提示先跑 analyze。
- 导完随手 `cat data/results/<project>/<project>_audit.json`：
  `iv_overfit_features`（IV>2 疑似数据穿越，必须排除出结论）与
  `unstable_rules`（不稳定规则，不得直接写进政策）两个列表在报结论前必须核对。
