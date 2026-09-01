# -*- coding: utf-8 -*-
"""本地大模型客户端（research 中间区）

封装 OpenAI 兼容的 chat/completions 调用，指向 .env 中配置的本地大模型 API，
供因子挖掘 Agent 使用。不依赖具体业务逻辑，只负责「发请求 → 取文本」。

注意：当前模型 Qwen3.8-Flash 为推理模型，响应含 reasoning_content（思考过程），
max_tokens 仅计生成部分，需预留充足空间；本客户端默认自动剥离 reasoning。

用法：
    from research.llm_client import LLMClient
    client = LLMClient()
    text = client.chat("请写一个 Qlib 动量因子表达式")
"""

from __future__ import annotations

from research.config import llm_config


class LLMClient:
    """本地大模型的轻量 OpenAI 兼容客户端。"""

    def __init__(self, config: dict | None = None):
        self.cfg = config or llm_config()
        # base_url 形如 http://host:port/v1；SDK 需以 /v1 结尾
        self.base_url = self.cfg["base_url"].rstrip("/")

    def _client(self):
        from openai import OpenAI
        return OpenAI(base_url=self.base_url, api_key=self.cfg["api_key"])

    def chat(self, messages: list[dict], *, temperature: float = 0.6,
             max_tokens: int = 8192) -> str:
        """发送一轮对话，返回助手文本内容（不含 reasoning）。

        参数：
            messages:   [{role: 'system'|'user', content: ...}, ...]
            temperature:采样温度（推理模型通常建议较低值）。
            max_tokens:  生成 token 上限（不含思考 token），需预留足够空间。
        返回：
            助手回复正文。
        """
        client = self._client()
        resp = client.chat.completions.create(
            model=self.cfg["model"],
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        msg = resp.choices[0].message
        # 若服务端把思考放进 content（本实现为 reasoning_content 独立字段），取 content
        text = getattr(msg, "content", "") or ""
        return text.strip()

    @property
    def model(self) -> str:
        return self.cfg["model"]

    def __repr__(self) -> str:
        return f"LLMClient(base_url={self.base_url!r}, model={self.model!r})"
