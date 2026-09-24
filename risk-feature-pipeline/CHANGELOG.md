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
| B8 | export 完成时若存在 `稳定性等级=不稳定` 的规则，stdout 列出前 5 条（段-规则编号-有效重抽样次数），同时写入 `_audit.json` 的 `unstable_rules` 字段（D2 起字段为 `稳定性有效次数` + `评估口径`，原 `CV有效折数` 废弃） | `risk_export_report` / `risk_rule_mining` |
| B10 | （留位，未实施）`risk_pipeline.paths.unified_results_dir(project, 'level2')` 已就位，后续将把 trigger 默认输出从 `output/<project>/` 切换到 `data/results/<project>/level2/`；届时旧路径仍向后兼容读取 | `risk_trigger_extraction` |

## D 系列 — 统计口径（设计检视整改）

| 代号 | 变更内容 | 影响面 |
|---|---|---|
| D1 | 缺失值统一口径（`risk_core/missing.py`）：统计检验（相关/均值差/T 检验）成对删除；逻辑回归/规则/阈值用中位数填补且训练与评估同一套填补值；IV/WOE 缺失单独成箱。credit/gsfc 老链路保持原口径（golden 钉死） | generic 链路相关系数、LR 系数与 AUC；规则命中；`calc_woe_table` |
| D2 | 规则改为留出评估：分层 70/30，训练集挖树，Lift/闸门/建议用途在测试集计算；稳定性改为测试集 bootstrap。规则表新增 `训练集Lift` / `评估口径`，`CV坏账率*` / `CV有效折数` 改为 `稳定性坏账率*` / `稳定性有效次数` / `稳定性重抽样次数`；YAML `cv_splits`/`stability_min_folds` 改为 `holdout_ratio`/`holdout_min_bad`/`bootstrap_n`/`stability_min_valid_ratio` | `risk_rule_mining` / `_风险规则表.csv` / `_audit.json` |
| D3 | 触碰阈值只在 scope 内计算；新增 `方向校验` 列与 stderr 告警；scope 维度列缺失时跳过该特征（原为套用到全量） | `risk_trigger_extraction` / `_触碰阈值说明.csv` |
| D4 | IV 零膨胀特征（众数占比高、qcut 塌成 1 箱）改为「众数单独成箱 + 其余等频」，不再 IV=0 | `iv_core.calc_iv` |

## C 系列 — CLI 与自检

| 代号 | 变更内容 | 影响面 |
|---|---|---|
| C11 | 规则条件文本的阈值精度按特征名自适应：比率类（占比/比率/率/系数）→ 2 位小数；金额类（金额/余额/资产/收入/负债/现金/存款/贷款）→ 整数 + 千分位；其它 `:.4g` | `risk_rule_mining` / `risk_threshold_explore` |
| C12 | 新增 `{project}_audit.json` 机器可读自检（IV>2 过拟合特征、不稳定规则、Level 状态）；agent 报回结论前须 cat 对照 | `risk_export_report` |
| C15 | `--confirmed-new-dataset` 支持拆分为三件套：`--confirmed-id-col` / `--confirmed-target-col` / `--confirmed-target-positive` | `prepare` / `run` 子命令 |
