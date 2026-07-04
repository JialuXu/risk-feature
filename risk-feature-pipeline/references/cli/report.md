# `report` —— LLM JSON → Word 报告（→ Level 3）

**对外交付先过阻断节点 3**（见 [blocking-gates.md](../blocking-gates.md)）。

```bash
# internal 用途（内部审阅）
python -m risk_pipeline report --project <项目名> \
  --report-markdown <已写好的 md 报告.md> \
  --purpose internal

# external 用途（对外交付）必须额外加 --confirmed-final-version
python -m risk_pipeline report --project <项目名> \
  --report-markdown <已写好的 md 报告.md> \
  --purpose external --confirmed-final-version
```

## 雷区

- 报告标题由 `--purpose` 自动选择，不要另传。
- 写作约束（措辞/结构/禁写项）见 `report-prompt.md`；正文 markdown 先按它写好再喂给本命令。
- Level 3 后修改任何底层 CSV 必须同步重新出报告（见 levels.md）。
