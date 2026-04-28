# 征信域 (CRDTC) · 业务上下文

## 业务定位

征信域指标来自人行征信报告. **本轮挖掘中信号最强的维度** (IV 普遍 0.27–0.56).

## 主要基础表

- `DT_SSDP_CORP_CUST_CRDTC_IND_W` —— 对公客户征信信息 (核心: 担保人查询次数 / 总机构数 / 各类未结清明细)
- `DT_SSDP_CORP_CUST_OTHER_CRDTC_IND_W` —— 对公客户其他征信指标 (信贷交易未结清总机构数 / 银行授信机构数 / 非银授信机构数 / 当前逾期机构数 / 借贷余额)

## 命名约定

- `CRDTC_M_<业务键>_<窗口>_<统计>`
- 机构计数类: `CRDTC_M_<X>_ORG_SNAP_CNT`
- 占比类: `CRDTC_M_<X>_RATIO`
- 查询类: `CRDTC_M_QRY_<X>_<W>_CNT`
- 渠道结构: `CRDTC_M_<X>_CHANNEL_<W>_RATIO`
- 逾期类: `CRDTC_M_OVDUE_<X>_<W>_<STAT>`

## 设计模式约定

- `ref_date_logic`: SNAP (征信报告报送时点)
- `null_handling`: `KEEP_NULL` + `SAFE_DIVIDE_ZERO` (机构数=0 时比例算 0 而非 NULL,因为业务上 = "无信贷活动")
- `post_processing_rule`: `KEEP_NULL_ON_LEFT_JOIN` (无征信报告 = 真缺失)

## 风险方向常识

- 总机构数 / 担保人查询次数 / 未结清机构数 / 高风险渠道占比 → 大者风险高 (正向)
- **担保查询机构比 / 未结清机构占比 / 担保查询未结清比** 这类比率类 LR 系数符号与单变量 IV 直觉可能反向 (多元共线性), 在 notes 中标 "LR 方向待验证, 多元共线性"
- 银行授信机构数 → 通常大者风险低 (银行多代表信誉好), 但本批数据呈现"正向", 这是腰部企业的特殊行为, 接受用户输入的 risk_direction
- 当前逾期余额 / 当前逾期机构数 → 强正向

## 注意事项

- 部分原始字段口径需要核实 (如 GUARTOR_CRDTC_QRY_CNT 是累计还是滚动 24 月) — 在 notes 写 "口径需向数源核实是累计还是窗口"
- "授信分散度 = log1p(总机构数)" 与 "总机构数" 是同源 — 不要重复登记, 建议只入 `CRDTC_M_TOTORG_SNAP_CNT`, log 变换在建模时做
