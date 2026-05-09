"""
LLM backend wrapper.

Connects to any OpenAI-compatible API server:
  - vLLM:      python3 -m vllm.entrypoints.openai.api_server --model <model> --port 8000
  - llama.cpp: ./llama-server -m model.gguf --port 8000 --ctx-size 4096

Configure via environment variables:
  LLM_BASE_URL  default: http://localhost:8000/v1
  LLM_MODEL     default: mistral-7b-instruct
  LLM_API_KEY   default: not-needed (local servers don't require a real key)
"""

import logging
import os

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class LLMBackend:
    def __init__(self) -> None:
        self.base_url = os.getenv("LLM_BASE_URL", "http://localhost:8000/v1")
        self.model = os.getenv("LLM_MODEL", "mistral-7b-instruct")
        self.api_key = os.getenv("LLM_API_KEY", "not-needed")
        self.client = AsyncOpenAI(base_url=self.base_url, api_key=self.api_key)
        logger.info("LLM backend: %s  model: %s", self.base_url, self.model)

    async def generate(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """Send a chat-completion request and return the assistant's reply."""
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        text = response.choices[0].message.content or ""
        return text.strip()
