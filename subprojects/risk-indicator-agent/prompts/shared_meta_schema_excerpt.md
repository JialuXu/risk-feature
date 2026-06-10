# 元表 DIM_DERIV_IND_REG · Schema 摘要 (LLM 必须遵守)

## 必填字段

| 字段 | 类型 | 约束 |
|---|---|---|
| `ind_code` | string | 正则 `^(FIN\|CRDTC\|OPN\|PUB\|JUDI\|LON\|GUAR\|RELA\|FUND)_[MDA]_[A-Z0-9_]+$` ; 长度 ≤60 |
| `ind_version` | int | 默认 1 |
| `ind_name_cn` | string | 中文名 2~200 字符 |
| `domain` | enum | FIN / CRDTC / OPN / PUB / JUDI / LON / GUAR / RELA / FUND |
| `granularity` | enum | M (月度客户快照) / D / A / EVT |
| `window` | enum | SNAP / M3 / M6 / M12 / Y1 / Y3 / Y5 / LIFE / EVT |
| `value_type` | enum | NUM / RATIO / FLG / IDX / STR / DATE |
| `biz_definition` | string | 业务口径,中文一句话 |
| `calc_logic` | string | 伪表达式 (**不是可执行 SQL**); 含空值/异常处理说明 |
| `source_tables` | array<string> | 依赖基础表英文名 (从「表清单.csv」选, 不要编造) |
| `source_fields` | array<string> | 依赖字段, 格式 `表英文名.字段英文名(中文名)` |
| `priority` | enum | P0 / P0-阻塞 / P1 / P1-稀疏池 / P2 / P3-观察 / P4-观察 |
| `lifecycle_status` | enum | DRAFT (新提案) / ACTIVE / DEPRECATED / RETIRED |
| `proposer` | enum | LLM_AGENT (LLM 提的) / HUMAN / MIGRATION |
| `owner` | string | 业务团队, 默认填 `RISK_TEAM` |
| `eff_dt` | date | 默认填今天 |
| `exp_dt` | date | 默认填 `9999-12-31` |
| `is_dynamic_expansion` | int | 0=具体实例 / 1=动态展开模板 |
| `ref_date_logic` | enum | BATCH_MAX (默认,本批最大日) / SYS_TODAY / EXPLICIT_PARAM / SNAP_DT / NONE |
| `post_processing_rule` | enum | PAD_ZERO_ON_LEFT_JOIN (OPN/PUB 默认) / KEEP_NULL_ON_LEFT_JOIN (FIN/CRDTC 默认) / NONE |

## 选填字段

- `ind_name_en`, `value_unit`, `notes` (≤2000 字)
- `dynamic_template`, `dynamic_axes`, `parent_template_code` — 仅动态展开类指标用
- `null_handling` — 数组,可叠加: `DROP_KEY_NULL` / `FILL_ZERO` / `KEEP_NULL` / `SAFE_DIVIDE_ZERO` / `SAFE_DIVIDE_NULL` / `FALLBACK_OTHER` / `INT_PARSE_ZERO` / `POST_LEFT_JOIN_FILL_ZERO`
- `current_iv`, `current_coverage_rate`, `current_signal_strength`, `current_risk_direction`, `iv_history` — 由 IV 验证回填,提案阶段填实测值

## 命名规范 (ind_code)

格式: `{域}_{粒度}_{业务键}_{窗口}_{统计}`

例:
- `CRDTC_M_GUARQRY_UNPAYOFF_SNAP_RATIO` (征信-月度-担保查询未结清-快照-比率)
- `OPN_M_CHG_LIFE_LEGALREP_CNT` (工商-月度-法人变更-生命周期-计数)
- `PUB_M_TAG_OVDUE_M12_CNT` (舆情-月度-逾期标签-近12月-计数)
- `FIN_M_CGB_CRDT_USAGE_SNAP_RATIO` (财务-月度-本行授信使用-快照-比率)

**反例 (禁止)**:
- ❌ `feature_001` (无语义)
- ❌ `担保查询未结清比` (中文)
- ❌ `crdtc_m_xxx` (小写)
- ❌ `CRDTC_GUARQRY` (缺粒度/窗口/统计)
