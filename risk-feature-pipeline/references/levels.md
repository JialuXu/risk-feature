# 结果确定性层次（Level 1 / 2 / 3）

结论处于哪个层次，决定了可以做什么动作、承担什么责任。状态由
`.pipeline_state.json` 追踪，**只升不降**；`query` / `visualize` /
`explore_thresholds` 是只读动作，不改 level。

```
前置 → 过渡态 → Level 1 → Level 2 → Level 3
prepare   analyze    export     trigger    report
```

## Level 1 — 分析结论可用（内部流转）

**达成条件：** `export` 完成，以下文件全部落盘（`data/results/<project>/`）：

```
*_IV分析结果_全量.csv ⭐ / *_IV分析结果_分群.csv ⭐
*_特征风险相关性.csv / *_逻辑回归系数.csv
*_IV可信度透视表.csv / *_IV可信度诊断.csv
*_IV值透视表.csv / *_综合特征分析结果.csv
*_LLM报告数据.json + *_LLM_分群画像.csv
*_audit.json ⭐（机器可读自检：IV>2 疑似数据穿越 + 不稳定规则）
```

- 可做：`query` 查询、`visualize` 出图、人工审阅、修改后重跑
- 不可做：对外交付、写入预警名单

## Level 2 — 结论落到客户个体（可运营，对内不可随意撤回）

**达成条件：** `trigger` 完成，三张表全部写出（`output/<project>/`）：
`{project}_风险触碰明细_宽表.csv` / `_长表.csv` / `{project}_触碰阈值说明.csv`

- 可做：推送预警名单给业务部门、客户经理使用
- 不可做：修改底层宽表后不重新 trigger（结果将与名单失去一致性）

## Level 3 — 正式报告交付（对外不可撤回）

**达成条件：** `report` 的 `.docx` 渲染完成并交付。

- 不可做：此后修改底层 CSV 而不同步重新出报告（报告与数据将失去一致性）

---

**任何 Level 1 之前的中间输出（单步 univariate/IV/LR，`_intermediate/` 内容）
均属过渡态，不能作为结论引用。**
