"""LLM 抽象层. 默认 Anthropic, 接口 generate(messages, response_schema).

通过 provider 配置位预留 OpenAI / Bedrock / 行内网关替换空间.
"""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .config import LLMConfig

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """LLM 调用失败 (网络/配额/格式)."""


class LLMJSONError(LLMError):
    """LLM 响应不能解析为 JSON."""


class BaseLLMClient(ABC):
    """LLM 客户端抽象基类."""

    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg

    @abstractmethod
    def _call(self, system: str, user: str, max_tokens: int, temperature: float) -> str:
        """实际调用. 返回纯文本响应."""

    def generate(
        self,
        system: str,
        user: str,
        response_schema: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any] | list[Any] | str:
        """调用 LLM. 若指定 response_schema 则严格 JSON 解析."""
        max_tokens = max_tokens or self.cfg.max_tokens
        temperature = self.cfg.temperature if temperature is None else temperature

        @retry(
            stop=stop_after_attempt(self.cfg.retry_attempts),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type(LLMError),
            reraise=True,
        )
        def _do_call() -> str:
            return self._call(system, user, max_tokens, temperature)

        text = _do_call()

        if response_schema is None:
            return text

        # 严格 JSON 解析
        try:
            return _extract_json(text)
        except json.JSONDecodeError as e:
            # 重试一次让 LLM 修
            logger.warning("LLM 输出非 JSON, 重试一次让其修复: %s", e)
            fix_user = (
                f"上一次输出无法解析为 JSON. 错误: {e}\n"
                f"原始响应:\n```\n{text}\n```\n"
                f"请仅返回符合要求的 JSON,不要任何解释或 markdown 包裹."
            )
            text2 = self._call(system, fix_user, max_tokens, temperature)
            try:
                return _extract_json(text2)
            except json.JSONDecodeError as e2:
                raise LLMJSONError(
                    f"LLM 两次都无法返回有效 JSON: {e2}"
                ) from e2


def _extract_json(text: str) -> Any:
    """从 LLM 响应提取 JSON. 容忍 markdown 包裹的代码块."""
    text = text.strip()
    if text.startswith("```"):
        # 剥掉 ``` ... ``` 包裹
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)


class AnthropicClient(BaseLLMClient):
    def __init__(self, cfg: LLMConfig):
        super().__init__(cfg)
        try:
            import anthropic
        except ImportError as e:
            raise LLMError("未安装 anthropic SDK; pip install anthropic") from e
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise LLMError("缺少环境变量 ANTHROPIC_API_KEY")
        self._client = anthropic.Anthropic(api_key=api_key)

    def _call(self, system: str, user: str, max_tokens: int, temperature: float) -> str:
        try:
            resp = self._client.messages.create(
                model=self.cfg.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except Exception as e:
            raise LLMError(f"Anthropic API 调用失败: {e}") from e
        # 拼接所有 text 块
        return "".join(b.text for b in resp.content if hasattr(b, "text"))


def build_client(cfg: LLMConfig) -> BaseLLMClient:
    """工厂. 按 cfg.provider 返回对应客户端."""
    provider = cfg.provider.lower()
    if provider == "anthropic":
        return AnthropicClient(cfg)
    raise LLMError(f"未支持的 LLM provider: {provider}")
