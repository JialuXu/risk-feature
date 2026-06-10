# UCI Credit Card 验收测试剧本

risk-feature-pipeline 统一 CLI 改造的端到端验证。所有命令可直接复制粘贴到当前目录运行。

## 目录结构

```
uci_acceptance_test/
├── README.md           # 本文件
├── setup.sh            # 一键建 venv + 导出环境变量（首次运行）
├── data/raw/wide.csv   # → 软链到 /Volumes/Xujl/Skill/data/UCI_Credit_Card.csv
├── filter.json         # filter 模板：排除稀疏分群（EDUCATION 0/5/6 + MARRIAGE 0）
└── feats.json          # 自定义 features 模板（trigger 用）
```

数据集：30000 行 × 25 列，目标列 `default.payment.next.month`，默认率 22.12%。

---

## 0. 一次性准备

```bash
cd /Volumes/Xujl/Skill/uci_acceptance_test
source ./setup.sh        # 建 venv（首次需 1-2 分钟）+ 导出 PIPELINE_ROOT / PY
```

如果之后新开 shell 继续测试，重新 `cd` 并 `source ./setup.sh`（venv 已建好就秒过）。

> 后续命令模板：`PYTHONPATH=$PIPELINE_ROOT $PY -m risk_pipeline <子命令>`

---

## 1. prepare（含 filter）

```bash
PYTHONPATH=$PIPELINE_ROOT $PY -m risk_pipeline prepare \
  --wide data/raw/wide.csv \
  --id-col ID \
  --target-col default.payment.next.month \
  --filter-file filter.json \
  --project uci_demo \
  --confirmed-new-dataset
```

**预期**：
- 末尾 `[prepare] OK | project=uci_demo | level=前置`
- `rows=29541, features=23, bad=6604`（22.36%，过滤后略升）
- 生成 `data/processed/uci_demo/{prepared.csv, features.json}`

**验证**：
```bash
ls -la data/processed/uci_demo/
$PY -m json.tool data/processed/uci_demo/features.json | head -20
```

---

## 2. analyze（多维分群）

```bash
PYTHONPATH=$PIPELINE_ROOT $PY -m risk_pipeline analyze \
  --project uci_demo \
  --steps univariate,iv,lr \
  --category-dims SEX,EDUCATION,MARRIAGE \
  --qual-dims ""
```

> `--qual-dims ""` 显式声明无 `是_*` 资质标签维度，否则会自动检测出空集而走默认分支。

**预期**：
- 末尾 `[analyze] OK | level=过渡态`
- `data/processed/uci_demo/_intermediate/` 含：
  - `iv_full.csv`、`iv_group_all.csv`
  - `corr_wide_SEX.csv` / `corr_wide_EDUCATION.csv` / `corr_wide_MARRIAGE.csv`
  - `lr_coef_wide_*.csv` ×3
  - `manifest.json`

**验证**：
```bash
ls data/processed/uci_demo/_intermediate/
$PY -m json.tool data/processed/uci_demo/_intermediate/manifest.json
```

---

## 3. export（→ Level 1）

```bash
PYTHONPATH=$PIPELINE_ROOT $PY -m risk_pipeline export --project uci_demo
```

**预期**：
- 末尾 `[export] OK | level=Level 1`，「9 个文件已落盘」
- `data/results/uci_demo/`：8 张 CSV
- `output/uci_demo/`：`uci_demo_LLM报告数据.json` + `uci_demo_LLM_分群画像.csv`

**验证**：
```bash
ls data/results/uci_demo/
ls output/uci_demo/
```

---

## 4. query（多模式查询）

```bash
# 4a. 全量 IV top 10（PAY_0 应排第一）
PYTHONPATH=$PIPELINE_ROOT $PY -m risk_pipeline query \
  --project uci_demo --kind iv --top 10

# 4b. 分群 IV：女性（SEX=2）的 top 5
PYTHONPATH=$PIPELINE_ROOT $PY -m risk_pipeline query \
  --project uci_demo --kind iv_group --dim SEX --group 2 --top 5

# 4c. 分群相关性：研究生（EDUCATION=1）的 top 5
PYTHONPATH=$PIPELINE_ROOT $PY -m risk_pipeline query \
  --project uci_demo --kind corr --dim EDUCATION --group 1 --top 5

# 4d. 分群 LR 正向系数：已婚（MARRIAGE=1）top 5
PYTHONPATH=$PIPELINE_ROOT $PY -m risk_pipeline query \
  --project uci_demo --kind lr --dim MARRIAGE --group 1 --top 5 --sign positive

# 4e. CSV 格式输出（可重定向）
PYTHONPATH=$PIPELINE_ROOT $PY -m risk_pipeline query \
  --project uci_demo --kind iv --top 10 --output-format csv > iv_top10.csv
head -3 iv_top10.csv
```

**预期**：
- 4a 结果中 `PAY_0` 排第一（最近还款状态对违约预测最强）
- 4b/c/d 各打印 5 行
- 4e：`iv_top10.csv` 可被 `pd.read_csv` 读

---

## 5. trigger（自定义 features）

UCI 没有默认 RISK_FEATURES（工商变更类）需要的中文列，**必须** `--features-file`。

```bash
# 5a. 不带 --confirmed 应被阻断节点 2 拦下
PYTHONPATH=$PIPELINE_ROOT $PY -m risk_pipeline trigger \
  --project uci_demo --features-file feats.json
echo "节点 2 exit code: $?"   # 应该是 1

# 5b. 带 --confirmed 才放行
PYTHONPATH=$PIPELINE_ROOT $PY -m risk_pipeline trigger \
  --project uci_demo --features-file feats.json --confirmed
```

**预期**：
- 5a：打印 `⚠️ [阻断节点 2]`，exit 1
- 5b：`[trigger] OK | level=Level 2`，三张表落盘到 `output/uci_demo/`：
  - `uci_demo_风险触碰明细_宽表.csv`
  - `uci_demo_风险触碰明细_长表.csv`
  - `uci_demo_触碰阈值说明.csv`

**验证**：
```bash
ls output/uci_demo/*风险触碰* output/uci_demo/*触碰阈值*
$PY -c "import pandas as pd; df=pd.read_csv('output/uci_demo/uci_demo_触碰阈值说明.csv'); print(df.to_string(index=False))"
```

---

## 6. 三个阻断节点（额外验证）

```bash
# 6a. 节点 1：用一个未见过的"新"数据集跑 prepare
mkdir -p _block_test/data/raw
ln -sf /Volumes/Xujl/Skill/data/UCI_Credit_Card.csv _block_test/data/raw/another.csv
cd _block_test && PYTHONPATH=$PIPELINE_ROOT $PY -m risk_pipeline prepare \
  --wide data/raw/another.csv --id-col ID \
  --target-col default.payment.next.month \
  --project blk_test
echo "节点 1 exit code: $?"   # 应该是 1
cd ..

# 6b. 节点 3：跑 report --purpose external 不带 --confirmed-final-version
echo "# 测试报告" > r.md
PYTHONPATH=$PIPELINE_ROOT $PY -m risk_pipeline report \
  --project uci_demo --report-markdown r.md --purpose external
echo "节点 3 exit code: $?"   # 应该是 1
```

**预期**：每个都打印对应阻断文案，exit 1。

---

## 7. state.json（项目执行历史）

```bash
$PY -c "
import json
with open('data/results/uci_demo/.pipeline_state.json') as f:
    s = json.load(f)
print(f'project:       {s[\"project_name\"]}')
print(f'current_level: {s[\"current_level\"]}')
print(f'datasets:      {len(s[\"known_datasets\"])}')
print(f'history ({len(s[\"history\"])} 项):')
for h in s['history']:
    print(f'  - {h[\"cmd\"]:8s} → {h[\"level_after\"]:9s} ({h.get(\"duration_sec\",\"?\")}s)')
"
```

**预期**：
- `current_level: Level 2`
- `datasets: 1`（known_datasets 存了 wide.csv 的 sha256 指纹）
- history ≥ 4 项：prepare → analyze → export → trigger

---

## 8. 老入口兼容（deprecation）

```bash
# 8a. python -m shared --help 仍工作 + stderr 警告
PYTHONPATH=$PIPELINE_ROOT $PY -m shared --help 2>&1 | head -3

# 8b. 老 import 路径仍工作 + DeprecationWarning
PYTHONPATH=$PIPELINE_ROOT $PY -W default::DeprecationWarning -c "
from shared.config import COL_TARGET
from shared.pipeline import run_generic_pipeline
print('legacy imports OK')
"
```

**预期**：
- 8a：stderr 第一行有 `[DEPRECATION]`
- 8b：stderr 出现 `DeprecationWarning`，stdout 出现 `legacy imports OK`

---

## 9. 清理（可选）

测完想干净，删掉本地产物（保留 README/setup/filter/feats/data/raw 软链不动）：

```bash
rm -rf data/processed data/results output _block_test r.md iv_top10.csv
```

完整清空（包括 venv）：

```bash
rm -rf /tmp/risk_venv
rm -rf data/processed data/results output _block_test r.md iv_top10.csv
```

---

# 验收 checklist

任何一条没过，把命令 + 完整 stderr 贴出来：

- [ ] **测试 1** prepare：rows=29541, features=23
- [ ] **测试 2** analyze：`_intermediate/` 含 `iv_full.csv` + `corr_wide_*.csv` ×3
- [ ] **测试 3** export：`data/results/uci_demo/` 至少 6 张 CSV
- [ ] **测试 4a** query：PAY_0 在 IV top 3
- [ ] **测试 4d** query 分群 LR：MARRIAGE=1 的正向系数表非空
- [ ] **测试 5a** 阻断 2：未带 --confirmed 时 exit 1
- [ ] **测试 5b** trigger：3 张触碰表落盘
- [ ] **测试 6a** 阻断 1：新数据集未带 --confirmed-new-dataset 时 exit 1
- [ ] **测试 6b** 阻断 3：external 未带 --confirmed-final-version 时 exit 1
- [ ] **测试 7** state.json：current_level=Level 2，history ≥ 4 项
- [ ] **测试 8a** 老入口：stderr 第一行 `[DEPRECATION]`
- [ ] **测试 8b** 老 import：DeprecationWarning + import 成功
