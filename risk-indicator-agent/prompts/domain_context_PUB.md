# 舆情域 (PUB) · 业务上下文

## 业务定位

PUB 域来自外部舆情爬取 (新闻/裁判文书/经营异常公示等). 本轮挖掘 IV 弱 (0.01-0.06) 但稳定. 信号弱不代表无价值 — 是规则系统的"触发器"而非主评分入参.

## 主要基础表

- `DT_SSDP_CORP_CUST_PUB_OPINION_A` —— **底表已就绪,无缺口**
   - `CUST_NO` 客户编号
   - `IS_MAIN` 是否主体企业 ("否" → 传导舆情; 其他 → 自身舆情)
   - `TAG_NAME` 风险标签 (信贷逾期 / 列入被执行人 / 资产被查封冻结 / 破产清算 等)
   - `SIGNAL_LEVEL` 舆情信号等级 (整数)
   - `PUB_TIME` 发布时间
   - `RELA_WEIGHT` 穿透关联权重

## 命名约定

- `PUB_M_<业务键>_<窗口>_<统计>`
- 标签计数类 (动态展开): `PUB_M_TAG_<LABEL>_<W>_CNT` 模板
- 标签 FLG 类: `PUB_M_TAG_<LABEL>_<W>_FLG`
- 自身/传导拆分: `PUB_M_OPN_SELF_<W>_CNT` / `PUB_M_OPN_PROPAG_<W>_CNT`
- 信号等级类: `PUB_M_SIG_<X>_<STAT>` (MAX / AVG / HIGH_CNT / HIGH_RATIO)
- 时间锚类: `PUB_M_OPN_RECENT_DAYS` / `PUB_M_OPN_TIMESPAN_DAYS`
- 占比类: `PUB_M_OPN_<X>_RATIO`

## 设计模式约定

- 如果 seed 名形如 `风险标签_X_数量` / `自身舆情_X_数量` / `舆情信号等级X_数量`:
  - 优先**提案动态展开模板** (如 `PUB_M_TAG_LABEL_M12_CNT_TPL`, `dynamic_template="风险标签_{标签}_数量"`)
  - 不要枚举所有标签
- `ref_date_logic`: BATCH_MAX (CSV 加工: "参考日 = 全量批数据最大发布时间")
- `null_handling`: `DROP_KEY_NULL` + `FALLBACK_OTHER` (TAG_NAME 空值置"未标注")
- `post_processing_rule`: `PAD_ZERO_ON_LEFT_JOIN` (无舆情 = 没风险信号 = 0)

## 风险方向常识

- 全部舆情类指标几乎都是 **正向** (有舆情/标签更多/高等级更多 → 风险更高)
- 例外: 自身舆情占比 vs 传导舆情占比 — 业务含义不同, 让 LR 决定

## 窗口选择

- 默认 M12 (近 12 月) 或 LIFE (生命周期累计)
- 高频指标可考虑 M3 (近 90 天)
- "信贷逾期"类标签建议 M12 + LIFE 两个版本同时入元表

## 注意事项

- 大部分 OPN 域 IV 弱 (0.01–0.06) → priority 多为 P3-观察 / P2
- 但少数标签 IV 较强 (如"信贷逾期" 0.06) → 可入 P1
- 风险方向 LR 系数与单变量 IV 在该域应基本一致, 若严重不一致需在 notes 标注"待人工核实"
