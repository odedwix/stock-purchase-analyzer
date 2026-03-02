import asyncio
import logging
import time

from src.agents.base_agent import BaseAgent
from src.agents.moderator import ModeratorAgent
from src.agents.risk_manager import RiskManagerAgent
from src.agents.stock_analyst import StockAnalystAgent
from src.agents.token_budget import TokenBudget
from src.models.analysis import AgentAnalysis, DebateResponse, DebateTranscript, Recommendation
from src.models.stock_data import StockDataPackage

logger = logging.getLogger(__name__)


class DebateEngine:
    """Orchestrates the 3-phase multi-agent debate."""

    def __init__(self):
        self.agents: list[BaseAgent] = [
            StockAnalystAgent(),
            RiskManagerAgent(),
        ]
        self.moderator = ModeratorAgent()

    async def run_debate(self, data: StockDataPackage) -> DebateTranscript:
        """Run a full analysis debate for a stock."""
        start = time.time()
        budget = TokenBudget()
        symbol = data.symbol

        logger.info(f"Starting debate for {symbol}")

        # Phase 1: Independent analysis (parallel)
        logger.info(f"Phase 1: Independent analysis ({len(self.agents)} agents)")
        phase1_results = await self._phase1_analyze(data, budget)

        # Phase 2: Debate rounds
        phase2_rounds = []
        if self._should_debate(phase1_results):
            logger.info("Phase 2: Debate round 1")
            round1 = await self._phase2_debate_round(data, phase1_results, budget)
            phase2_rounds.append(round1)

            # Only do round 2 if there's still significant disagreement
            if self._still_disagreeing(round1):
                logger.info("Phase 2: Debate round 2 (convergence)")
                round2 = await self._phase2_debate_round(data, phase1_results, budget)
                phase2_rounds.append(round2)
        else:
            logger.info("Phase 2: Skipped — agents are in consensus")

        # Phase 3: Moderator synthesis
        logger.info("Phase 3: Moderator synthesis")
        recommendation = await self.moderator.synthesize(
            symbol, phase1_results, phase2_rounds, budget
        )
        recommendation.analysis_duration_seconds = time.time() - start
        recommendation.total_tokens_used = budget.total_tokens

        logger.info(
            f"Debate complete for {symbol}: {recommendation.position.value} "
            f"(confidence: {recommendation.confidence}%, "
            f"tokens: {budget.total_tokens:,}, "
            f"time: {recommendation.analysis_duration_seconds:.1f}s)"
        )

        return DebateTranscript(
            symbol=symbol,
            phase1_analyses=phase1_results,
            phase2_rounds=phase2_rounds,
            moderator_synthesis=recommendation.bull_case + " | " + recommendation.bear_case,
            recommendation=recommendation,
        )

    async def _phase1_analyze(
        self, data: StockDataPackage, budget: TokenBudget
    ) -> list[AgentAnalysis]:
        """Run all agents' independent analysis in parallel."""
        tasks = [agent.analyze(data, budget) for agent in self.agents]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        analyses = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Agent {self.agents[i].name} failed: {result}")
                analyses.append(
                    AgentAnalysis(
                        agent_name=self.agents[i].name,
                        position="HOLD",
                        confidence=0,
                        data_gaps=[f"Agent error: {result}"],
                    )
                )
            else:
                analyses.append(result)

        return analyses

    async def _phase2_debate_round(
        self,
        data: StockDataPackage,
        phase1_analyses: list[AgentAnalysis],
        budget: TokenBudget,
    ) -> list[DebateResponse]:
        """Run one round of debate where agents respond to each other."""
        tasks = [
            agent.debate_respond(data, phase1_analyses, budget) for agent in self.agents
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        responses = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Agent {self.agents[i].name} debate failed: {result}")
                responses.append(
                    DebateResponse(
                        agent_name=self.agents[i].name,
                        updated_position="HOLD",
                        updated_confidence=0,
                    )
                )
            else:
                responses.append(result)

        return responses

    def _should_debate(self, analyses: list[AgentAnalysis]) -> bool:
        """Skip debate if all agents agree with high confidence."""
        if len(analyses) < 2:
            return False

        positions = {a.position for a in analyses}
        if len(positions) == 1 and all(a.confidence >= 70 for a in analyses):
            logger.info("All agents agree with high confidence — skipping debate")
            return False
        return True

    def _still_disagreeing(self, round_responses: list[DebateResponse]) -> bool:
        """Check if agents are still in significant disagreement after a round."""
        positions = {r.updated_position for r in round_responses}
        if len(positions) == 1:
            return False

        # Check if confidence gap is still large
        confidences = [r.updated_confidence for r in round_responses]
        if max(confidences) - min(confidences) > 30:
            return True

        return len(positions) > 1
