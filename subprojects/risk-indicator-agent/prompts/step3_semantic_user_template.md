# 待校验提案

```json
{candidate_json}
```

# 元表中相似度最高的 Top {top_k} 候选

```json
{similar_existing_json}
```

# 任务

判断本提案与上述任一元表已有指标是否**业务语义重复**, 评估业务口径质量与风险方向一致性.

返回严格 JSON 对象 (字段定义见 system prompt).
