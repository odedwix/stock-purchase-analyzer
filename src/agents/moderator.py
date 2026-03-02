import json
import logging

from src.agents.base_agent import _clean_price, _clean_string_list, _extract_json, _parse_position
from src.agents.llm_provider import LLMProvider, get_provider
from src.agents.token_budget import TokenBudget
from src.models.analysis import (
    AgentAnalysis,
    DebateResponse,
    Position,
    Recommendation,
)

logger = logging.getLogger(__name__)


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
            max_tokens=5000,
            temperature=0.5,
        )
        budget.record_usage(input_tokens, output_tokens)

        try:
            parsed = _extract_json(response_text)

            return Recommendation(
                symbol=symbol,
                position=_parse_position(parsed.get("position", "WAIT")),
                confidence=parsed.get("confidence", 50),
                # Legacy entry/exit
                entry_price=_clean_price(parsed.get("entry_price")),
                exit_price=_clean_price(parsed.get("exit_price")),
                stop_loss=_clean_price(parsed.get("stop_loss")),
                # Detailed entry strategy
                entry_price_aggressive=_clean_price(parsed.get("entry_price_aggressive")),
                entry_price_conservative=_clean_price(parsed.get("entry_price_conservative")),
                scaling_plan=parsed.get("scaling_plan", ""),
                # Detailed exit strategy
                exit_price_partial=_clean_price(parsed.get("exit_price_partial")),
                exit_price_full=_clean_price(parsed.get("exit_price_full")),
                # Dual stop-loss
                stop_loss_tight=_clean_price(parsed.get("stop_loss_tight")),
                stop_loss_wide=_clean_price(parsed.get("stop_loss_wide")),
                # Position sizing
                position_size_pct=parsed.get("position_size_pct"),
                # Risk/reward
                risk_reward_ratio=parsed.get("risk_reward_ratio"),
                estimated_upside_pct=parsed.get("estimated_upside_pct"),
                estimated_downside_pct=parsed.get("estimated_downside_pct"),
                # Analysis
                bull_case=parsed.get("bull_case", ""),
                bear_case=parsed.get("bear_case", ""),
                time_horizon=parsed.get("time_horizon", ""),
                key_factors=parsed.get("key_factors", []),
                # Multi-timeframe outlook
                outlook_6_months=parsed.get("outlook_6_months", ""),
                outlook_1_year=parsed.get("outlook_1_year", ""),
                outlook_long_term=parsed.get("outlook_long_term", ""),
                # What could change
                what_could_change=_clean_string_list(parsed.get("what_could_change", [])),
                contradictory_signals=_clean_string_list(parsed.get("contradictory_signals", [])),
                # Influential figures
                influential_figures_summary=parsed.get("influential_figures_summary", ""),
                # Business quality
                moat_assessment=parsed.get("moat_assessment", ""),
                # Agreement
                agent_agreement_level=parsed.get("agent_agreement_level", 0.5),
                sector_etf_suggestion=parsed.get("sector_etf_suggestion"),
                total_tokens_used=budget.total_tokens,
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Moderator synthesis failed to parse: {e}")
            return Recommendation(
                symbol=symbol,
                position=Position.WAIT,
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
