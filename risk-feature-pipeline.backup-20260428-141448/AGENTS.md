# AGENTS.md — risk-feature-pipeline 硬规矩

本文件是所有在 `risk-feature-pipeline/` 下运行的 agent 的强制行为约束。SKILL.md 负责"选什么"，本文件负责"怎么做不出错"。

**执行任何步骤前必须读完本文件。**

---

## 一、绝对触发 / 绝对排斥

### 绝对触发（条件成立时，必须且只能走这条路）

| 用户意图信号 | 必须触发 | 禁止替代 |
|---|---|---|
| "查/读/看/解读/top X/已有结果" | `risk_result_query.load_results` | 重跑管线 |
| 提供宽表路径 + 坏客户路径 | `prepare_df` | 手写合并代码 |
| "哪些客户触碰阈值/风险预警名单/客户级扫描" | `risk_trigger_extraction.extract_triggers` | 自行写阈值判断逻辑 |
| "生成 Word/正式报告" | `risk_docx_report` | 直接输出 Markdown |
| 任何 IV > 2.0 的特征 | 标记"过拟合嫌疑"并强制排除出结论推荐 | 正常纳入结论 |

### 绝对排斥（无条件禁止，不因上下文而例外）

- 手抄"读宽表 + merge 坏客户 + 筛特征列"逻辑——统一用 `prepare_df`
- 跨 Bash 调用依赖 Python 状态（每次 Bash 是独立进程，变量不保留）
- 整表 `print(df)` / `df.to_string()`——超过屏幕可读范围必须 `head(N)`
- 输出中出现客户姓名、客户编号、手机号任意一项
- 跳过 segment 不记录原因（必须 log "跳过：{原因}"）
- `verbose=True`（会淹没关键错误信息，默认 `verbose=False`）

---

## 二、结果确定性层次

结论处于哪个层次，决定了可以做什么动作、承担什么责任。

```
Level 1 — 分析结论可用（内部流转）
  达成条件：risk_export_report 完成，以下文件全部落盘：
    *_IV分析结果.csv / *_特征风险相关性.csv / *_逻辑回归系数.csv
    *_IV值分析.csv / *_IV可信度透视表.csv / *_IV可信度诊断.csv
    *_IV值透视表.csv / *_综合特征分析结果.csv
    *_LLM报告数据.json + *_LLM_分群画像.csv
  可做：risk_result_query 查询、人工审阅、修改后重跑
  不可做：对外交付、写入预警名单

Level 2 — 结论落到客户个体（可运营，对内不可随意撤回）
  达成条件：risk_trigger_extraction 完成，以下三张表全部写出：
    {project}_风险触碰明细_宽表.csv
    {project}_风险触碰明细_长表.csv
    {project}_触碰阈值说明.csv
  可做：推送预警名单给业务部门、客户经理使用
  不可做：修改底层宽表后不重新 extract_triggers（结果将与名单失去一致性）

Level 3 — 正式报告交付（对外不可撤回）
  达成条件：risk_docx_report 的 .docx 渲染完成并交付
  不可做：此后修改底层 CSV 而不同步重新出报告（报告与数据将失去一致性）
```

**任何 Level 1 之前的中间输出（单步 univariate/IV/LR）均属过渡态，不能作为结论引用。**

---

## 三、最小无歧义工具集与雷区

```
prepare_df          进数据的唯一合法入口
run_*_pipeline      跑分析的唯一合法入口
load_results        读已有结果的唯一合法入口
top_features        排序/筛选结论的唯一合法入口
extract_triggers    客户级风险落地的唯一合法入口
```

### 各工具雷区

| 工具 | 雷区 |
|---|---|
| `prepare_df` | `id_col`/`target_col` 传错会静默通过但目标列语义错误；`filter` 的 `exclude`/`include` 逻辑相反，混用会悄悄过滤掉错误的行 |
| `run_*_pipeline` | `steps` 顺序不当（如先 `export` 再 `iv`）不报错但结果为空；`verbose=True` 会淹没关键错误信息 |
| `load_results` | 读的是**磁盘快照**——上游重跑后若不重新 `load_results`，查询到的是旧结果，缓存失效是隐性 bug |
| `top_features` | `sign='positive'` 在坏客户定义反转的项目中，方向语义与业务直觉相反，需提前确认坏客户方向 |
| `extract_triggers` | 默认 `RISK_FEATURES` 是通用配置；项目专属特征必须显式传 `features=`，否则触碰计算基于错误特征集，名单结果无效 |

---

## 四、事实断层时的核验路径

遇到字段/文件/映射不确定时，**核验后再执行，不允许假设后继续**。

| 断层类型 | 核验方式 | 退路 |
|---|---|---|
| 字段是否存在 | 读 `df.columns` 或 CSV 表头，不猜测 | `ColumnMapper.detect_qual_cols(df.columns)` 自动推断分群维度 |
| 结果文件是否已生成 | 检查 `data/results/征信/{project_name}/` 目录是否有 `*_IV分析结果.csv` | 提示用户先跑 `risk_export_report`，不允许用空结果假装有数据 |
| 列映射是否正确（多银行） | `load_config("{bank}.yaml")` 读取，与 `df.columns` 做交集验证 | 回退 `config/default.yaml` 默认映射，并**显式告知用户**哪些列使用了默认值 |

**任何情况下不允许的退路：** 假设字段存在后继续执行。错误必须在 `prepare_df` 阶段暴露，不能延迟到 `run_pipeline` 内部。

---

## 五、必须物理阻断、等待人类确认的节点

以下三个节点必须**停止执行，输出确认请求，等待用户明确回复后才继续**。

### 阻断节点 1 — 首次运行新数据集之前

**触发条件：** 用户提供从未见过的宽表路径，或切换了银行/项目配置。

**阻断原因：** `id_col`、`target_col`、坏客户定义一旦跑错，后续 8 张 CSV 全部污染，无法从结果层面发现。

**必须确认：**
- [ ] 主键字段名（默认 `客户编号`，实际是？）
- [ ] 坏客户标签列名与定义（1=坏客户还是其他？）
- [ ] 是否需要 `filter` 排除某些企业规模/行业

---

### 阻断节点 2 — extract_triggers 使用非默认 features 配置时

**触发条件：** 用户要求触碰提取，但项目专属特征集与 `RISK_FEATURES` 默认值存在差异（或用户未明确表态用默认）。

**阻断原因：** 触碰阈值计算的特征集错误会直接导致预警名单错误，是可运营决策的上游，一旦推送给业务部门不可撤回。

**必须确认：**
- [ ] 使用默认 `RISK_FEATURES` 配置，还是项目专属特征列表？
- [ ] 如用专属列表，请用户确认 `features=` 参数中每个特征的 `risk_direction` 和 `iv`

---

### 阻断节点 3 — risk_docx_report 生成之前（Level 3 临界点）

**触发条件：** 用户要求"生成正式报告/Word 报告"。

**阻断原因：** `.docx` 一旦生成并交付，报告与底层数据的一致性承诺即成立；此后修改 CSV 须同步重新出报告，否则存在数据与报告不一致的合规风险。

**必须确认：**
- [ ] 当前的 `*_LLM报告数据.json` 是最终版本（无数据更新计划）？
- [ ] 报告用途（内部传阅 vs 对外交付）？

---

## 六、代码模板

### 模板 A — 跑管线（全流程 / 单维快路径）

```python
# Step 1: 数据准备（唯一合法入口）
from risk_data_prep.scripts.prepare_df import prepare_df

df, feature_cols = prepare_df(
    wide_path='data/raw/<宽表>.csv',
    bad_customer_path='data/raw/<坏客户清单>.csv',  # 已有 is_bad 列时可省略
    id_col='客户编号',       # ⚠️ 阻断节点1：确认后才填
    target_col='is_bad',    # ⚠️ 阻断节点1：确认后才填
    filter={'企业规模': {'exclude': ['0']}},  # 按需
    exclude_features={'授信总金额'},           # 按需
)

# Step 2: 跑管线
from shared.pipeline import run_generic_pipeline

run_generic_pipeline(
    df=df,
    feature_cols=feature_cols,
    target_col='is_bad',
    project_name='<项目名>',
    category_dims=['企业规模'],  # 分群维度
    qual_dims=[],                # 定性维度（若有）
    steps=['univariate', 'iv', 'lr', 'export'],
    verbose=False,               # 禁止 True
)
```

### 模板 B — 读已有结果（不重跑管线）

```python
from risk_result_query.scripts.results_loader import load_results, top_features

r = load_results('<项目名>')  # FileNotFoundError 才考虑重跑

# 全量 IV top 15
top_features(r, kind='iv', n=15)

# 分群 LR 正向系数 top 15
top_features(r, kind='lr', dim='企业规模', group='小型企业', n=15, sign='positive')

# 分群相关性 top 15
top_features(r, kind='corr', dim='企业规模', group='小型企业', n=15)
```

### 模板 C — 触碰提取（须先过阻断节点 2）

```python
from risk_data_prep.scripts.prepare_df import prepare_df
from risk_trigger_extraction.scripts.trigger_extraction import extract_triggers

df, _ = prepare_df(
    wide_path='data/raw/<宽表>.csv',
    bad_customer_path='data/raw/<坏客户清单>.csv',
    id_col='客户编号',
    target_col='is_bad',
)

# 使用默认 RISK_FEATURES（需用户确认）
df_wide, df_long, df_threshold = extract_triggers(
    df=df,
    project_name='<项目名>',
)

# 或传入项目专属特征配置（须用户确认每个特征的方向和 IV）
df_wide, df_long, df_threshold = extract_triggers(
    df=df,
    features=MY_FEATURES,  # 用户确认后的列表
    target_col='is_bad',
    id_col='客户编号',
    project_name='<项目名>',
)
```

---

## 七、日志规范

- 每个跳过的 segment 必须 log：`"[跳过] {segment_name}：{原因}（样本={n}，坏客户={n_bad}）"`
- AUC 必须附注类型：`交叉验证` / `训练集-样本不足` / `训练集-CV失败`
- IV 可信度标注：`可信` / `参考` / `不可信-样本不足` / `不可信-过拟合嫌疑`
- 阻断节点触发时输出格式：

```
⚠️ [阻断节点 {N}] 需要确认后才能继续执行
问题：{具体问题}
请回复确认或提供正确值。
```
