# CHANGELOG — 版本变更代号索引

本文件是 `AGENTS.md` / `CLAUDE.md` / 历史提交中出现的版本变更代号（A1/A4/B6/C11 …）的唯一查询处。
**各子 Skill 的 SKILL.md 正文只描述当前行为，不再引用这些代号**——业务用户和执行 agent 无需了解变更史。

## A 系列 — 命名与产物收敛

| 代号 | 变更内容 | 影响面 |
|---|---|---|
| A1 | trigger 默认特征常量由 `RISK_FEATURES` 改名为 `RISK_FEATURES_GSFC`（明确仅适配工商财务主题）；`RISK_FEATURES` 保留为向后兼容 alias | `risk_trigger_extraction/scripts/config.py` |
| A4 | 产物 CSV 对外列名统一为 `特征` / `分群维度` / `分群名称`；旧列名 `特征名称` / `分群值` 仅存在于历史 CSV，`load_results()` 读取时自动 rename | 全部 Level 1 产物 + 规则表 |
| A5 | IV 结果文件按颗粒度拆分：`_IV分析结果_全量.csv` + `_IV分析结果_分群.csv`；旧名 `_IV分析结果.csv` / `_IV值分析.csv` 仍各写一份兼容副本，**下版本移除** | `risk_export_report` |

## B 系列 — 行为变更与守门

| 代号 | 变更内容 | 影响面 |
|---|---|---|
| B6 | trigger 宽表 CSV 默认**不再包含** `is_bad` / `企业规模` 等业务元信息列（避免与 `prepared.csv` merge 撞列）；需保留时传 `keep_metadata_cols=[...]` 或 CLI `--keep-metadata-cols` | `risk_trigger_extraction` |
| B8 | export 完成时若存在 `稳定性等级=不稳定` 的规则，stdout 列出前 5 条（段-规则编号-CV 折数），同时写入 `_audit.json` 的 `unstable_rules` 字段 | `risk_export_report` / `risk_rule_mining` |
| B10 | （留位，未实施）`risk_pipeline.paths.unified_results_dir(project, 'level2')` 已就位，后续将把 trigger 默认输出从 `output/<project>/` 切换到 `data/results/<project>/level2/`；届时旧路径仍向后兼容读取 | `risk_trigger_extraction` |

## C 系列 — CLI 与自检

| 代号 | 变更内容 | 影响面 |
|---|---|---|
| C11 | 规则条件文本的阈值精度按特征名自适应：比率类（占比/比率/率/系数）→ 2 位小数；金额类（金额/余额/资产/收入/负债/现金/存款/贷款）→ 整数 + 千分位；其它 `:.4g` | `risk_rule_mining` / `risk_threshold_explore` |
| C12 | 新增 `{project}_audit.json` 机器可读自检（IV>2 过拟合特征、不稳定规则、Level 状态）；agent 报回结论前须 cat 对照 | `risk_export_report` |
| C15 | `--confirmed-new-dataset` 支持拆分为三件套：`--confirmed-id-col` / `--confirmed-target-col` / `--confirmed-target-positive` | `prepare` / `run` 子命令 |
