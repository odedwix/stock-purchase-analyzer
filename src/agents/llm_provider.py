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
        import asyncio

        max_retries = 3
        for attempt in range(max_retries):
            try:
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
            except Exception as e:
                err_str = str(e)
                is_rate_limit = "429" in err_str or "413" in err_str or "rate_limit" in err_str.lower()
                if is_rate_limit and attempt < max_retries - 1:
                    wait = (attempt + 1) * 30
                    logger.warning(f"Groq rate limited (attempt {attempt+1}/{max_retries}), retrying in {wait}s...")
                    await asyncio.sleep(wait)
                else:
                    raise


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


class AnthropicProvider(LLMProvider):
    """Anthropic Claude API provider."""

    def __init__(self, model: str | None = None):
        import anthropic

        self.model_name = model or settings.anthropic_model
        api_key = settings.anthropic_api_key

        # Fallback: shell env may override .env with empty string (e.g. from Claude Code)
        if not api_key:
            from dotenv import dotenv_values
            from config.settings import PROJECT_ROOT
            vals = dotenv_values(PROJECT_ROOT / ".env")
            api_key = vals.get("ANTHROPIC_API_KEY", "")

        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set in .env or environment")

        self.client = anthropic.AsyncAnthropic(api_key=api_key)

    async def generate(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 2000,
        temperature: float = 0.7,
    ) -> tuple[str, int, int]:
        import asyncio

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = await self.client.messages.create(
                    model=self.model_name,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system_prompt,
                    messages=[
                        {"role": "user", "content": user_message},
                    ],
                )

                text = response.content[0].text if response.content else ""
                input_tokens = response.usage.input_tokens
                output_tokens = response.usage.output_tokens

                return text, input_tokens, output_tokens
            except Exception as e:
                err_str = str(e)
                is_overloaded = "529" in err_str or "overloaded" in err_str.lower()
                is_rate_limit = "429" in err_str or "rate" in err_str.lower()
                if (is_overloaded or is_rate_limit) and attempt < max_retries - 1:
                    wait = (attempt + 1) * 10
                    logger.warning(f"Anthropic API overloaded (attempt {attempt+1}/{max_retries}), retrying in {wait}s...")
                    await asyncio.sleep(wait)
                else:
                    raise


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

    if provider == "anthropic":
        return AnthropicProvider()

    if provider == "ollama":
        return OllamaProvider()

    if provider == "gemini":
        model = settings.gemini_agent_model if role == "agent" else settings.gemini_summarizer_model
        return GeminiProvider(model=model)

    # Default to Groq
    return GroqProvider()
