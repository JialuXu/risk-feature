# 列名参考

`load_results()` 返回对象的每个属性对应的精确列名。**写消费代码时以此为准，不要猜。**

## ⚠️ 宽表 vs 长表：必读

**磁盘上的原始 CSV（`_逻辑回归系数.csv` / `_特征风险相关性.csv` / `_IV分析结果_分群.csv`）是宽格式**：
- 行 = 分群，列 = 特征名，值 = 系数/相关系数/IV
- 不存在 `系数` / `相关系数` / `IV值` 这些列

`load_results()` 会自动把宽表 `melt` 为长格式并挂到 `r.lr_coef_long` / `r.corr_long` / `r.iv_group_all`。

**结论：永远用 `load_results()` + `r.xxx` 读结果，不要直接 `pd.read_csv` 原始 CSV 后套用长格式列名。**

> **A4/A5 后产物列名/文件名统一**（旧版本仍兼容读取）：
> - 列：`特征` / `分群维度` / `分群名称`（旧 `特征名称` / `分群值` 在读取时自动 rename）
> - 文件：`_IV分析结果_全量.csv` / `_IV分析结果_分群.csv`（旧 `_IV分析结果.csv` / `_IV值分析.csv` 仍写一份兼容副本）

---

## `r.iv_full` — 全量 IV

| 列 | 类型 | 说明 |
|---|---|---|
| `特征` | str | 特征列名 |
| `IV值` | float | Information Value |
| `IV可信度` | str | 可信 / 参考 / 不可信-样本不足 / 不可信-过拟合嫌疑 |
| `样本数` | int | |
| `坏客户数` | int | |

按 `IV值` 降序已排好。

> **`预测能力` 列不在 `iv_full`**，它只存在于 `r.comprehensive`（`iv_all` 衍生）。不要对 `iv_full` / `top_features(..., kind='iv')` 访问 `'预测能力'`。

## `r.iv_group_all` — 分群 IV（长格式）

| 列 | 说明 |
|---|---|
| `分群维度` | 例如 `企业规模` |
| `分群名称` | 例如 `小型企业`（注意**不是** `分群值`）|
| `特征` | |
| `IV值` | |
| `IV可信度` | |

## `r.corr_long` — 分群相关系数（长格式）

| 列 | 说明 |
|---|---|
| `分群维度`, `分群名称`, `特征` | |
| `相关系数` | 特征与 is_bad 的点二列相关 |
| `\|相关系数\|` | 取绝对值，便于排序 |

## `r.diff_long` — 坏-好样本均值差

> **始终为 `None`**：均值差未独立落盘，`load_results` 不会填充此属性。如需均值差，须从宽表现算：
> ```python
> df.groupby('is_bad')[feat].mean()
> ```

## `r.lr_coef_long` — 分群 LR 系数（长格式）

| 列 | 说明 |
|---|---|
| `分群维度`, `分群名称`, `特征` | |
| `系数` | 标准化后系数（StandardScaler + L2），可直接比较大小 |
| `\|系数\|` | 取绝对值 |

> 正系数 = 特征上升推高风险；负系数 = 特征上升降低风险。

## `r.lr_auc_long` — 分群 AUC（长格式）

| 列 | 说明 |
|---|---|
| `分群维度`, `分群名称` | |
| `AUC` | float |
| `AUC类型` | `5折交叉验证` / `训练集(样本不足)` / `训练集(CV失败)` |
| `样本数`, `坏客户数` | |

## `r.comprehensive` — 综合特征分析

> **注意**：此表列名与 `iv_full` **不同**，禁止直接套用 `iv_full` 的列名。

| 列 | 类型 | 说明 |
|---|---|---|
| `特征` | str | 特征列名（A4 后已统一；旧 CSV 中可能叫 `特征名称`，读取时自动 rename） |
| `iv_all` | float | 全量 IV 值（**不是** `IV值`） |
| `IV可信度` | str | 可信 / 参考 / 不可信-* |
| `预测能力` | str | 强 / 中 / 弱 / 无（iv_all 衍生） |
| `特征类型` | str | 原始 / 衍生（可选） |
| `corr_{维度名}` | float | 各分群维度相关系数均值（如 `corr_企业规模`） |
| `lr_coef_mean` | float | 跨分群 LR 系数均值（可选） |
| `iv_{维度名}` | float | 各分群维度 IV 均值（如 `iv_企业规模`） |

排序：已按 `iv_all` 降序排好。

**正确用法**：
```python
top = r.comprehensive.head(15)
cols = [c for c in ['特征', 'iv_all', 'IV可信度', '预测能力'] if c in top.columns]
print(top[cols].to_string(index=False))
```

## `r.iv_pivot` / `r.reliability_pivot` — 透视宽表（可选）

- 行 = 分群名称，列 = 特征名，值分别为 `IV值` / `IV可信度`
- 用于横向对比，列名动态（等于特征名），**无固定列名**
- 读取前先 `print(r.iv_pivot.columns.tolist()[:10])` 确认

## `r.llm_report` — LLM 报告数据（dict）

从 `*_LLM报告数据.json` 加载；顶层键见 `risk_export_report/references/llm_json_schema.md`（需要写报告时再读）。
