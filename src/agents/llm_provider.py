import logging
from abc import ABC, abstractmethod

from config.settings import settings

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """Abstract LLM provider interface."""

    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 2000,
        temperature: float = 0.7,
    ) -> tuple[str, int, int]:
        """Generate a response.

        Returns: (response_text, input_tokens, output_tokens)
        """
        ...


class GroqProvider(LLMProvider):
    """Groq API provider. Free tier: 30 req/min, 14,400 req/day."""

    def __init__(self, model: str | None = None):
        from groq import AsyncGroq

        self.model_name = model or settings.groq_model
        self.client = AsyncGroq(api_key=settings.groq_api_key)

    async def generate(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 2000,
        temperature: float = 0.7,
    ) -> tuple[str, int, int]:
        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )

        text = response.choices[0].message.content or ""
        input_tokens = response.usage.prompt_tokens if response.usage else 0
        output_tokens = response.usage.completion_tokens if response.usage else 0

        return text, input_tokens, output_tokens


class GeminiProvider(LLMProvider):
    """Google Gemini API provider using the new google-genai SDK."""

    def __init__(self, model: str | None = None):
        from google import genai

        self.model_name = model or settings.gemini_agent_model
        self.client = genai.Client(api_key=settings.gemini_api_key)

    async def generate(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 2000,
        temperature: float = 0.7,
    ) -> tuple[str, int, int]:
        from google.genai import types

        response = await self.client.aio.models.generate_content(
            model=self.model_name,
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=max_tokens,
                temperature=temperature,
            ),
        )

        text = response.text
        input_tokens = 0
        output_tokens = 0
        if response.usage_metadata:
            input_tokens = response.usage_metadata.prompt_token_count or 0
            output_tokens = response.usage_metadata.candidates_token_count or 0

        return text, input_tokens, output_tokens


class OllamaProvider(LLMProvider):
    """Ollama local model provider."""

    def __init__(self, model: str | None = None, host: str | None = None):
        self.model = model or settings.ollama_model
        self.host = host or settings.ollama_host

    async def generate(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 2000,
        temperature: float = 0.7,
    ) -> tuple[str, int, int]:
        import httpx

        async with httpx.AsyncClient(base_url=self.host, timeout=300) as client:
            response = await client.post(
                "/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "stream": False,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": temperature,
                    },
                },
            )
            response.raise_for_status()
            data = response.json()

            text = data.get("message", {}).get("content", "")
            input_tokens = data.get("prompt_eval_count", 0)
            output_tokens = data.get("eval_count", 0)

            return text, input_tokens, output_tokens


def get_provider(role: str = "agent") -> LLMProvider:
    """Get the configured LLM provider.

    Args:
        role: "agent" for reasoning tasks, "summarizer" for data condensation
    """
    provider = settings.llm_provider

    if provider == "ollama":
        return OllamaProvider()

    if provider == "gemini":
        model = settings.gemini_agent_model if role == "agent" else settings.gemini_summarizer_model
        return GeminiProvider(model=model)

    # Default to Groq
    return GroqProvider()
