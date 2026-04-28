# 工商/经营域 (OPN) · 业务上下文

## 业务定位

OPN 域聚焦工商变更行为模式 (法人变更频率 / 股东变化 / 地址迁移 等). 通常信号中等, 覆盖率高.

## 主要基础表

- `DEMO_CORP_BASIC_INFO` —— 基础信息 (`FOUND_DT`=成立日期 / `IS_TECH_CORP`=是否科技 / 注册资本)
- `DEMO_CORP_REG_CHANGE` —— **【缺口表,数仓待补建】** 工商变更明细
   - 必备字段: CUST_NO, CHG_EVENT, CHG_BEFORE, CHG_AFTER, CHG_DT
   - 推荐字段: CHG_TYPE_STD (18 类标准事项), CHG_AMT_BEFORE, CHG_AMT_AFTER
- `DEMO_CORP_REG_TAG` —— **【缺口表】** 工商标记 (新增/退出类)

## 命名约定

- `OPN_M_<业务键>_<窗口>_<统计>`
- 变更次数: `OPN_M_CHG_<TYPE>_<W>_CNT` (W=LIFE / Y1 / M12 / M3)
- 变更类型计数: `OPN_M_CHG_<TYPE>_CNT`
- 资本类: `OPN_M_CHG_CAP_<X>_<W>_<STAT>` (RATIO / AMT / PCT)
- 法人/股东相关: `OPN_M_CHG_LEGALREP_*` / `OPN_M_CHG_SHARE_*`
- 标记类: `OPN_M_TAG_<DIR>_<W>_CNT`
- 时间锚类: `OPN_M_<X>_DAYS` / `OPN_M_<X>_YEARS`

## 18 类标准事项类别 (动态展开维度的取值)

```
法定代表人/负责人变更, 董监高变更, 股东/投资人变更, 注册资本变更,
经营范围变更, 地址/住所变更, 企业类型变更, 章程变更,
联络员变更, 登记机关变更, 名称变更, 行业代码变更,
期限变更, 清算组备案, 分支机构备案, 企业状态变更,
其他事项备案, 其他
```

## 设计模式约定

- 如果 seed 名形如 `累计_X` / `近N天_X` / `年度_YYYY_X`:
  - 优先**提案动态展开模板** `OPN_M_CHG_LIFE_TYPE_TPL` (`is_dynamic_expansion=1`, `dynamic_template="累计_{事项类别}"`)
  - 不要为每一类事项都单独提案
- `ref_date_logic`: BATCH_MAX (CSV 加工逻辑里"参考日 = 全量批数据最大变更时间")
- `null_handling`: `DROP_KEY_NULL` + `FALLBACK_OTHER` (未匹配事项归"其他")
- `post_processing_rule`: `PAD_ZERO_ON_LEFT_JOIN` (无变更 = 没动 = 0)

## 风险方向常识

- 距离最近变更天数 → 大者风险低 (负向, 越近期变越频繁就越可疑)
- 变更总次数 / 各类变更累计次数 → 大者风险高 (正向)
- 高频变更 (法人/股东/地址) → 强正向, 是经典预警信号
- 是否科技型企业 (FLG) → 上下文依赖, 此项让 LR 决定方向
- 成立年限 → 大者风险低 (负向, 老企业稳定)

## 注意事项

- **大部分 OPN 候选的 priority 应是 P0-阻塞**, 因为基础表 `DEMO_CORP_REG_CHANGE` 当前未建. 在 notes 写 "依赖工商变更明细表, 待数仓补建后落地"
- 财务/股东资本类 (出资比例/增资幅度) 来自 CHG_AFTER 的文本正则提取, 数仓侧应预清洗成 `CHG_AMT_*` 字段, 否则下游每次都要正则
