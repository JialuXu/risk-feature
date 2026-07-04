---
name: risk_threshold_explore
description: 候选规则阈值探索：对人工挑选的 (分群维度, 分群名称, 特征) 三元组跑 optbinning 单变量最优切点，结合卡方检验与风险倍数判定是否值得纳入预警/审批清单。产物为候选阈值表 + 分箱明细 + audit 节点。
---

> **何时读我**：只有需要五道门槛定义、optbinning 参数细节时才读本文件；常规阈值探索走 `python -m risk_pipeline explore_thresholds`（见 `references/cli/explore_thresholds.md`）。

## 定位

`risk_rule_mining` 用决策树做**多变量**自动规则发现；本 skill 是其互补的**单变量人工探索**通道：

| | risk_rule_mining | **risk_threshold_explore** |
|---|---|---|
| 输入 | 全特征 + 分群列 | **手工指定 (dim, group, feat) 清单** |
| 方法 | 决策树 max_depth=3 | **optbinning 单变量最优切点** |
| 维度 | 多变量交互 (AND) | **单变量** |
| 显著性 | Lift + CV 稳定性 | **卡方 p + 风险倍数** |
| 用途 | 自动发现规则 | **分析师候选规则评审** |

## 何时使用（触发语）

- "中型企业 担保查询机构比 阈值是多少"
- "我挑了几个指标想看看候选阈值"
- "把这几个 (分群, 特征) 跑一下 optbinning"
- "候选规则阈值探索 / 单变量阈值评审"

## 前置

- 必须先跑到 Level 1（`prepare → analyze → export`），保证 `iv_full` / LR / corr 已落盘。
- 输入 pair list 文件（CSV/JSON），列 `分群维度,分群名称,特征`。
- 已自动从前序结果读取 LR 系数或相关系数作为风险方向；两者都缺时回落到段内分箱跳变方向。

## CLI

```bash
python -m risk_pipeline explore_thresholds \
    --project xxx \
    --pairs-file path/to/pairs.csv \
    [--prepared path/to/prepared.csv] \
    [--results-subdir 征信] \
    [--min-risk-ratio 2.0] [--max-p 0.05] [--min-bad-high 10] \
    [--alert-rate-min 0.01] [--alert-rate-max 0.30] [--min-iv 0.02] \
    [--min-bin-size 0.05]
```

参数说明：
- `--min-iv`：参考 IV 下限。**优先取分群 IV（`iv_group_all`），缺失回落到全样本 IV**。
- `--min-bin-size`：optbinning min_bin_size。zero-inflated count 特征（如非零占比 < 5%）可调到 0.02-0.03，或依赖兜底（见下）。

pairs.csv（UTF-8-sig）：

```csv
分群维度,分群名称,特征
企业规模,中型企业,担保查询机构比
企业规模,中型企业,未结清机构占比
企业规模,中型企业,授信分散度
```

JSON 形式：`[{"分群维度": "...", "分群名称": "...", "特征": "..."}, ...]`

## 状态机

- `state.require_level('Level 1')` — 不满足报错并提示先跑 export。
- **不推进 level**（与 `query` / `visualize` 一致）。

## 输出

### `{project}_候选阈值表.csv`（每行 = 评估成功的一个 pair）

| 列 | 说明 |
|---|---|
| 分群维度 / 分群名称 / 特征 | 主键三元组 |
| 风险方向 | `positive` / `negative` |
| 方向来源 | `lr` / `corr` / `bin_jump` |
| 段总样本数 / 段坏客户数 / 段坏率 | segment 描述 |
| 候选阈值 | optbinning 在 splits 内按"已锁定方向风险倍数最大"挑出的切点 |
| 切点来源 | `optbinning`（正常路径）/ `zero_inflate_fallback`（兜底路径，见下文 zero-inflated） |
| 高风险侧 / 低风险侧 样本数·坏客户数·坏率 | 评估字段 |
| 风险倍数 | 高/低风险侧坏率比；低风险侧坏率为 0 时截断到 999 |
| 卡方p值 / 显著性 | `*** / ** / * / ns` |
| 触警率 | 高风险侧样本数 / 段总样本数 |
| 全局IV | 参考 IV 值。**优先取分群 IV**（来自 `iv_group_all`），缺失回落到全样本 IV（`iv_full`） |
| IV来源 | `group` / `full` / `missing`，对应上一列 IV 的真实出处 |
| 规则有效 | 五道门槛 AND 通过 |
| 不通过原因 | 最先失败的门槛名；**通过时为 `-` 哨兵**（避免 CSV 重读时空字符串被解析成 NaN） |
| 规则文本 | 中文业务语言（如 `资产负债率 大于 0.75 时坏率 0.21，是低风险侧 2.8 倍`） |

### `{project}_候选阈值_分箱明细.csv`（长表）

每个 pair 的 optbinning `binning_table` 数据行（去掉 Special / Missing / Totals），列名已汉化：
`分群维度 / 分群名称 / 特征 / 分箱 / 样本数 / 占比 / 好客户数 / 坏客户数 / 坏率 / WoE / IV分量 / 是否候选阈值边界`。

zero-inflated 兜底切点对应的分箱明细是手工构造的 2 行（`(-inf, mode]` 与 `(mode, inf)`），口径与 optbinning 一致。

### `_audit.json` 追加节点 `threshold_candidates`

```json
"threshold_candidates": {
  "created_at": "...",
  "n_pairs_input": 12, "n_pairs_evaluated": 10, "n_pairs_skipped": 2, "n_rules_valid": 6,
  "gates": {"min_risk_ratio": 2.0, ...},
  "skipped": [{"分群维度": "...", "分群名称": "...", "特征": "...", "原因": "..."}],
  "candidates": [{"分群维度": "...", ..., "规则有效": true}]
}
```

agent 报回前 `cat` 这个节点即可。

## 规则有效门槛（五道 AND，默认值见 `scripts/config.py`）

| 门槛 | 默认 | CLI 覆盖 |
|---|---|---|
| 风险倍数 ≥ | 2.0 | `--min-risk-ratio` |
| 卡方 p ≤ | 0.05 | `--max-p` |
| 高风险侧坏客户数 ≥ | 10 | `--min-bad-high` |
| 触警率 ∈ | [1%, 30%] | `--alert-rate-min` / `--alert-rate-max` |
| 参考 IV ≥ | 0.02（IV_THRESHOLD['weak']） | `--min-iv` |

## Zero-inflated count 特征兜底（NOTE-2）

当 `optbinning` 因「非零占比 < `min_bin_size`（默认 5%）」无法产出 splits 时（典型场景：某计数特征 95% 都是 0），skill 自动启用**zero-inflated 兜底**：

1. 检查特征是否有「某常值占比 ≥ 80%」（阈值 `ZERO_INFLATE_RATIO_THRESHOLD`，可改 config）。
2. 命中时，用 `> 常值`（通常即 `> 0`）作为手工切点。
3. 风险方向**只走 LR 系数 / 相关系数**（没有 binning_table，bin_jump 不适用）；两者都缺则 skip。
4. 走完整的五道门槛判定（不偷工减料）。
5. 候选表 `切点来源` 列标 `zero_inflate_fallback`，便于分析师人工复核。

如需绕过兜底直接调 optbinning，传 `--min-bin-size 0.02` 把准入降到 2%。

## 可视化

跑 `python -m risk_pipeline visualize --project xxx --kinds thresholds` 出图：

- `threshold_binning_<dim>_<group>_<feat>.png` — 分箱坏率柱图 + 候选阈值竖线
- `threshold_summary_<dim>.png` — 分群内候选规则风险倍数对比

## 底层实现（仅 notebook）

> `explore_thresholds` / `read_pair_list` 仅 notebook 直接 import；agent 走上面的 `explore_thresholds` CLI。

## 边界处理

| 场景 | 行为 |
|---|---|
| segment 样本 < 50 | skip：`段样本不足` |
| segment 坏客户 < 10 | skip：`段坏客户不足` |
| 特征列全 NaN / nunique ≤ 1 | skip：`特征无变异` |
| optbinning 异常/未收敛/splits 空 | 先试 zero-inflated 兜底；都不行 → skip：`optbinning未收敛` 或 `无有效分箱` |
| zero-inflated 但 LR/corr 方向都缺 | skip：`zero_inflated但无方向` |
| segment 内单类别 target | skip：`段内单类别目标` |
| LR/corr/bin_jump 都缺（主路径） | skip：`方向无法推断` |
| 低风险侧坏率 = 0 | 风险倍数 = 999，仍走门槛 |
| 分群 IV 与全样本 IV 都查不到 | 参考IV=NaN，门槛 `MIN_IV` 失败 → `不通过原因='IV缺失'` |

## 不做

- 已有规则对比（候选 vs 现有规则交叉）—— 留待后续 skill。
- 多变量 AND 规则 —— 属 `risk_rule_mining`。
- 重跑 IV / LR / 相关 —— 严格只读 Level-1 产物。
- Level 2/3 推进。
