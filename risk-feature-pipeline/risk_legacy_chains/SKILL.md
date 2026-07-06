---
name: risk_legacy_chains
description: 征信(credit) + 工商财务(gsfc) 两条黑盒链路的编排层。数据路径、预置维度、特征配置全部走 config/ 默认，一条命令跑通 data_prep→特征工程→单变量/IV/LR→导出。当用户说"跑征信链路/征信风险分析"、"工商财务风险特征分析/gsfc 链路"、"跑一下 credit / gsfc 那条常用路径"时触发。**与 generic 链路刻意分离，不接受 --wide 等任意宽表参数，不可拆入 generic。**
---

> **何时读我**：只有需要理解 credit/gsfc 两条黑盒链路的定位、默认步骤、与 generic 的边界时才读本文件；常规执行直接走 `python -m risk_pipeline run --pipeline credit|gsfc`（CLI 细节见 `references/cli/run.md`）。
> **本 skill 是独立编排层，刻意不挂进顶层 `SKILL.md` 的主路径路由**——它服务的是"某些用户的固定常用路径"，不是通用入口。

## 定位

credit / gsfc 是两条**预打包的主题链路**：数据源路径、分群维度、特征清单都在 `config/` 里写死，用户不用准备宽表、不用点特征，一条命令即出结果。它们是**黑盒**——算法与产物 schema 与 generic 共享内核，但编排流程独立、不可中段拆调、不并入 generic（见 `[[credit-gsfc-blackbox-decision]]` 决策）。

| | **credit（征信）** | **gsfc（工商财务）** | generic（通用） |
|---|---|---|---|
| 数据来源 | `config/` 默认路径 | `config/` 默认路径 | 用户传 `--wide` + `--bad-customer` |
| 分群维度 | 预置（如企业规模） | 预置（如客户性质） | `--category-dims` 自选 |
| 特征清单 | `CREDIT_CONFIG` 写死 | `DATA_CONFIG` 写死 | 从宽表自动摸底 |
| 默认 steps | `data_prep,feature_engineering,univariate,lr,iv,export` | `data_prep,feature_eng,univariate,iv,lr,export` | `univariate,iv,lr,rules` |
| 结果前缀 | `data/results/征信/` | `data/results/工商财务/` | `data/results/<project>/` |

> 注：credit 用 `feature_engineering`、gsfc 用 `feature_eng`（历史命名差异，逐字保留）。

## 何时使用（触发语）

- "跑一下征信链路 / 征信风险特征分析"
- "工商财务风险分析 / gsfc 链路跑通"
- "跑我们常用的 credit / gsfc 那条路径"
- "只跑征信的 data_prep 和 IV"（→ `--steps data_prep,iv`）

数据是**任意宽表**、要自选维度/特征 → 不走本链路，走 generic（顶层 `SKILL.md` → `run --pipeline generic`）。

## CLI（agent 默认走这里）

```bash
# 全流程（数据路径走 config/ 默认，不传 --wide）
python -m risk_pipeline run --pipeline credit
python -m risk_pipeline run --pipeline gsfc

# 只跑部分步骤
python -m risk_pipeline run --pipeline gsfc --steps data_prep,iv
python -m risk_pipeline run --pipeline credit --quiet
```

CLI 全参数、filter/exclude JSON、雷区见 `references/cli/run.md`；阻断节点（首次数据集确认等）见 `references/blocking-gates.md`；Level 状态机见 `references/levels.md`；沙盒路径变量见 `references/paths-env.md`。

## Level 1 之后（与 generic 完全一致）

导出完成即达 Level 1，后续读结果 / 出图 / 阈值探索 / 触碰扫描都复用通用子 skill：

```bash
python -m risk_pipeline query   --project <征信/工商财务项目名> --kind iv --top 15
python -m risk_pipeline visualize --project <征信/工商财务项目名>
```

## Python API（仅 notebook；agent 走 CLI）

```python
from risk_legacy_chains.scripts import run_credit_pipeline, run_gsfc_pipeline
r = run_credit_pipeline(steps=['data_prep', 'iv'], verbose=False)   # 默认全步骤
```

**保号**：旧路径 `from risk_pipeline.pipeline import run_credit_pipeline` / `run_gsfc_pipeline` 仍等价可用（逐字 re-export，不变）。

## 老入口（将退休）

`python -m shared --pipeline credit|gsfc` 仍可用，但会打印 deprecation 警告，下个版本移除——新脚本用 `python -m risk_pipeline run --pipeline ...`。

## 雷区 / 不做

- **不可中段独立调用**：`run --pipeline credit/gsfc` 是 state.json 里的黑盒一项，不接受 `--wide` 等 generic 参数；`--steps` 不含 `export` 时不推进 Level 1。
- `--category-dims` / `--qual-dims` 对 credit/gsfc **无效**（用预置维度，传了告警忽略）。
- **不并入 generic、不加特殊化**：黑盒故意与通用链路分离（决策见 `docs/DECOUPLING-DESIGN.md §10`）。
- 不改算法、不改对外 CSV/JSON schema——两条链路从 `risk_pipeline/pipeline.py` 逐字迁出，数值由 `tests/test_golden_legacy_chains.py` 钉死。
