# 阻断节点（物理 exit 1，等待人类确认）

> 单一真源：本文件。三个节点由 CLI 物理阻断（exit 1 + 打印文案），agent 必须
> **原样转发文案给用户，等待明确回复后才继续**，不允许替用户确认。

## 阻断节点 1 — 首次运行新数据集之前（`prepare` / `run`）

**触发条件：** 用户提供从未见过的宽表路径，或切换了银行/项目配置。

**阻断原因：** `id_col`、`target_col`、坏客户定义一旦跑错，后续 8 张 CSV 全部污染，无法从结果层面发现。

**必须确认：**
- [ ] 主键字段名（默认 `客户编号`，实际是？）
- [ ] 坏客户标签列名与定义（1=坏客户还是其他？）
- [ ] 是否需要 `filter` 排除某些企业规模/行业

**放行方式（任选其一）：**
- 一键版：`--confirmed-new-dataset`
- 拆分版（推荐，留审计痕迹）：`--confirmed-id-col <主键> --confirmed-target-col <目标列> --confirmed-target-positive 1`（三件套必须全填且与 `--id-col/--target-col` 一致）

## 阻断节点 2 — trigger 生成预警名单之前

**触发条件：** 用户要求触碰提取（无论默认还是自定义 features 配置）。

**阻断原因：** 触碰阈值依赖的特征集错误会直接导致预警名单错误，是可运营决策的上游，一旦推送给业务部门不可撤回。

**必须确认：**
- [ ] 当前数据是否 GSFC（工商财务）主题？是 → 可用默认 `--use-default-features`；否 → 必须 `--features-file`
- [ ] 如用专属列表，用户已确认每个特征的 `risk_direction` 和 `iv`

**放行方式：** `--confirmed`。

**默认特征匹配率守门（数值单一真源）：** 默认特征仅适配 GSFC 主题；其它主题误用
默认时，若宽表列匹配率低于 `MIN_DEFAULT_FEATURE_MATCH_RATE = 0.7`（即 **70%**，
定义在 `risk_trigger_extraction/scripts/config.py`）会抛 RuntimeError 阻断，
不会输出全 0 名单。历史文档写过 50%——已收紧为 70%，以代码常量为准。

## 阻断节点 3 — 对外 Word 报告生成之前（Level 3 临界点）

**触发条件：** 用户要求"生成正式报告/Word 报告"且 `--purpose external`。

**阻断原因：** `.docx` 一旦生成并交付，报告与底层数据的一致性承诺即成立；此后修改 CSV 须同步重新出报告，否则存在数据与报告不一致的合规风险。

**必须确认：**
- [ ] 当前的 `*_LLM报告数据.json` 是最终版本（无数据更新计划）？
- [ ] 报告用途（内部传阅 vs 对外交付）？

**放行方式：** `--purpose external` 必须加 `--confirmed-final-version`（internal 用途不需要）。
