# 文件落地位置

## 各链路导出路径

| 链路 | results 目录 | output 目录 |
|------|-------------|-------------|
| `generic` (通用宽表) | `data/results/<project_name>/` | `output/<project_name>/` |
| `credit` (征信) | `data/results/征信/<project_name>/` | `output/征信/<project_name>/` |
| `gsfc` (工商财务) | `data/results/工商财务/<project_name>/` | `output/工商财务/<project_name>/` |

路径根均为 `<project_root>`（向上找 `data/` 目录的第一个祖先）。

## 文件清单（以 generic 为例）

```
<project_root>/data/results/<project_name>/
    <project_name>_IV分析结果_全量.csv      → r.iv_full
    <project_name>_IV分析结果_分群.csv      → r.iv_group_all
    <project_name>_特征风险相关性.csv       → r.corr_long（重塑）
    <project_name>_逻辑回归系数.csv         → r.lr_coef_long（重塑）
    <project_name>_IV值透视表.csv           → r.iv_pivot（可选）
    <project_name>_IV可信度透视表.csv
    <project_name>_IV可信度诊断.csv         → r.reliability_summary
    <project_name>_综合特征分析结果.csv     → r.comprehensive

<project_root>/output/<project_name>/
    <project_name>_LLM报告数据.json         → r.llm_report
    <project_name>_LLM_分群画像.csv         → r.segment_profiles
```

若用户手动传了 `output_subdir='xxx'`，则末级子目录替换为 `xxx`。

## `load_results` 查找逻辑

自动搜索顺序（`results_base=None` 时）：
1. `data/results/<subdir>` ← generic pipeline（优先）
2. `data/results/征信/<subdir>` ← credit pipeline（向后兼容）
3. `data/results/工商财务/<subdir>` ← gsfc pipeline（向后兼容）

找到第一个存在的目录即停止；全部不存在则抛 `FileNotFoundError`，并列出每个父目录下的候选子目录。

如需强制指定路径，传 `results_base` 参数：
```python
load_results('项目名', results_base='data/results/征信')
```
