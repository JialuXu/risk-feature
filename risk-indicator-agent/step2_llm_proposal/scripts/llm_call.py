"""调 LLM. 严格 JSON 解析, 错误重试一次让 LLM 修."""

from __future__ import annotations

import logging
from typing import Any

from indicator_pipeline.llm_client import BaseLLMClient, LLMJSONError

logger = logging.getLogger(__name__)


def call_llm_for_proposals(
    client: BaseLLMClient,
    system_prompt: str,
    user_prompt: str,
) -> tuple[list[dict[str, Any]], str | None]:
    """调 LLM 拿提案数组. 返回 (proposals, error_msg).

    error_msg 为 None 表示成功; 否则 proposals 是空列表 + 失败原因.
    """
    try:
        result = client.generate(
            system=system_prompt,
            user=user_prompt,
            response_schema={"type": "array"},  # 用作信号让 client 走 JSON 严格解析
        )
    except LLMJSONError as e:
        logger.warning("LLM JSON 解析失败: %s", e)
        return [], f"JSONParseError: {e}"
    except Exception as e:
        logger.warning("LLM 调用失败: %s", e)
        return [], f"LLMError: {e}"

    if not isinstance(result, list):
        return [], f"LLM 返回类型不是 list: {type(result).__name__}"

    proposals = []
    for item in result:
        if isinstance(item, dict):
            proposals.append(item)
        else:
            logger.warning("跳过非 dict 提案: %s", item)
    return proposals, None


__all__ = ["call_llm_for_proposals"]
