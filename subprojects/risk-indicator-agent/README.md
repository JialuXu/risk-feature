# risk-indicator-agent

LLM 指标衍生 Agent 流水线 — 把 `risk-feature-pipeline` 的特征挖掘结果翻译成衍生指标设计稿（含元表注册）。

## 快速开始

```bash
cd <仓库根>/risk-indicator-agent
pip install -e .
cp .env.example .env  # 填 ANTHROPIC_API_KEY

# 单元测试
pytest tests/ -v

# 端到端测试（用 20 条新种子 + Mock LLM）
pytest tests/test_e2e_seed20.py -v

# 真实跑通一个 batch
BATCH=$(date +%Y%m%d)_first
python -m indicator_pipeline --step 1 --batch-id $BATCH
python -m indicator_pipeline --step 2 --batch-id $BATCH
python -m indicator_pipeline --step 3 --batch-id $BATCH
# Step 3 输出 review packet → 人审 → 创建 sentinel 文件
touch data/processed/$BATCH/APPROVED
python -m indicator_pipeline --step 4 --batch-id $BATCH
# 数仓回填 shadow_iv_response.json → 人审
touch data/processed/$BATCH/STEP5_APPROVED
python -m indicator_pipeline --step 5 --batch-id $BATCH
```

## 目录结构

详见 `SKILL.md`。简版：

```
risk-indicator-agent/
├── SKILL.md / AGENTS.md / README.md   总文档
├── config/                             配置（meta_schema 是单一事实源）
├── prompts/                            外置 .md prompt（人审/git diff 友好）
├── references/                         软链到 <本地参考资料>/
├── indicator_pipeline/                 共享组件
├── step1..step5_*/                     5 个独立子 Skill
├── data/                               工作目录（raw/processed/meta_store/results）
├── output/                             最终交付物
└── tests/                              单测 + e2e
```

## 关键设计

| 决策 | 选择 |
|---|---|
| 元表存储 | SQLite + CSV 双写（SCD2） |
| LLM | Anthropic Claude（抽象层支持后续换 provider） |
| 去重 | rapidfuzz 文本相似度（首版无 embedding） |
| 人审 | 异步 sentinel 文件（写 review packet + 等 APPROVED 文件） |
| Step 4 | 仅出工单 + SQL 骨架，本地不执行 |

详见 `<本地实施计划>`（实施计划）。

## 与 risk-feature-pipeline 的关系

- **上游**：消费 `risk-feature-pipeline/data/results/{project}/` 的 IV/LR 结果
- **下游**：写入元表后，下次特征分析重跑时把 P3-观察 指标加入验证；IV 结果回写到元表 `iv_history`

## 文档参考

- 业务方法论：`references/工作链路-指标设计方法论.md`
- 元表 40 字段：`references/衍生指标层数据结构设计文档.md` §1.2
- 4 个设计模式：`references/原始加工逻辑整合纪要.md` §3
