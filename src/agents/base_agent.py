import json
import logging
import re
from pathlib import Path

from config.settings import PROMPTS_DIR
from src.agents.llm_provider import LLMProvider, get_provider
from src.agents.token_budget import TokenBudget
from src.models.analysis import AgentAnalysis, DebateResponse, Position
from src.models.stock_data import StockDataPackage

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown code blocks and common errors."""
    # Try to find JSON in code blocks
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        text = match.group(1).strip()

    # Try to find JSON object
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        text = match.group(0)

    # Try parsing as-is first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fix common LLM JSON errors:
    # 1. Trailing commas before } or ]
    cleaned = re.sub(r",\s*([}\]])", r"\1", text)
    # 2. Single quotes instead of double quotes (simple cases)
    # 3. Unquoted keys
    # 4. Comments (// style)
    cleaned = re.sub(r"//[^\n]*", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Last resort: try to extract key-value pairs more aggressively
    # Remove any non-JSON text before/after the object
    cleaned = re.sub(r"[\x00-\x1f]", " ", cleaned)  # Control chars
    return json.loads(cleaned)


def _clean_price(value) -> float | None:
    """Parse price values that may contain $ signs, text, or percentages."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        # Extract first number from strings like "$160", "$171.03 (support level)", "-15%"
        match = re.search(r"[\d]+\.?\d*", value.replace(",", ""))
        if match:
            return float(match.group(0))
    return None


def _clean_string_list(items: list) -> list[str]:
    """Convert a list that may contain dicts or other types to a list of strings."""
    result = []
    for item in items:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            # Agents sometimes return {"agent": "...", "concession": "..."} instead of strings
            parts = [str(v) for v in item.values() if v]
            result.append(" — ".join(parts))
        else:
            result.append(str(item))
    return result


class BaseAgent:
    """Base class for all specialist agents."""

    def __init__(self, name: str, prompt_file: str, provider: LLMProvider | None = None):
        self.name = name
        self.provider = provider or get_provider("agent")
        self.system_prompt = self._load_prompt(prompt_file)

    def _load_prompt(self, filename: str) -> str:
        path = PROMPTS_DIR / filename
        if path.exists():
            return path.read_text()
        raise FileNotFoundError(f"Prompt file not found: {path}")

    def _format_data(self, data: StockDataPackage) -> str:
        """Format data for this agent. Override in subclasses for data slicing."""
        return data.to_summary_text()

    async def analyze(
        self, data: StockDataPackage, budget: TokenBudget
    ) -> AgentAnalysis:
        """Phase 1: Independent analysis."""
        await budget.wait_if_needed()

        user_message = (
            f"Analyze {data.symbol} based on the following data and provide your "
            f"assessment. Respond ONLY with valid JSON.\n\n{self._format_data(data)}"
        )

        response_text, input_tokens, output_tokens = await self.provider.generate(
            system_prompt=self.system_prompt,
            user_message=user_message,
            max_tokens=4000,
            temperature=0.7,
        )
        budget.record_usage(input_tokens, output_tokens)

        try:
            parsed = _extract_json(response_text)
            return AgentAnalysis(
                agent_name=self.name,
                position=Position(parsed.get("position", "HOLD")),
                confidence=parsed.get("confidence", 50),
                key_arguments=[
                    {"claim": a["claim"], "evidence": a["evidence"], "strength": a.get("strength", "moderate")}
                    for a in parsed.get("key_arguments", [])
                ],
                risks_identified=parsed.get("risks_identified", []),
                entry_price=_clean_price(parsed.get("entry_price")),
                exit_price=_clean_price(parsed.get("exit_price")),
                stop_loss=_clean_price(parsed.get("stop_loss")),
                time_horizon=parsed.get("time_horizon", ""),
                data_gaps=parsed.get("data_gaps", []),
                raw_reasoning=parsed.get("raw_reasoning", response_text),
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"{self.name} returned unparseable response: {e}")
            return AgentAnalysis(
                agent_name=self.name,
                position=Position.HOLD,
                confidence=30,
                raw_reasoning=response_text,
                data_gaps=[f"Failed to parse structured response: {e}"],
            )

    async def debate_respond(
        self,
        data: StockDataPackage,
        all_analyses: list[AgentAnalysis],
        budget: TokenBudget,
    ) -> DebateResponse:
        """Phase 2: Respond to other agents' positions."""
        await budget.wait_if_needed()

        others_text = self._format_others_positions(all_analyses)
        user_message = (
            f"You previously analyzed {data.symbol}. Now review your fellow analysts' "
            f"positions and respond. Challenge weak arguments, concede strong ones, and "
            f"update your position if warranted. Respond ONLY with valid JSON.\n\n"
            f"YOUR ORIGINAL POSITION: Review the debate below.\n\n"
            f"OTHER ANALYSTS' POSITIONS:\n{others_text}\n\n"
            f"Respond with JSON: {{'rebuttals': [{{'target_agent': '...', 'target_claim': '...', "
            f"'response': '...', 'concedes': true/false}}], 'concessions': ['...'], "
            f"'updated_position': 'BUY|SELL|HOLD|STRONG_BUY|STRONG_SELL', "
            f"'updated_confidence': 0-100, 'strongest_opposing_point': '...'}}"
        )

        response_text, input_tokens, output_tokens = await self.provider.generate(
            system_prompt=self.system_prompt,
            user_message=user_message,
            max_tokens=3000,
            temperature=0.7,
        )
        budget.record_usage(input_tokens, output_tokens)

        try:
            parsed = _extract_json(response_text)
            return DebateResponse(
                agent_name=self.name,
                rebuttals=[
                    {
                        "target_agent": r.get("target_agent", ""),
                        "target_claim": r.get("target_claim", ""),
                        "response": r.get("response", ""),
                        "concedes": r.get("concedes", False),
                    }
                    for r in parsed.get("rebuttals", [])
                ],
                concessions=_clean_string_list(parsed.get("concessions", [])),
                updated_position=Position(parsed.get("updated_position", "HOLD")),
                updated_confidence=parsed.get("updated_confidence", 50),
                strongest_opposing_point=parsed.get("strongest_opposing_point", ""),
                raw_reasoning=response_text,
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"{self.name} debate response unparseable: {e}")
            return DebateResponse(
                agent_name=self.name,
                updated_position=Position.HOLD,
                updated_confidence=30,
                raw_reasoning=response_text,
            )

    def _format_others_positions(self, analyses: list[AgentAnalysis]) -> str:
        parts = []
        for a in analyses:
            if a.agent_name == self.name:
                continue
            parts.append(f"\n--- {a.agent_name} ---")
            parts.append(f"Position: {a.position.value} (Confidence: {a.confidence}%)")
            for arg in a.key_arguments:
                parts.append(f"  Argument: {arg.claim}")
                parts.append(f"  Evidence: {arg.evidence}")
            if a.risks_identified:
                parts.append(f"  Risks: {', '.join(a.risks_identified)}")
            if a.entry_price:
                parts.append(f"  Entry: ${a.entry_price:.2f}")
            if a.exit_price:
                parts.append(f"  Exit: ${a.exit_price:.2f}")
        return "\n".join(parts)
