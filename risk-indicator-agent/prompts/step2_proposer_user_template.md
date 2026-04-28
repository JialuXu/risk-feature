# 域专属业务上下文

{domain_context}

# 本批输入

## 候选 seed 特征 (from risk-feature-pipeline 挖掘结果)

{seeds_json}

## 可用基础表清单 (你只能引用这里的表)

{base_tables_section}

## 元表中已有的相关指标 (用于去重参考)

{existing_indicators_section}

# 任务

把上述每条 seed 翻译成 1~2 条衍生指标提案 (常见 1 条; 当 seed 是"明显由两个原子可组合"时可拆分 2 条).

如果 seed 的 IV 已经很强 (signal_strength=强) 但元表里没有等价指标 → 提一条命名规范的指标, calc_logic 详细写.

如果 seed 的 IV 弱 (signal_strength=观察期) → 仍要提案, 但 priority 设为 P3-观察 或 P4-观察, 并在 notes 里说明 "当前信号弱, 元表保留观察待重跑".

返回 JSON 数组. 数组长度建议 ≤ {max_per_batch} 条.
