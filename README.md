# 企业征信风险特征分析流水线

## 一、项目概述

本工具链是一套模块化的风险特征挖掘流水线，用于对公贷后场景下的风险特征分析。核心功能包括：

- **多源数据合并**：将多表数据合并为宽表
- **标准数据预处理**：统一打坏客户标签、过滤口径、选特征列（`prepare_df`）
- **特征工程**：生成比值类衍生特征，消除规模影响
- **分群分析**：按行业、企业性质、分行等维度分群统计
- **IV诊断**：计算信息价值（IV），评估特征预测能力
- **逻辑回归**：分群建模，输出系数与AUC
- **规则挖掘（可选）**：决策树多变量交互规则，用于预警/审批/贷后触发
- **结果导出**：生成标准化CSV与LLM友好JSON
- **风险触碰**：把风险结论落到每个客户，产出触碰宽表/长表/阈值说明表（`risk_trigger_extraction`）
- **结果查询**：不重跑管线，直接从磁盘读已导出结果（`risk_result_query`）
- **正式报告**：从 LLM JSON 生成 `.docx` 交付件（`risk_docx_report`）

## 二、架构设计

### 整体流程

```
┌─────────────────────────────────────────────────────────────────┐
│                         数据输入层                               │
│  data/raw/    data/processed/    (CSV文件)                       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Step 1: risk_data_prep（数据准备）                              │
│  ├─ 多表合并 → 宽表                                              │
│  ├─ 金额清洗、千分位处理                                          │
│  ├─ 目标列打标（is_bad）                                         │
│  └─ 样本摸底、分群维度检测                                        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Step 2: risk_feature_engineering（特征工程）                    │
│  ├─ 比值特征生成（资产周转率、负债率等）                          │
│  ├─ 安全除法（避免除零错误）                                      │
│  └─ Winsorization 缩尾处理                                       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
        ┌────────────────────┼────────────────────┐
        ↓                    ↓                    ↓
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ Step 3       │    │ Step 4       │    │ Step 5       │
│ 单变量分析    │    │ IV诊断       │    │ 逻辑回归     │
│ ├─相关系数    │    │ ├─自适应分箱 │    │ ├─标准化     │
│ ├─T检验      │    │ ├─WOE截断    │    │ ├─L2正则     │
│ └─分群摸底    │    │ └─可信度评级 │    │ └─交叉验证   │
└──────────────┘    └──────────────┘    └──────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Step 5.5（可选）: risk_rule_mining（决策树规则挖掘）            │
│  ├─ 多变量交互规则提取                                            │
│  ├─ 覆盖率 / 坏账率 / Lift                                        │
│  └─ 稳定性评估（K-fold）                                          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Step 6: risk_export_report（结果导出）                          │
│  ├─ 8个标准CSV文件                                               │
│  ├─ IV可信度透视表                                               │
│  └─ LLM友好JSON（供大模型解读）                                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                      data/results/ → output/                     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
        ┌──────────────────────┬──────────────────────┐
        ↓                      ↓                      ↓
┌────────────────────┐ ┌────────────────────┐ ┌────────────────────┐
│ risk_result_query  │ │ risk_trigger_      │ │ risk_docx_report   │
│ 只读已导出 CSV，   │ │ extraction         │ │ LLM JSON → 正式    │
│ 不重跑             │ │ 客户级触碰明细     │ │ Word 报告          │
│ load_results /     │ │ IV 加权风险得分    │ │ build_prompt_      │
│ top_features       │ │ 宽表/长表/阈值表   │ │ bundle /            │
│                    │ │                    │ │ build_docx_report  │
│ → Level 1 后查询   │ │ → Level 2          │ │ → Level 3          │
└────────────────────┘ └────────────────────┘ └────────────────────┘
```

### 目录结构

```
risk-feature-pipeline/
├── SKILL.md                   # 【顶层调度器】选管线 (credit/gsfc/generic) + 选深度
├── AGENTS.md                  # 本目录下 agent 的硬规矩（先查再跑、prepare_df、verbose=False）
├── report-prompt.md           # DOCX 报告写作模板（供 risk_docx_report 使用）
│
├── shared/                    # 【核心】共享模块（唯一配置源 + 统一入口）
│   ├── __init__.py
│   ├── __main__.py            # CLI入口（python -m shared）
│   ├── config.py              # 配置接口（从 YAML 加载）
│   ├── config_loader.py       # YAML 加载器（深度合并）
│   ├── column_mapper.py       # 字段映射器 ColumnMapper
│   └── pipeline.py            # 【统一入口】run_credit_pipeline / run_gsfc_pipeline / run_generic_pipeline
│
├── config/                    # 【配置中心】YAML 配置目录
│   ├── default.yaml           # 默认配置（路径、阈值、IV 参数）
│   └── column_mapping.yaml    # 字段映射模板
│
├── risk_data_prep/            # Step 1: 数据准备
│   ├── SKILL.md
│   └── scripts/
│       ├── prepare_df.py      # ⭐ 标准 "宽表 + 坏客户 → (df, feature_cols)" 一行合成
│       ├── config.py
│       ├── data_prep.py       # prepare_credit_wide_table()
│       ├── wide_table_builder.py
│       └── io_utils.py
│
├── risk_feature_engineering/  # Step 2: 特征工程
│   ├── SKILL.md
│   └── scripts/
│       ├── financial_feature_engineering.py
│       ├── credit_feature_engineering.py
│       └── change_feature_engineering.py    # 工商变更类衍生特征
│
├── risk_segment_univariate/   # Step 3: 分群单变量
│   └── scripts/
│       ├── segment_univariate.py            # univariate_by_group()
│       └── univariate.py
│
├── risk_iv_diagnosis/         # Step 4: IV 诊断
│   └── scripts/
│       ├── iv_group_diagnosis.py            # iv_by_group(), reliability_diagnosis()
│       └── iv_analysis.py                   # run_iv_analysis()
│
├── risk_logistic_regression/  # Step 5: 逻辑回归
│   └── scripts/
│       ├── group_logistic_regression.py     # lr_by_group(), compare_feature_sets()
│       └── base_modeling.py
│
├── risk_rule_mining/          # Step 5.5（可选）: 决策树规则挖掘
│   ├── SKILL.md
│   └── scripts/
│       ├── rule_extraction.py               # mine_rules()
│       ├── rule_evaluation.py               # evaluate_rules()
│       ├── rule_stability.py                # assess_rule_stability()
│       └── rule_mining_pipeline.py          # rules_by_group(), export_rules()
│
├── risk_export_report/        # Step 6: 结果导出
│   └── scripts/
│       ├── report_analysis.py               # export_results(), build_llm_report_data()
│       ├── report_export.py
│       └── report_insights.py
│
├── risk_trigger_extraction/   # 【客户级落地】把风险结论落到每个客户
│   ├── SKILL.md
│   └── scripts/
│       ├── trigger_extraction.py            # extract_triggers()
│       └── config.py                         # RISK_FEATURES 默认特征配置
│
├── risk_result_query/         # 【查询型】读已导出结果，不重跑管线
│   ├── SKILL.md
│   ├── references/            # 按需加载的参考（列名、查询配方、文件布局）
│   │   ├── columns.md
│   │   ├── query_recipes.md
│   │   └── file_layout.md
│   └── scripts/
│       └── results_loader.py                # load_results(), top_features()
│
└── risk_docx_report/          # 【交付型】LLM JSON → 正式 Word 报告
    ├── SKILL.md
    ├── package.json
    └── scripts/
        ├── build_prompt_bundle.py           # 打包 report-prompt.md + LLM JSON
        ├── build_docx_report.py             # Markdown 正文 → .docx
        └── render_docx_report.js            # Node 渲染器
```

> 注：所有子模块目录均使用下划线命名，`import` 路径与目录名一致（如 `from risk_data_prep.scripts.prepare_df import prepare_df`）。

### 设计原则

| 原则         | 说明                                                            |
| ---------- | ------------------------------------------------------------- |
| **配置集中化**  | 所有数值阈值、路径、参数集中在 `config/default.yaml`                         |
| **字段映射分离** | 不同银行字段名差异通过 `column_mapping.yaml` 处理                          |
| **模块松耦合**  | 各 Skill 的 `scripts/config.py` 仅 `from shared.config import *` |
| **深度合并**   | 用户配置只需覆盖差异项，其余自动回退默认值                                         |
| **统一入口**   | `shared.pipeline.py` 提供一键执行，自动处理模块切换                          |
| **渐进式披露**  | SKILL.md 只给最小调用面；列名表、查询配方等参考文档按需 Read |
| **查询与执行分离** | `risk_result_query` 负责"读已有结果"，与执行管线的子 Skill 解耦 |

### 面向 Agent 的运行规范

在 `risk-feature-pipeline/` 下运行的 Claude Code / Agent 必须遵循 `risk-feature-pipeline/AGENTS.md`：

1. **先查再跑** — 用户说"查/读/解读/top X"时默认走 `risk_result_query`，不重跑管线
2. **用 `prepare_df`** — 不要手抄"读宽表 + 合并坏客户 + 选特征列"三段式
3. **单脚本 + `verbose=False` + `head(N)`** — Bash 之间不保留 Python 状态；大结果禁止整表打印

决策树、标准脚本模板、禁止清单、失败上报格式详见 `AGENTS.md`。

***

## 三、环境依赖

### Python 版本

- Python 3.10+（仓库中使用了 `Optional[list[str]]` 等 PEP 604 / PEP 585 语法）

### 核心依赖

```bash
pip install pandas numpy scipy scikit-learn pyyaml
```

完整依赖列表：

| 包名           | 版本建议  | 用途       |
| ------------ | ----- | -------- |
| pandas       | ≥1.3  | 数据处理     |
| numpy        | ≥1.20 | 数值计算     |
| scipy        | ≥1.7  | 统计检验     |
| scikit-learn | ≥1.0  | 逻辑回归、标准化 |
| pyyaml       | ≥5.4  | 配置加载     |

***

## 四、配置系统详解

### 配置加载流程

```
用户配置（可选）          默认配置
config/my_bank.yaml  →  config/default.yaml
        ↓                    ↓
        └── 深度合并 ─────────┘
                  ↓
           config_loader.py
                  ↓
           shared/config.py
                  ↓
    各模块 scripts/config.py（from shared.config import *）
```

### default.yaml 关键配置项

```yaml
# 数据路径
data:
  raw:
    customer_info: "data/raw/客户信息.csv"
    credit_report: "data/raw/征信数据.csv"
    bad_labels: "data/raw/坏客户标记.csv"
  processed:
    financial: "data/processed/财务数据_处理后.csv"

# 样本量阈值（统计检验门槛）
thresholds:
  min_samples: 50            # 分群总样本数下限
  min_bad_samples: 10        # IV计算坏客户数下限
  min_bad_lr: 20             # 逻辑回归坏客户数下限
  min_samples_cv: 200        # 交叉验证AUC总样本下限

# IV 配置
iv:
  suspect_threshold: 2.0     # IV > 2.0 视为过拟合嫌疑
  woe_cap: 5.0               # WOE 截断范围 [-5, +5]
  select_threshold: 0.1      # IV筛选阈值（中等预测性）

# 分群维度
segment_dims:
  industry: "所属行业"
  nature: "客户性质"
  branch: "所属分行"
```

### column\_mapping.yaml 关键配置项

```yaml
# 必填字段映射
required:
  customer_id: "客户编号"    # 其他银行可能叫 "CUST_NO"
  target: "is_bad"           # 其他银行可能叫 "是否违约"

# 分群维度映射
segment_dims:
  industry: "所属行业"
  branch: "所属分行"

# 资质标签前缀
qualification:
  prefix: "是_"              # 用于识别 "是_高新技术企业" 等

# 金额字段（需清洗千分位）
amount_cols:
  - "授信总金额"
  - "表内授信余额"
```

### 列名常量（COL\_\*）

为消除硬编码，`shared/config.py` 通过 `ColumnMapper` 自动生成列名常量：

| 常量                       | 默认值                                   | 用途        |
| ------------------------ | ------------------------------------- | --------- |
| `COL_CUSTOMER_ID`        | `"客户编号"`                              | 主键列名      |
| `COL_CUSTOMER_ID_STR`    | `"客户编号_str"`                          | 派生主键列     |
| `COL_TARGET`             | `"is_bad"`                            | 目标变量列名    |
| `COL_REPORT_DATE`        | `"报告日期"`                              | 报告日期列名    |
| `COL_QUAL_PREFIX`        | `"是_"`                                | 资质标签前缀    |
| `COL_SEGMENT_DIMS`       | `['所属行业', '所属分行', ...]`               | 分群维度列表    |
| `COL_SEGMENT_DIMS_DICT`  | `{'industry': '所属行业', ...}`           | 分群维度映射    |
| `COL_INDUSTRY_DATA_COLS` | `['客户分层', '细分赛道', ...]`               | 产业属性列     |
| `COL_AMOUNT_COLS`        | `['授信总金额', '表内授信余额', ...]`            | 金额字段      |
| `COL_SEGMENT_IV_LIMITS`  | `{'industry': 15, 'branch': 20, ...}` | IV分析唯一值上限 |

**使用方式：**

```python
# 各模块通过 from shared.config import * 自动获得
from shared.config import COL_CUSTOMER_ID, COL_TARGET

df[COL_CUSTOMER_ID]  # 替代 df['客户编号']
df[COL_TARGET]       # 替代 df['is_bad']
```

**适配时，只需修改** **`column_mapping.yaml`：**

```yaml
required:
  customer_id: "CUST_NO"    # 常量 COL_CUSTOMER_ID 自动变为 "CUST_NO"
  target: "DEFAULT_FLAG"    # 常量 COL_TARGET 自动变为 "DEFAULT_FLAG"
```

所有业务代码无需修改，常量自动跟随配置变化。

### 适配示例

假设银行字段名与本工具默认值不同，只需创建 `config/city_bank.yaml`：

```yaml
# 仅覆盖差异项，其余自动使用 default.yaml 默认值
thresholds:
  min_samples: 30            # 该行样本较少，放宽阈值
  min_bad_samples: 5

column_mapping:
  required:
    customer_id: "客户号"     # 该行叫"客户号"
    target: "是否不良"        # 该行叫"是否不良"
  qualification:
    prefix: "标签_"           # 该行资质列前缀为"标签_"
```

使用自定义配置：

```python
from shared.config_loader import load_config
from shared.column_mapper import ColumnMapper

config = load_config("config/city_bank.yaml")
mapper = ColumnMapper("config/city_bank.yaml")

print(mapper.customer_id)  # -> "客户号"
print(mapper.target)       # -> "是否不良"
```

***

## 五、数据准备要求

### 输入文件格式

- **编码**：UTF-8 或 GBK（工具自动检测）
- **格式**：CSV，首行为表头
- **主键**：必须有唯一标识客户的主键列（默认 `客户编号`）

### 必备数据文件

| 文件    | 必备列           | 说明          |
| ----- | ------------- | ----------- |
| 客户信息  | 主键、分行、行业、企业性质 | 基准表，定义分析总体  |
| 坏客户标记 | 主键、目标变量(0/1)  | 定义风险标签      |
| 征信数据  | 主键、征信特征列      | 可选，用于征信管线   |
| 财务数据  | 主键、财务指标       | 可选，用于工商财务管线 |

### 目标变量说明

- **is\_bad = 1**：坏客户（违约/不良）
- **is\_bad = 0**：好客户
- 建议坏客户率在 1%-10% 区间，过低会导致统计检验不可靠

### 数据目录结构

```
data/
├── raw/                      # 原始数据（只读）
│   ├── 客户信息.csv
│   ├── 征信数据.csv
│   ├── 坏客户标记.csv
│   └── 工商变更_特征.csv
│
├── processed/                # 预处理数据
│   ├── 财务数据_处理后.csv
│   └── 产业数据_处理后.csv
│
├── results/                  # 中间结果
│   ├── 工商财务/
│   └── 征信/
│
output/                       # 最终输出
    ├── 工商财务/
    └── 征信/
```

***

## 六、使用方法

### 方式一：Python API（推荐）

```python
# 切换到 risk-feature-pipeline 目录
import sys
sys.path.insert(0, '/path/to/risk-feature-pipeline')

# 征信管线：完整执行 5 步
from shared.pipeline import run_credit_pipeline
results = run_credit_pipeline()

# 工商财务管线：完整执行 6 步
from shared.pipeline import run_gsfc_pipeline
results = run_gsfc_pipeline()

# 通用管线（自备宽表）：一行 prepare_df + run_generic_pipeline
from risk_data_prep.scripts import prepare_df
from shared.pipeline import run_generic_pipeline

df, feature_cols = prepare_df(
    wide_path='data/processed/舆情特征宽表.csv',
    bad_customer_path='data/raw/坏客户标记.csv',
    id_col='客户编号', target_col='is_bad',
    filter={'企业规模': {'exclude': ['0']}},         # 可选过滤
    exclude_features={'授信总金额', '表内授信余额'}, # 业务列排除
)
run_generic_pipeline(
    df=df, feature_cols=feature_cols, target_col='is_bad',
    project_name='舆情特征分析',
    category_dims=['企业规模'], qual_dims=[],
    steps=['univariate', 'iv', 'lr', 'export'], verbose=False,
)

# 仅执行指定步骤
results = run_gsfc_pipeline(steps=['data_prep', 'feature_eng', 'iv'])

# 静默模式
results = run_credit_pipeline(verbose=False)
```

### 方式二：命令行 CLI

```bash
# 进入 risk-feature-pipeline 目录
cd risk-feature-pipeline

# 征信全流程
python -m shared --pipeline credit

# 工商财务全流程
python -m shared --pipeline gsfc

# 通用宽表（自备宽表 + 坏客户清单）
python -m shared --pipeline generic \
  --input data/processed/舆情特征宽表.csv \
  --target is_bad \
  --merge-target data/raw/坏客户标记.csv \
  --project-name 舆情特征分析

# 指定步骤（注意：征信用 feature_engineering，工商财务用 feature_eng）
python -m shared --pipeline gsfc --steps data_prep,feature_eng,iv
python -m shared --pipeline credit --steps data_prep,feature_engineering,iv

# 静默模式
python -m shared --pipeline credit --quiet

# 查看帮助
python -m shared --help
```

**CLI 参数一览**：

| 参数 | 简写 | 适用管线 | 说明 |
| --- | --- | --- | --- |
| `--pipeline` | `-p` | 全部 | 必填：`credit` / `gsfc` / `generic` |
| `--input` | `-i` | generic | 宽表 CSV 路径（generic 必填） |
| `--target` | — | generic | 目标列名，默认 `is_bad` |
| `--project-name` | — | 全部 | 输出文件前缀，默认「风险特征分析」 |
| `--feature-cols` | — | generic | 特征列名（逗号分隔），默认自动检测 |
| `--merge-target` | — | generic | 坏客户清单 CSV 路径，自动按客户编号左连接 |
| `--steps` | `-s` | 全部 | 要执行的步骤（逗号分隔），默认全部 |
| `--quiet` | `-q` | 全部 | 静默模式 |

### 步骤名称对照

| 步骤 | 名称    | 征信管线              | 工商财务管线        | 通用管线(generic) |
| -- | ----- | ----------------- | ------------- | ------------- |
| 1  | 数据准备  | `data_prep`       | `data_prep`   | —（自备宽表）       |
| 2  | 特征工程  | `feature_engineering` | `feature_eng` | —（自备宽表）       |
| 3  | 单变量分析 | `univariate`      | `univariate`  | `univariate`  |
| 4  | IV诊断  | `iv`              | `iv`          | `iv`          |
| 5  | 逻辑回归  | `lr`              | `lr`          | `lr`          |
| 6  | 结果导出  | `export`          | `export`      | `export`      |

> **注意**：征信管线与工商财务管线的「特征工程」步骤名**不同**——征信用 `feature_engineering`，工商财务用 `feature_eng`。传 `steps=` 参数时按管线对照填写，否则会被 `VALID_STEPS_*` 校验拒绝。

### 方式三：查询已导出结果（不重跑管线）

一旦跑过一次管线并完成 `export`，所有后续"top X"、"分群对比"、"解读"类问题都应**直接读磁盘上的 CSV**，不要重复触发管线：

```python
from risk_result_query.scripts import load_results, top_features

r = load_results('舆情特征分析')    # 自动定位 data/results/征信/<project>/
print(r)                             # 一行看哪些对象加载成功

# 全量 IV top 15
top_features(r, kind='iv', n=15)

# 分群 IV / LR / 相关性
top_features(r, kind='iv_group', dim='企业规模', group='小型企业', n=15)
top_features(r, kind='lr',       dim='企业规模', group='小型企业', n=15, sign='positive')
top_features(r, kind='corr',     dim='企业规模', group='小型企业', n=15)

# AUC 汇总
r.lr_auc_long
```

非标准查询（透视、冗余特征识别、跨分群对比）见 `risk_result_query/references/query_recipes.md`；
精确列名见 `risk_result_query/references/columns.md`；
磁盘布局见 `risk_result_query/references/file_layout.md`。

### 方式四：抽取客户级风险触碰清单

管线已导出结论后，可用 `risk_trigger_extraction` 把风险结论落到每个客户（**Level 2 客户级风险落地**）：

```python
from risk_data_prep.scripts import prepare_df
from risk_trigger_extraction.scripts.trigger_extraction import extract_triggers

df, _ = prepare_df(
    wide_path='data/processed/舆情特征宽表.csv',
    bad_customer_path='data/raw/坏客户标记.csv',
    id_col='客户编号', target_col='is_bad',
)

df_wide, df_long, df_threshold = extract_triggers(
    df=df,
    project_name='舆情特征分析',
    target_col='is_bad',
    id_col='客户编号',
)
```

产出三张表：

| 文件                      | 内容                                     |
| ----------------------- | -------------------------------------- |
| `<项目>_风险触碰明细_宽表.csv` | 每行一个客户，含触碰标记、触碰特征总数、IV 加权风险得分、触碰特征清单 |
| `<项目>_风险触碰明细_长表.csv` | 仅保留触碰的 客户×特征 记录，含阈值、来源、特征类别           |
| `<项目>_触碰阈值说明.csv`      | 每个特征的触碰条件、好/坏客户均值、阈值来源                |

**阈值策略**（优先级从高到低）：

1. 显式阈值（`RISK_FEATURES` 配置里的 `explicit_threshold` 字段）
2. 坏客户均值（以坏客户平均水平为触碰线，保守且风控意义明确）
3. 好/坏样本不足时用全量中位数兜底

**IV 加权风险得分**：`得分 = Σ(触碰_i × IV_i) / Σ(IV_i) × 100`，高 IV 特征被触碰时贡献更大权重。

如需自定义特征集，传入 `features=` 参数并参照 `risk_trigger_extraction/scripts/config.py` 的 `RISK_FEATURES` 格式。

### 方式五：生成正式 Word 报告

管线导出 `_LLM报告数据.json` 后，可用 `risk_docx_report` 生成 `.docx`：

```bash
cd risk-feature-pipeline/risk_docx_report

# 1. 打包报告写作上下文（report-prompt.md + LLM JSON）
python3 scripts/build_prompt_bundle.py \
  --llm-json ../output/征信/<project>/<project>_LLM报告数据.json

# 2. 拿到大模型输出的 Markdown 正文后渲染 docx
python3 scripts/build_docx_report.py \
  --llm-json   ../output/征信/<project>/<project>_LLM报告数据.json \
  --report-markdown ../output/征信/<project>/<project>_正式报告.md \
  --output     ../output/docx-report/<project>_正式报告.docx
```

### 单步调用（高级）

如需单独调用某步骤：

```python
# Step 1: 数据准备
from risk_data_prep.scripts.data_prep import prepare_credit_wide_table
from risk_data_prep.scripts.io_utils import load_data
data = load_data(CREDIT_CONFIG['data'], project_root)
df, summary = prepare_credit_wide_table(data)

# Step 2: 特征工程
# 征信管线：credit_feature_engineering
from risk_feature_engineering.scripts.credit_feature_engineering import feature_engineering as credit_fe
df = credit_fe(df)

# 工商财务管线：财务 + 工商变更 两步都要跑
from risk_feature_engineering.scripts.financial_feature_engineering import feature_engineering
from risk_feature_engineering.scripts.change_feature_engineering import feature_engineering_gsbb
df = feature_engineering(df)
df = feature_engineering_gsbb(df)

# Step 3: 分群单变量
from risk_segment_univariate.scripts.segment_univariate import univariate_by_group

# Step 4: IV 分析
from risk_iv_diagnosis.scripts.iv_group_diagnosis import iv_by_group, reliability_diagnosis
iv_df, skipped = iv_by_group(df, '所属行业', feature_cols)

# Step 5: 逻辑回归
from risk_logistic_regression.scripts.group_logistic_regression import lr_by_group

# Step 5.5（可选）: 决策树规则挖掘
from risk_rule_mining.scripts.rule_extraction import mine_rules
from risk_rule_mining.scripts.rule_mining_pipeline import rules_by_group, export_rules
rules_df = mine_rules(df, feature_cols, target='is_bad')

# Step 6: 导出
from risk_export_report.scripts.report_analysis import export_results, build_llm_report_data

# 附加：客户级风险触碰提取（Level 2，产出触碰宽表/长表/阈值表）
from risk_trigger_extraction.scripts.trigger_extraction import extract_triggers
df_wide, df_long, df_threshold = extract_triggers(
    df=df, project_name='舆情特征分析', target_col='is_bad', id_col='客户编号',
)
```

***

## 七、输出文件说明

### 标准输出文件列表

执行完成后，输出目录包含以下 8 个标准 CSV（UTF-8 BOM 编码）：

| 文件名                  | 内容             |
| -------------------- | -------------- |
| `_IV分析结果.csv`        | 全样本 IV 值       |
| `_特征风险相关性.csv`       | 分群相关系数         |
| `_逻辑回归系数.csv`        | LR系数 + AUC类型标记 |
| `_IV值分析.csv`         | 分群IV + 可信度评级   |
| `_IV可信度透视表.csv`      | 可信度统计汇总        |
| `_分群样本概况.csv`        | 各维度分群统计        |
| `_原始vs衍生特征AUC对比.csv` | 特征集对比          |
| `_综合特征分析结果.csv`      | 综合分析结果         |

### AUC类型说明

| 标记         | 含义        | 出现条件              |
| ---------- | --------- | ----------------- |
| `交叉验证`     | 5折交叉验证AUC | 样本 ≥200 且 坏客户 ≥30 |
| `训练集-样本不足` | 仅训练集AUC   | 样本不足无法交叉验证        |

### IV可信度评级

| 评级          | 条件        | 建议      |
| ----------- | --------- | ------- |
| `可信`        | 样本充足，IV正常 | 可作为建模依据 |
| `参考`        | 样本略少      | 结合业务判断  |
| `不可信-样本不足`  | 坏客户 <10   | 不建议使用   |
| `不可信-过拟合嫌疑` | IV > 2.0  | 需排查异常   |

***

## 八、移植与集成指南

### 移植到隔离环境

1. **复制必要文件**

```bash
# 最小移植：核心模块 + 配置
risk-feature-pipeline/
├── SKILL.md                      # 必需（顶层调度器）
├── AGENTS.md                     # 必需（agent 行为规范）
├── shared/                       # 必需
├── config/                       # 必需
├── risk_data_prep/               # 必需（含 prepare_df.py）
├── risk_iv_diagnosis/            # 必需
├── risk_logistic_regression/     # 必需
├── risk_export_report/           # 必需
├── risk_feature_engineering/     # 工商财务管线需要
├── risk_segment_univariate/      # 工商财务管线需要
├── risk_rule_mining/             # 可选：规则挖掘
├── risk_trigger_extraction/      # 可选：客户级风险触碰提取（Level 2）
├── risk_result_query/            # 强烈建议：结果查询（节省 token / 避免重跑）
└── risk_docx_report/             # 可选：正式 Word 交付件
```

1. **适配字段名**

创建 `config/my_bank.yaml`，仅覆盖字段名差异：

```yaml
column_mapping:
  required:
    customer_id: "你行的主键列名"
    target: "你行的目标变量列名"
  segment_dims:
    industry: "你行的行业列名"
    branch: "你行的分行列名"
```

1. **适配数据路径**

修改 `config/my_bank.yaml` 中的路径：

```yaml
data:
  raw:
    customer_info: "/your/path/客户信息.csv"
    bad_labels: "/your/path/坏客户标记.csv"
```

1. **调整阈值（可选）**

根据样本规模调整：

```yaml
thresholds:
  min_samples: 30      # 样本较少时放宽
  min_bad_lr: 10       # 坏客户较少时放宽
```

### 集成到内部工具

#### 方式一：作为模块导入

```python
# 在你的工具代码中
import sys
sys.path.insert(0, '/path/to/risk-feature-pipeline')

from shared.pipeline import run_credit_pipeline
from shared.config_loader import load_config

# 使用自定义配置
config = load_config('/your/path/custom.yaml')

# 执行分析
results = run_credit_pipeline(verbose=False)

# 获取结果 DataFrame
iv_df = results['iv_full']
lr_coef = results['lr_coef_results']['所属行业']
```

#### 方式二：作为服务调用

```python
# 封装为内部服务
class RiskAnalysisService:
    def __init__(self, config_path):
        self.config = load_config(config_path)
        self.mapper = ColumnMapper(config_path)

    def analyze(self, data_path, steps=None):
        # 加载数据、执行分析、返回结果
        results = run_credit_pipeline(steps=steps)
        return results
```

#### 方式三：嵌入 ETL 流程

```python
# 在 ETL 链路中插入分析步骤
def etl_pipeline():
    # Step 1: 数据抽取
    raw_data = extract_from_source()

    # Step 2: 调用风险分析
    from shared.pipeline import run_gsfc_pipeline
    results = run_gsfc_pipeline(steps=['iv', 'lr'])

    # Step 3: 结果写入内部系统
    write_to_internal_db(results['iv_group_all'])
```

***

## 九、注意事项

### 数据安全

- **禁止输出敏感信息**：客户姓名、证件号、手机号不得出现在日志或导出文件
- **CSV编码**：使用 `utf-8-sig` 确保 Excel 正确打开

### 统计可靠性

- **样本不足自动跳过**：低于阈值时自动跳过并记录原因
- **AUC降级**：样本不足时自动使用训练集AUC并标记

### 业务适配

- **目标变量定义**：确保坏客户定义与业务一致
- **分群维度**：选择有业务意义的维度（行业、规模等）
- **特征筛选**：IV > 0.1 建议纳入建模

### 性能优化

- 大数据集（>10万行）建议分批处理
- IV计算可并行化（需自行实现）

***

## 十、常见问题

### Q1: 字段名不匹配怎么办？

修改 `config/column_mapping.yaml` 或创建自定义配置覆盖。

### Q2: 样本不足导致跳过怎么办？

检查 `thresholds` 配置，根据实际样本规模调整下限。

### Q3: 如何只运行部分步骤？

使用 `steps` 参数指定：`run_gsfc_pipeline(steps=['data_prep', 'iv'])`

### Q4: 如何获取单步详细文档？

阅读各 Skill 目录下的 `SKILL.md` 文件。

### Q5: 如何自定义特征工程？

修改 `risk_feature_engineering/scripts/financial_feature_engineering.py`（财务）或 `credit_feature_engineering.py`（征信）或 `change_feature_engineering.py`（工商变更）。

### Q6: 已跑过一次管线，还需要重新跑才能"看 top IV"吗？

**不需要。** 用 `risk_result_query` 直接读磁盘：

```python
from risk_result_query.scripts import load_results, top_features
r = load_results('<project_name>')
top_features(r, kind='iv', n=15)
```

详情见 README §六 "方式三" 或 `risk_result_query/SKILL.md`。

### Q7: 同一份宽表 + 坏客户清单，不同 agent 每次合并代码都不一样怎么办？

统一用 `risk_data_prep.scripts.prepare_df`。它做三件事：打 `is_bad` 标签 → 可选过滤 → 自动挑数值型非零方差特征列。禁止在业务代码里手抄这三步。

### Q8: `skills/` 目录是什么？需要修改吗？

`skills/` 是从 `anthropics/skills` 克隆的**官方参考样例**，仅作为 SKILL.md 写作规范的参考，**不属于本项目**。不要在工程改动中修改或复制其中文件。

***
