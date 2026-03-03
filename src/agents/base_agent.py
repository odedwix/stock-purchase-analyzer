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

# Map old position values (HOLD/SELL) to new enum values
_POSITION_MAP = {
    "STRONG_BUY": "STRONG_BUY",
    "BUY": "BUY",
    "HOLD": "WAIT",
    "WAIT": "WAIT",
    "SELL": "AVOID",
    "AVOID": "AVOID",
    "STRONG_SELL": "STRONG_AVOID",
    "STRONG_AVOID": "STRONG_AVOID",
}


def _parse_position(raw: str) -> Position:
    """Parse position string, mapping old HOLD/SELL values to new WAIT/AVOID."""
    mapped = _POSITION_MAP.get(raw.upper().strip(), "WAIT")
    return Position(mapped)


def _extract_json(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown code blocks and common errors."""
    original_text = text

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
    # 2. Comments (// style)
    cleaned = re.sub(r"//[^\n]*", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 3. Control characters in string values
    cleaned = re.sub(r"[\x00-\x1f]", " ", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 4. Try removing the raw_reasoning field which often has unescaped characters
    # that break JSON parsing. We can reconstruct it from the full response.
    stripped = re.sub(r'"raw_reasoning"\s*:\s*"[^"]*(?:"|\Z)', '"raw_reasoning": ""', cleaned)
    # Also try with the more aggressive pattern for multi-line raw_reasoning
    if stripped == cleaned:
        stripped = re.sub(
            r'"raw_reasoning"\s*:\s*"[\s\S]*?"(\s*[,}])',
            r'"raw_reasoning": ""\1',
            cleaned,
        )

    try:
        result = json.loads(stripped)
        # Restore the full response as raw_reasoning since we stripped it
        result["raw_reasoning"] = original_text
        return result
    except json.JSONDecodeError:
        pass

    # 5. Last resort: try to build a partial result from regex extraction
    result = {}
    # Extract position
    pos_match = re.search(r'"position"\s*:\s*"([^"]+)"', original_text)
    if pos_match:
        result["position"] = pos_match.group(1)
    # Extract confidence
    conf_match = re.search(r'"confidence"\s*:\s*(\d+)', original_text)
    if conf_match:
        result["confidence"] = int(conf_match.group(1))
    # Extract key_arguments array
    args_match = re.search(r'"key_arguments"\s*:\s*\[([\s\S]*?)\]', original_text)
    if args_match:
        try:
            args_text = "[" + args_match.group(1) + "]"
            # Fix trailing commas in the array
            args_text = re.sub(r",\s*\]", "]", args_text)
            result["key_arguments"] = json.loads(args_text)
        except json.JSONDecodeError:
            pass

    if result.get("position") or result.get("confidence"):
        result.setdefault("raw_reasoning", original_text)
        logger.info(f"Extracted partial JSON with {len(result)} fields via regex fallback")
        return result

    # If nothing works, raise to trigger the fallback
    return json.loads(cleaned)  # Will raise JSONDecodeError


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

        formatted_data = self._format_data(data)
        user_message = (
            f"Analyze {data.symbol} based on the following data and provide your "
            f"assessment. Respond ONLY with valid JSON.\n\n{formatted_data}"
        )

        logger.info(f"{self.name}: sending {len(user_message)} chars to LLM")

        response_text, input_tokens, output_tokens = await self.provider.generate(
            system_prompt=self.system_prompt,
            user_message=user_message,
            max_tokens=4000,
            temperature=0.7,
        )
        budget.record_usage(input_tokens, output_tokens)
        logger.info(f"{self.name}: got {len(response_text)} chars back ({input_tokens} in, {output_tokens} out)")

        try:
            parsed = _extract_json(response_text)

            # Robustly parse key_arguments — use .get() to avoid KeyError
            key_arguments = []
            for a in parsed.get("key_arguments", []):
                if isinstance(a, dict):
                    claim = a.get("claim", a.get("argument", a.get("point", "")))
                    evidence = a.get("evidence", a.get("data", a.get("support", a.get("reasoning", ""))))
                    strength = str(a.get("strength", "moderate")).lower()
                    # Normalize strength to valid Literal values
                    if strength not in ("strong", "moderate", "weak"):
                        strength = "moderate"
                    if claim:  # Only add if there's a claim
                        key_arguments.append({"claim": str(claim), "evidence": str(evidence), "strength": strength})
                elif isinstance(a, str):
                    key_arguments.append({"claim": a, "evidence": "", "strength": "moderate"})

            # Robustly parse risks — handle both strings and dicts
            risks = parsed.get("risks_identified", parsed.get("risks", []))
            if isinstance(risks, list):
                risks = [str(r) if isinstance(r, str) else r.get("risk", str(r)) if isinstance(r, dict) else str(r) for r in risks]
            else:
                risks = []

            # Clamp confidence to valid range (Pydantic requires 0-100)
            confidence = parsed.get("confidence", 50)
            try:
                confidence = max(0, min(100, int(confidence)))
            except (ValueError, TypeError):
                confidence = 50

            return AgentAnalysis(
                agent_name=self.name,
                position=_parse_position(parsed.get("position", "WAIT")),
                confidence=confidence,
                key_arguments=key_arguments,
                risks_identified=risks,
                entry_price=_clean_price(parsed.get("entry_price")),
                exit_price=_clean_price(parsed.get("exit_price")),
                stop_loss=_clean_price(parsed.get("stop_loss")),
                time_horizon=parsed.get("time_horizon", ""),
                data_gaps=parsed.get("data_gaps", []),
                raw_reasoning=parsed.get("raw_reasoning", response_text),
            )
        except Exception as e:
            logger.warning(f"{self.name} Phase 1 parse failed: {type(e).__name__}: {e}")
            logger.warning(f"{self.name} raw response (first 500 chars): {response_text[:500]}")

            # Try to extract position and confidence from raw text
            position = Position.WAIT
            confidence = 40
            text_upper = response_text.upper()
            for pos_name in ["STRONG_BUY", "STRONG_AVOID", "BUY", "AVOID", "WAIT"]:
                if pos_name in text_upper:
                    position = _parse_position(pos_name)
                    break
            # Try to find a confidence number near the word "confidence"
            conf_match = re.search(r'"confidence"\s*:\s*(\d+)', response_text)
            if conf_match:
                confidence = max(0, min(100, int(conf_match.group(1))))

            return AgentAnalysis(
                agent_name=self.name,
                position=position,
                confidence=confidence,
                raw_reasoning=response_text,
                data_gaps=[f"Partial parse — raw reasoning preserved: {type(e).__name__}: {e}"],
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
            f"'updated_position': 'BUY|WAIT|AVOID|STRONG_BUY|STRONG_AVOID', "
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
            # Clamp confidence to valid range
            debate_conf = parsed.get("updated_confidence", 50)
            try:
                debate_conf = max(0, min(100, int(debate_conf)))
            except (ValueError, TypeError):
                debate_conf = 50

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
                updated_position=_parse_position(parsed.get("updated_position", "WAIT")),
                updated_confidence=debate_conf,
                strongest_opposing_point=parsed.get("strongest_opposing_point", ""),
                raw_reasoning=response_text,
            )
        except Exception as e:
            logger.warning(f"{self.name} debate response unparseable: {type(e).__name__}: {e}")
            # Try to preserve original position from Phase 1
            original_position = Position.WAIT
            original_confidence = 50
            for a in all_analyses:
                if a.agent_name == self.name:
                    original_position = a.position
                    original_confidence = a.confidence
                    break
            # Try to extract position from raw text
            text_upper = response_text.upper()
            for pos_name in ["STRONG_BUY", "STRONG_AVOID", "BUY", "AVOID", "WAIT"]:
                if pos_name in text_upper:
                    original_position = _parse_position(pos_name)
                    break
            return DebateResponse(
                agent_name=self.name,
                updated_position=original_position,
                updated_confidence=original_confidence,
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
                claim = arg.get("claim", "") if isinstance(arg, dict) else getattr(arg, "claim", str(arg))
                evidence = arg.get("evidence", "") if isinstance(arg, dict) else getattr(arg, "evidence", "")
                if claim:
                    parts.append(f"  Argument: {claim}")
                if evidence:
                    parts.append(f"  Evidence: {evidence}")
            if a.risks_identified:
                parts.append(f"  Risks: {', '.join(str(r) for r in a.risks_identified)}")
            if a.entry_price:
                parts.append(f"  Entry: ${a.entry_price:.2f}")
            if a.exit_price:
                parts.append(f"  Exit: ${a.exit_price:.2f}")
            # Include raw reasoning snippet if no key arguments (fallback display)
            if not a.key_arguments and a.raw_reasoning:
                reasoning_snippet = a.raw_reasoning[:500].replace("\n", " ")
                parts.append(f"  Analysis: {reasoning_snippet}")
        return "\n".join(parts)
