---
name: risk_data_prep
description: 风险特征宽表的数据准备：主实体多表合并、清洗、二分类标签打标与分群摸底（内置企业信贷场景脚本，可替换为任意主题宽表）
---

## 方法论前提（与数据来源无关）

- **分析粒度**：一行代表一个主实体（常见为客户/借据/账户；由业务定义），下游 IV、分群 LR、单变量均默认在该粒度上统计。
- **必备列**：稳定主键、二分类目标列（本仓库脚本默认列名为 `is_bad`，若你自有管线改名，须在接入脚本前与下游约定一致）。
- **可选列**：用于分群的类别字段、用于「资质/标签」式对比的二值列（命名可为任意规则；本仓库常用 `是_` 前缀作为二值标签的一种约定，非强制）。
- **数据来源**：征信、工商、财务、司法、供应链等仅为**主题示例**；同一套流程适用于「任意主题宽表」，只要满足上述列语义。

实现代码位于本目录 `scripts/`（下文路径均相对本 Skill 根目录）。

## 流水线位置

- **前置**：无（本 Skill 为分析起点）。若你已自备符合粒度与列约定的宽表，可直接进入 `risk_feature_engineering` 或下游（仍建议做一次样本摸底）。
- **后置**：`risk_feature_engineering`（衍生特征）、`risk_segment_univariate` / `risk_iv_diagnosis` / `risk_logistic_regression`（均需宽表与目标列）。
- **全局约定**：数值/类别缺失策略、主实体总体口径以本 Skill 产出为准；跨 Skill 的样本门槛统一由 `scripts/config.py` 的 `SAMPLE_THRESHOLDS` 定义，不在此重复罗列。

## 何时使用（触发）

- 多表合并为宽表、从 `data/raw` 与 `data/processed` 加载、定义分析总体与主键。
- 目标列打标、各侧表与主实体匹配摸底、分析前样本/坏率概况。
- 用户已提供宽表，但缺少 `is_bad`，需要通过坏客户清单补打标签。

## 职责边界

| 负责 | 不负责 |
|------|--------|
| 本目录内置的「企业信贷参考」数据检测与宽表构建（见下方脚本） | 非本仓库覆盖的主题表合并逻辑（需你自写或另接 ETL） |
| 千分位/金额占位清洗、按业务规则去重取最新（在内置流程中） | 衍生比率特征（见 `risk_feature_engineering`） |
| 输出目标列、打印全量与各维度样本/坏率摸底 | IV、LR、单变量统计（见对应 Skill）；标准八文件导出（见 `risk_export_report`） |

## 调用入口（最小示例）

**自备宽表（任意主题）**：在满足「粒度 + 主键 + 目标列 + 分群/特征列」后直接分析，无需调用本目录脚本。

**如果自备宽表缺少目标列**：
- 不要直接进入 IV / LR / 风险特征结论
- 先要求用户补充坏客户清单，典型示例：`data/raw/坏客户标记.csv`
- 最低要求是能与宽表按主键关联的一份文件：
  - 场景 1：文件包含主键列 + `is_bad`
  - 场景 2：文件只有坏客户主键清单，则清单中的主键记为 1，其余记为 0
- 在 `generic` CLI 中可通过 `--merge-target </path/to/bad_customer_list.csv>` 合并生成目标变量

**Python 直用一行合成（推荐，避免 agent 手写合并）**：

> 路径可以是任意可访问的绝对路径或相对于当前工作目录的路径，不要求项目内有 `data/raw/` 或 `data/processed/` 目录。

```python
from risk_data_prep.scripts.prepare_df import prepare_df

df, feature_cols = prepare_df(
    wide_path='/path/to/your/宽表.csv',          # 任意路径
    bad_customer_path='/path/to/坏客户标记.csv', # 已有 is_bad 列时可省略此参数
    id_col='客户编号', target_col='is_bad',
    filter={
        '企业规模': {'exclude': ['0']},            # 类别排除
        '非银机构占比': {'range': [0, 1]},         # A3：数值范围（同时设 min/max）
        '资产负债率': {'max': 1.0, 'drop_na': True},  # A3：数值上限 + 丢空值
    },
    exclude_features={'授信总金额', '表内授信余额'},  # 业务列排除
)
# 直接喂给下游：
# run_generic_pipeline(df=df, feature_cols=feature_cols, target_col='is_bad', ...)
```

`prepare_df` 做的事：打 `is_bad` 标签 → 可选过滤 → 自动挑数值型非零方差特征列。**不要每个 agent 手抄一遍这三步**。

**filter 规则键（A3 后扩展）**：
- `exclude` / `include` — 类别值列表（按字符串比较）
- `min` / `max` / `range: [lo,hi]` — 数值范围（自动 `pd.to_numeric` 强转）
- `drop_na: true` — 丢弃该列为空的行

CLI 等价：`--filter-file filter.json`。

**内置参考实现（企业信贷常见：多源合并）**：

> 以下为本仓库内置场景的使用方式，须在 `risk-feature-pipeline/` 根目录下以包方式执行（`python -m ...`），或将根目录加入 `sys.path`。自备宽表的用户直接用上方 `prepare_df` 入口即可，不需要使用以下脚本。

```python
from risk_data_prep.scripts.io_utils import load_data, get_project_root
from risk_data_prep.scripts.config import DATA_CONFIG, CREDIT_CONFIG

project_root = get_project_root()
data = load_data(DATA_CONFIG, project_root)
```

以「征信类侧表」为主的宽表构建：

```python
from risk_data_prep.scripts.data_prep import prepare_credit_wide_table

df, summary = prepare_credit_wide_table(data)
```

以「工商 + 财务 + 产业」等侧表为主的宽表构建：

```python
from risk_data_prep.scripts.wide_table_builder import build_wide_table

df = build_wide_table(data)
```

二值标签列检测（示例：约定列名以 `是_` 开头）：

```python
qual_dims = [c for c in df.columns if c.startswith('是_')]
```

## 关键配置（仅列本步读取项）

- 路径与数据源（内置模板）：`scripts/config.py` 中 `DATA_CONFIG`、`CREDIT_CONFIG['data']`。
- 征信宽表准备列清单：`CREDIT_CONFIG['credit_prep_amount_cols']`、`CREDIT_CONFIG['credit_prep_object_keep_cols']`（金额清洗与保留为文本的类别列）。
- 工商财务宽表合并财务侧表时与客户表去重列：`FINANCE_MERGE_DUP_COLS`。
- 授信分层与腰部企业（仅在内置工商财务/授信相关流程中）：`CREDIT_BINS`、`CREDIT_LABELS`、`WAIST_*`、`WAIST_HIGH_RATINGS`。
- 分群维度候选（内置模板）：`SEGMENT_DIMS`、`CREDIT_CONFIG['category_dims']`。司法等其他主题应在你的配置或代码中声明等价的分群列清单。

## 本 Skill 强制规范

- 分析总体以**主实体基准表**去重后的集合为准；侧表（征信、司法等）中落在主实体集合之外的行不纳入分析。
- 数值型缺失填 0 仅适用于「无该主题暴露」等业务可解释情形；类别型缺失保留 NaN，不随意填充。若你更换主题（如司法），应对「无记录」与「未知」区分是否仍适用填 0，并在文档中写明业务含义。
- 合并后必须打印：总样本、好/坏客户数、坏客户率；各数据源匹配条数与剔除说明。
- 金额类字段须清洗 `-`、`,` 等后再转数值；侧表按主键去重取最新记录（具体键名以内置脚本为准）。
- 不在日志或示例中输出客户姓名、证件号、手机号等敏感字段。

## 主要脚本映射

| 模块 | 作用 |
|------|------|
| `scripts/data_prep.py` | `load_credit_data`、`prepare_credit_wide_table` |
| `scripts/wide_table_builder.py` | `build_wide_table` |
| `scripts/io_utils.py` | `load_data`、`read_csv_auto_encoding` |
