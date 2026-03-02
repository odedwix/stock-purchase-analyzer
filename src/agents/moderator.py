import json
import logging
import re

from src.agents.llm_provider import LLMProvider, get_provider
from src.agents.token_budget import TokenBudget
from src.models.analysis import (
    AgentAnalysis,
    DebateResponse,
    Position,
    Recommendation,
)

logger = logging.getLogger(__name__)

PROMPTS_DIR_PATH = None  # Set from config


class ModeratorAgent:
    """Synthesizes the debate into a final recommendation. Not a regular agent."""

    def __init__(self, provider: LLMProvider | None = None):
        self.provider = provider or get_provider("agent")
        from config.settings import PROMPTS_DIR

        prompt_path = PROMPTS_DIR / "moderator.md"
        self.system_prompt = prompt_path.read_text()

    async def synthesize(
        self,
        symbol: str,
        phase1_analyses: list[AgentAnalysis],
        phase2_rounds: list[list[DebateResponse]],
        budget: TokenBudget,
    ) -> Recommendation:
        """Phase 3: Produce final recommendation from debate transcript."""
        await budget.wait_if_needed()

        transcript = self._build_transcript(symbol, phase1_analyses, phase2_rounds)
        user_message = (
            f"Synthesize the following analyst debate about {symbol} into a final "
            f"investment recommendation. Respond ONLY with valid JSON.\n\n"
            f"{transcript}"
        )

        response_text, input_tokens, output_tokens = await self.provider.generate(
            system_prompt=self.system_prompt,
            user_message=user_message,
            max_tokens=2500,
            temperature=0.5,  # Lower temp for more consistent synthesis
        )
        budget.record_usage(input_tokens, output_tokens)

        try:
            # Extract JSON
            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", response_text)
            json_text = match.group(1).strip() if match else response_text
            match = re.search(r"\{[\s\S]*\}", json_text)
            if match:
                json_text = match.group(0)

            parsed = json.loads(json_text)

            return Recommendation(
                symbol=symbol,
                position=Position(parsed.get("position", "HOLD")),
                confidence=parsed.get("confidence", 50),
                entry_price=parsed.get("entry_price"),
                exit_price=parsed.get("exit_price"),
                stop_loss=parsed.get("stop_loss"),
                risk_reward_ratio=parsed.get("risk_reward_ratio"),
                estimated_upside_pct=parsed.get("estimated_upside_pct"),
                estimated_downside_pct=parsed.get("estimated_downside_pct"),
                bull_case=parsed.get("bull_case", ""),
                bear_case=parsed.get("bear_case", ""),
                time_horizon=parsed.get("time_horizon", ""),
                key_factors=parsed.get("key_factors", []),
                agent_agreement_level=parsed.get("agent_agreement_level", 0.5),
                sector_etf_suggestion=parsed.get("sector_etf_suggestion"),
                total_tokens_used=budget.total_tokens,
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Moderator synthesis failed to parse: {e}")
            return Recommendation(
                symbol=symbol,
                position=Position.HOLD,
                confidence=20,
                bull_case="Analysis could not be completed — parsing error",
                bear_case=str(e),
                total_tokens_used=budget.total_tokens,
            )

    def _build_transcript(
        self,
        symbol: str,
        phase1: list[AgentAnalysis],
        phase2: list[list[DebateResponse]],
    ) -> str:
        parts = [f"=== DEBATE TRANSCRIPT FOR {symbol} ===\n"]

        parts.append("## PHASE 1: INDEPENDENT ANALYSIS\n")
        for a in phase1:
            parts.append(f"### {a.agent_name}")
            parts.append(f"Position: {a.position.value} | Confidence: {a.confidence}%")
            for arg in a.key_arguments:
                parts.append(f"  [{arg.strength}] {arg.claim}")
                parts.append(f"    Evidence: {arg.evidence}")
            if a.risks_identified:
                parts.append(f"  Risks: {', '.join(a.risks_identified)}")
            if a.entry_price:
                parts.append(f"  Entry: ${a.entry_price:.2f}")
            if a.exit_price:
                parts.append(f"  Exit: ${a.exit_price:.2f}")
            if a.stop_loss:
                parts.append(f"  Stop Loss: ${a.stop_loss:.2f}")
            parts.append("")

        for round_num, responses in enumerate(phase2, 1):
            parts.append(f"\n## PHASE 2 ROUND {round_num}: DEBATE\n")
            for r in responses:
                parts.append(f"### {r.agent_name}")
                parts.append(f"Updated Position: {r.updated_position.value} | Confidence: {r.updated_confidence}%")
                if r.concessions:
                    parts.append(f"  Concessions: {'; '.join(r.concessions)}")
                if r.strongest_opposing_point:
                    parts.append(f"  Strongest opposing point: {r.strongest_opposing_point}")
                for reb in r.rebuttals:
                    prefix = "CONCEDES" if reb.concedes else "REBUTS"
                    parts.append(f"  {prefix} {reb.target_agent}: {reb.response}")
                parts.append("")

        return "\n".join(parts)
