import json
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


class GeminiProvider(LLMProvider):
    """Google Gemini API provider."""

    def __init__(self, model: str | None = None):
        import google.generativeai as genai

        genai.configure(api_key=settings.gemini_api_key)
        self.model_name = model or settings.gemini_agent_model
        self.model = genai.GenerativeModel(
            self.model_name,
            system_instruction=None,  # Set per-call
        )

    async def generate(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 2000,
        temperature: float = 0.7,
    ) -> tuple[str, int, int]:
        import google.generativeai as genai

        model = genai.GenerativeModel(
            self.model_name,
            system_instruction=system_prompt,
            generation_config=genai.GenerationConfig(
                max_output_tokens=max_tokens,
                temperature=temperature,
            ),
        )

        response = await model.generate_content_async(user_message)

        text = response.text
        # Estimate token counts from usage metadata if available
        input_tokens = 0
        output_tokens = 0
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            input_tokens = getattr(response.usage_metadata, "prompt_token_count", 0)
            output_tokens = getattr(response.usage_metadata, "candidates_token_count", 0)

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
    if settings.llm_provider == "ollama":
        return OllamaProvider()

    # Default to Gemini
    model = settings.gemini_agent_model if role == "agent" else settings.gemini_summarizer_model
    return GeminiProvider(model=model)
