---
name: risk_trigger_extraction
description: 逆向提取风险特征触碰客户清单：基于已筛选的有效风险特征（IV可信、中等以上预测能力），从宽表判断每个客户是否触碰风险阈值；产出客户触碰宽表/长表/阈值说明表，并给出 IV 加权风险得分排名。注意：默认特征配置仅适用 GSFC（工商财务）主题，征信/舆情/generic 等其他主题必须传项目专属 features 配置（--features-file）
---

> **何时读我**：只有需要 features 配置结构、阈值计算/IV 加权得分细节时才读本文件；常规触碰提取走 `python -m risk_pipeline trigger`（见 `references/cli/trigger.md`，先过阻断节点 2）。

> **这是 Level 2 操作（把风险结论落到每个客户），agent 必须走 CLI：**
> `python -m risk_pipeline trigger --project X --use-default-features --confirmed`
> ⚠️ **必须带 `--confirmed`（阻断节点 2，见 `AGENTS.md` 五）**——预警名单推送给业务后不可撤回。

## 触发 → CLI

| 用户说 | 跑 |
|---|---|
| "风险预警名单 / 哪些客户触碰阈值 / 客户级扫描"（GSFC 主题） | `python -m risk_pipeline trigger --project X --use-default-features --confirmed` |
| 非 GSFC 主题（征信/舆情/generic）或有专属特征 | `python -m risk_pipeline trigger --project X --features-file project_features.json --confirmed` |
| 要保留 `企业规模`/`内部评级` 等业务列 | 加 `--keep-metadata-cols 企业规模,内部评级` |

> ⚠️ **默认特征 `RISK_FEATURES_GSFC`（37 个）仅适配 GSFC 主题宽表。** 其它主题用默认特征时，若宽表匹配率 **< 70%**，`extract_triggers` 抛 `RuntimeError` 阻断，避免输出全 0/语义错误的名单。专属特征请走 `--features-file`，并在阻断节点确认每个特征的 `risk_direction` 和 `iv`。

## 产出三件套

1. `{project}_风险触碰明细_宽表.csv` — 每行一客户：各特征值、触碰标记(0/1)、触碰特征总数、IV加权风险得分、触碰特征清单
2. `{project}_风险触碰明细_长表.csv` — 仅触碰的 客户×特征 记录，含阈值、来源、类别
3. `{project}_触碰阈值说明.csv` — 每特征的触碰条件、好/坏均值、阈值来源

**输出位置**：默认落 `<project_root>/output/<project>/`，与 Level 1 的 `data/results/<project>/` 是**两个不同根**。CLI status stamp 打印绝对路径；找不到时用 `find <project_root>/output -name '*风险触碰*'`。

## 阈值策略（优先级从高到低）

1. **显式阈值**（`explicit_threshold`）：报告中业务专家给定，直接用
2. **坏客户均值**：客户表现至少和坏客户平均一样差才算触碰（保守、有风控意义）
3. **兜底**：好/坏样本不足时用范围内中位数，附注来源

- 阈值只在特征的 `scope` 适用范围内计算（分群规则用分群内的好/坏客户）。
- 阈值用被扫描客户自身的标签算出（**样本内**），摘要中的坏客户触碰率偏乐观。
- 坏/好客户均值方向与 `risk_direction` 相反时，阈值说明表 `方向校验` 列标 `⚠ 不一致`，并在 stderr 告警——多为方向配错，会大量误报好客户。
- `scope` 引用的维度列在宽表中不存在时，该特征**跳过**（触碰列为空、阈值说明表标 `(已跳过)`）。

## IV 加权风险得分

`得分 = Σ(触碰_i × IV_i) / Σ(IV_i) × 100`（0–100，越高风险越大，按降序排）。高 IV 特征触碰贡献更大权重。

## scope 维度筛选（每个特征的触发范围）

| scope 形态 | 含义 |
|---|---|
| `'full'`（默认）| 全量客户 |
| `'waist'` | 仅腰部企业（等价 `{"dim":"是否腰部企业","value":1}`，加权用 `iv_waist`）|
| `{"dim":"X","value":"Y"}` | 单值维度筛选 |
| `{"dim":"X","values":["Y1","Y2"]}` | 多值维度筛选 |

`dim` 不在宽表列中时该特征跳过（触碰列为空，阈值说明表 `阈值来源` 写明跳过原因），其余特征照常扫描。

## keep_metadata_cols（默认不含业务列）

宽表 CSV **默认不含** `is_bad`/`企业规模`/`所属行业` 等列，避免与 `prepared.csv` merge 撞列。需要时：
- CLI `--keep-metadata-cols 企业规模,内部评级`（任意原始列都可指定）
- 或默认行为下 `pd.merge(prepared, df_wide, on='客户编号', how='left')` 自取

## `--features-file` 配置（非 GSFC 主题必备）

JSON 数组，每条特征至少含 `report_name` / `source_col` / `risk_direction`（`positive`|`negative`）/ `iv` / `category` / `scope`：

```json
[{"report_name":"资产负债率","source_col":"资产负债率","risk_direction":"positive","iv":0.35,"category":"偿债能力","scope":"full"}]
```

> 底层 `extract_triggers` 与默认常量 `RISK_FEATURES_GSFC` 仅 notebook 直接 import；agent 走上面的 `trigger` CLI。

## 职责边界

| 负责 | 不负责 |
|------|--------|
| 阈值计算（显式/数据驱动）、客户级触碰评估、IV 加权得分、三张 CSV 落盘 | 特征工程、IV/LR 分析、八文件标准导出、DOCX 报告 |
