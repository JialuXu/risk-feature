# risk-feature-pipeline 优化方案：单 CLI 收敛 + 中段可独立调用

> 借鉴 kuaicha-search 的"单一调用面 + 自检 + 配置优先级链"，但**不引入** discover/相似度匹配（与 AGENTS.md 的 Level 递进/阻断节点结构性冲突）。

---

## 一、设计目标（同时满足的两条）

1. **AGENTS.md 的硬规矩从口号变约束**：唯一合法入口、阻断节点、Level 递进，agent 物理上无法绕过。
2. **中段可独立调用**：用户拿一份现成宽表，可以直接只跑 IV；拿一份已有结果，可以直接做触碰提取；不强制从 step 1 开始。

两条不冲突——它们恰好是同一个解：**所有子命令都走单 CLI、每个子命令都自己声明前置/后置契约**。Level 守护只在跨界子命令（`trigger` / `report`）才强制。

---

## 二、中段独立调用怎么实现（直接回应新需求）

每个子命令实现两条契约：

**输入契约**：开始时按清单校验存在性；缺什么就 exit 1 + 提示用哪个上游子命令补；**绝不假设存在后继续**。

**产出契约**：每个子命令写出**确定性命名的工件文件**，并把元信息（来源命令、参数 hash、产出文件、Level）追加到当前项目目录的 `.pipeline_state.json`。

这就解锁了三种"中段独立调用"场景：

| 场景 | 调用方式 | 说明 |
|---|---|---|
| 拿外部宽表只跑 IV | `prepare → analyze --steps iv` | 跳过 lr/export，结果只在过渡态，不打 Level 1 stamp |
| 已有 prepared.csv 只跑触碰 | `trigger --prepared prepared.csv --features ...` | 不重跑 analyze；trigger 自己校验 prepared.csv 字段完整性 |
| 只想看上次结果 | `query --project xxx --kind iv --top 15` | 根本不调上游，只读 export 产出 |
| 中途换分群维度重跑一段 | `analyze --steps iv,lr,export --category-dims 行业` | 只重算指定分群，已有结果按项目名隔离不污染 |

关键：**子命令不是 step 内部产物，它们都是一等入口**。`run` 只是 `prepare + analyze + export` 的便捷组合。

---

## 三、CLI 子命令树

```
python -m risk_pipeline <subcommand> [args]
```

| 子命令 | 作用 | 必需输入 | 产出 | Level 影响 |
|---|---|---|---|---|
| `prepare` | 宽表 + 打标 + 特征列推断 | `--wide` `--bad-customer` `--id-col` `--target-col` | `prepared.csv` + `features.json` | 前置 |
| `analyze` | 跑 univariate/iv/lr 子集 | `--prepared` `--features` `--steps` `--category-dims` | 各步内存→落盘中间结果 | 过渡态 |
| `export` | 写 8 张 CSV + LLM JSON | analyze 产出 | 标准 8+1 文件 | **→ Level 1** |
| `query` | 只读已有结果 | export 产出存在 | top-N / 分群查询 | Level 1 后 |
| `trigger` | 客户级触碰提取 | `--prepared` + `--features-file` 或 `--use-default-features` | 三张触碰表 | **→ Level 2** |
| `report` | LLM JSON → docx | LLM JSON 存在 + `--purpose` | `.docx` | **→ Level 3** |
| `run` | 便捷组合：prepare + analyze + export | `--pipeline credit\|gsfc\|generic` | 同 export | **→ Level 1** |

子命令复杂参数（自定义 features 列表、filter 规则等）一律走 `--xxx-file path.json`，借鉴 kuaicha `--params-file` 避开 shell 转义和中文坑。

---

## 四、前置/后置契约的具体形式

### 输入校验

```
[analyze] 需要文件:
  ✗ data/processed/<project>/prepared.csv  （不存在）
  ✗ data/processed/<project>/features.json （不存在）
建议: 先跑 `python -m risk_pipeline prepare --wide ... --bad-customer ...`
exit 1
```

### Status stamp（每个子命令收尾必打）

```
[analyze] OK | project=舆情特征分析 | steps=iv,lr | category_dims=企业规模
         inputs=prepared.csv@2026-04-28T03:11Z, features.json@2026-04-28T03:11Z
         outputs=results/iv_full.csv, results/lr_coef_long.csv
         level=过渡态（未达 Level 1，需要 export）
```

agent 把这一行原样回传给用户作为执行回执。

### `.pipeline_state.json`（项目目录下，单文件）

```json
{
  "project_name": "舆情特征分析",
  "history": [
    {"cmd": "prepare", "ts": "...", "args_hash": "...", "outputs": [...], "level_after": "前置"},
    {"cmd": "analyze", "ts": "...", "args_hash": "...", "steps": ["iv"], "level_after": "过渡态"},
    {"cmd": "export",  "ts": "...", "level_after": "Level 1"}
  ],
  "current_level": "Level 1",
  "known_datasets": ["data/raw/舆情_宽表.csv"]
}
```

`query` / `trigger` / `report` 都可以读这个文件回答"我现在能跑吗"。

---

## 五、阻断节点 CLI 强制化

把 AGENTS.md 五的三个节点从"agent 自觉输出确认"升级成"CLI 拒绝执行"：

| 阻断节点 | CLI 强制方式 |
|---|---|
| **节点 1**（首次新数据集） | `prepare` 在 `--wide` 路径不在 `.pipeline_state.json/known_datasets` 里时，要求 `--confirmed-new-dataset` 才放行；同时**强制 `--id-col` `--target-col` 必传**，不允许默认值 |
| **节点 2**（trigger 用非默认 features） | `trigger` 默认拒绝；要么 `--use-default-features --confirmed`，要么 `--features-file ... --confirmed` |
| **节点 3**（docx 生成） | `report` 必须传 `--purpose internal\|external` + `--confirmed-final-version`，否则拒绝 |

没传 confirm flag → CLI 直接 exit 1 + 打印阻断说明。阻断从"agent 自律"变成"系统约束"。

---

## 六、单维快路径补齐

现在单维快路径只能 Python API（CLI 没 `--category-dims`），所以模板里 agent 不得不在 Bash 里写 Python。补齐之后：

```
python -m risk_pipeline analyze \
  --prepared data/processed/xxx/prepared.csv \
  --features data/processed/xxx/features.json \
  --steps univariate,iv,lr \
  --category-dims 企业规模 \
  --qual-dims ""
```

`--steps` 接受逗号分隔子集；CLI 内部强制按 `univariate→iv→lr→export` 排序执行（哪怕用户写 `export,iv` 也按正确顺序跑），避开 AGENTS.md 三说的"steps 顺序不当不报错但结果为空"雷区。

---

## 七、AGENTS.md 末尾加 self-check 块

借鉴 kuaicha "响应前自检"，加一段不超过 10 行：

```
响应前自检（每次发回复前过一遍）：
- [ ] 已声明本次目标 Level
- [ ] 用了单 CLI 入口（不是 Bash 里手抄 Python import）
- [ ] trigger / report：是否传了 --confirmed flag
- [ ] 任何 IV>2.0 的特征是否标"过拟合嫌疑"且未进结论推荐
- [ ] segment 跳过是否每条有原因 log
- [ ] 输出是否含客户姓名/编号/手机号（必须 0）
- [ ] 末尾是否附了 CLI status stamp
```

---

## 八、配置优先级链显式化

column mapping / 项目配置的优先级独立成段（现状散在 AGENTS.md 四里）：

1. CLI `--columns-file <path>`（最高）
2. 项目目录 `.risk_pipeline_columns.yaml`
3. `config/{bank}.yaml`
4. `config/default.yaml`（兜底，**必须在 stdout 打印用了 default 的哪些键**——借鉴 kuaicha "数据来源标注"的强制 attribution 思路）

---

## 九、分阶段迁移（避免一次大改）

| 阶段 | 动作 | 风险 | 是否破坏现有行为 |
|---|---|---|---|
| **Phase 1** | 在 `shared/cli.py` 实现 6 个子命令，全部 wrap 现有 Python API；`python -m shared --pipeline ...` 保持原样 | 低 | 否（纯加法） |
| **Phase 2** | 给每个子命令加输入校验、status stamp、`.pipeline_state.json` | 低 | 否（纯加法） |
| **Phase 3** | 阻断节点 confirm flag 强制；更新 AGENTS.md 模板 A/B/C 改用 CLI 调用 | 中 | 是（agent 模板变了，需要回归测试） |
| **Phase 4** | AGENTS.md 加 self-check 块；配置优先级链独立段；"手抄 Python 在 Bash 里跑"列为绝对排斥 | 低 | 否（仅文档） |
| **Phase 5（可选）** | `python -m shared --pipeline ...` 改成新 CLI 的 alias；最终保留新 CLI 为唯一入口 | 中 | 是（历史脚本需迁移） |

每个 Phase 完成后建议端到端 smoke test 覆盖：full run（credit/gsfc/generic 各一次）、单维快路径、只跑 query、只跑 trigger 这四条路径。

---

## 十、不动的部分

- 子 skill 目录结构 / Python 模块函数签名都不变，CLI 是它们上面的薄壳
- AGENTS.md 的 Level 1/2/3 语义、雷区表、IV>2.0 规则、verbose=False 不变
- 各子 skill 自己的 SKILL.md 不必动，CLI 子命令是它们的"上游入口"
- **不引入** kuaicha 的 discover / 相似度匹配（与 AGENTS.md 的确定性约束冲突）

---

## 十一、风险与权衡

- **Agent 在历史会话/历史模板下还会写裸 Python**：靠 AGENTS.md 一新增"绝对排斥：在 Bash 里 import risk_pipeline 模块直接调用，必须走 `python -m risk_pipeline ...`"压住，并把模板 A/B/C 改成 CLI 调用示范
- **CLI 表达力天花板**：复杂参数走 `--xxx-file path.json`（features 列表、filter 规则、columns 映射），借鉴 kuaicha `--params-file` 模式
- **`.pipeline_state.json` 跨用户/跨机器协作**：建议项目目录下，**纳入 git**（非临时态），让多人在同一项目下能看到彼此的执行历史
- **测试成本**：Phase 3 是行为改变最大的一步，必须先在一个非生产项目上跑通 4 条 smoke 路径

---

## 十二、与 kuaicha 的对照（取舍备忘）

| kuaicha 模式 | 是否借鉴 | 理由 |
|---|---|---|
| 单一 CLI 入口（`kuaicha_tool.mjs`） | **借** | 解决"手抄代码 + 跨 Bash 状态丢失"两大隐患的同一个解 |
| `--params-file` 处理复杂/中文参数 | **借** | 直接搬，避开 shell 转义 |
| "响应前自检"压缩 checklist | **借** | 把 AGENTS.md 已有规则做成一次扫一眼的尾页 |
| 凭据/配置优先级链 + 默认值要明示 | **借** | 已有思想散在 AGENTS.md，独立成段并强制 stdout 提示 |
| `discover` + 相似度匹配 | **不借** | 与 Level 递进 + 阻断节点的确定性结构性冲突 |
| 服务端工具注册表（gateway） | **不借** | 你的子 skill 是有序工作流不是同质工具 |
| 模糊匹配企业简称类回退 | **不借** | 你的字段不允许"猜"——AGENTS.md 四已明确 |
