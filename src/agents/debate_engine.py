import asyncio
import logging
import time

from src.agents.base_agent import BaseAgent
from src.agents.macro_economist import MacroEconomistAgent
from src.agents.moderator import ModeratorAgent
from src.agents.risk_manager import RiskManagerAgent
from src.agents.sector_analyst import SectorAnalystAgent
from src.agents.sentiment_specialist import SentimentSpecialistAgent
from src.agents.stock_analyst import StockAnalystAgent
from src.agents.technical_analyst import TechnicalAnalystAgent
from src.agents.token_budget import TokenBudget
from src.models.analysis import AgentAnalysis, DebateResponse, DebateTranscript, Recommendation
from src.models.stock_data import StockDataPackage

logger = logging.getLogger(__name__)


def _get_agent_delay() -> float:
    """Get delay between agent calls. 0 for local/fast APIs, 6s for rate-limited providers."""
    from config.settings import settings
    # Ollama (local) and Anthropic (fast API, high rate limits) can run in parallel
    if settings.llm_provider in ("ollama", "anthropic"):
        return 0
    return 6  # Groq/Gemini need delays for rate limits


class DebateEngine:
    """Orchestrates the 3-phase multi-agent debate with 5 specialist agents."""

    def __init__(self):
        self.agents: list[BaseAgent] = [
            StockAnalystAgent(),
            SentimentSpecialistAgent(),
            RiskManagerAgent(),
            MacroEconomistAgent(),
            TechnicalAnalystAgent(),
        ]
        self.moderator = ModeratorAgent()
        self.sector_analyst = SectorAnalystAgent()

    async def run_debate(self, data: StockDataPackage) -> DebateTranscript:
        """Run a full analysis debate for a stock."""
        start = time.time()
        budget = TokenBudget()
        symbol = data.symbol

        logger.info(f"Starting debate for {symbol}")

        # Phase 1: Independent analysis + Sector analysis
        delay = _get_agent_delay()
        if delay == 0:
            # Ollama: run Phase 1 agents AND sector analyst all in parallel
            logger.info(f"Phase 1: All {len(self.agents) + 1} agents in parallel (Ollama)")
            phase1_task = self._phase1_analyze(data, budget)
            sector_task = self._run_sector_analysis(data, budget)
            phase1_results, sector_analysis = await asyncio.gather(phase1_task, sector_task)
        else:
            # API: sequential
            logger.info(f"Phase 1: Independent analysis ({len(self.agents)} agents)")
            phase1_results = await self._phase1_analyze(data, budget)
            logger.info("Running sector impact analysis...")
            sector_analysis = await self._run_sector_analysis(data, budget)
            await asyncio.sleep(delay)

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
        delay = _get_agent_delay()
        if delay > 0:
            await asyncio.sleep(delay)
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
            sector_analysis=sector_analysis,
        )

    async def _phase1_analyze(
        self, data: StockDataPackage, budget: TokenBudget
    ) -> list[AgentAnalysis]:
        """Run agents — parallel for Ollama, sequential for API providers."""
        delay = _get_agent_delay()

        if delay == 0:
            # Ollama: run all agents in parallel for ~5x speedup
            logger.info("Running agents in parallel (Ollama)")
            tasks = []
            for agent in self.agents:
                logger.info(f"  Launching: {agent.name}")
                tasks.append(self._run_single_agent(agent, data, budget))
            return list(await asyncio.gather(*tasks))
        else:
            # API providers: sequential with delays for rate limits
            analyses = []
            for i, agent in enumerate(self.agents):
                if i > 0:
                    logger.info(f"Waiting {delay}s before next agent (rate limit)...")
                    await asyncio.sleep(delay)
                logger.info(f"  Agent {i + 1}/{len(self.agents)}: {agent.name}")
                result = await self._run_single_agent(agent, data, budget)
                analyses.append(result)
            return analyses

    async def _run_single_agent(
        self, agent: BaseAgent, data: StockDataPackage, budget: TokenBudget
    ) -> AgentAnalysis:
        """Run a single agent with error handling."""
        try:
            result = await agent.analyze(data, budget)
            logger.info(f"Agent {agent.name}: {result.position.value} ({result.confidence}%) with {len(result.key_arguments)} arguments")
            return result
        except Exception as e:
            logger.error(f"Agent {agent.name} failed completely: {type(e).__name__}: {e}")
            from src.models.analysis import Position
            return AgentAnalysis(
                agent_name=agent.name,
                position=Position.WAIT,
                confidence=0,
                data_gaps=[f"Agent error: {type(e).__name__}: {e}"],
                raw_reasoning=f"Agent failed with error: {e}",
            )

    async def _run_sector_analysis(self, data: StockDataPackage, budget: TokenBudget) -> dict:
        """Run sector analysis with error handling."""
        try:
            result = await self.sector_analyst.analyze(data, budget)
            logger.info("Sector analysis complete")
            return result
        except Exception as e:
            logger.warning(f"Sector analysis failed (non-fatal): {e}")
            return {}

    async def _phase2_debate_round(
        self,
        data: StockDataPackage,
        phase1_analyses: list[AgentAnalysis],
        budget: TokenBudget,
    ) -> list[DebateResponse]:
        """Run one round of debate — parallel for Ollama, sequential for API."""
        delay = _get_agent_delay()

        if delay == 0:
            # Ollama: run debate responses in parallel
            logger.info("Running debate round in parallel (Ollama)")
            tasks = []
            for agent in self.agents:
                tasks.append(self._run_single_debate(agent, data, phase1_analyses, budget))
            return list(await asyncio.gather(*tasks))
        else:
            responses = []
            for i, agent in enumerate(self.agents):
                if i > 0:
                    await asyncio.sleep(delay)
                logger.info(f"  Debate {i + 1}/{len(self.agents)}: {agent.name}")
                result = await self._run_single_debate(agent, data, phase1_analyses, budget)
                responses.append(result)
            return responses

    async def _run_single_debate(
        self,
        agent: BaseAgent,
        data: StockDataPackage,
        phase1_analyses: list[AgentAnalysis],
        budget: TokenBudget,
    ) -> DebateResponse:
        """Run a single debate response with error handling."""
        try:
            return await agent.debate_respond(data, phase1_analyses, budget)
        except Exception as e:
            logger.error(f"Agent {agent.name} debate failed: {type(e).__name__}: {e}")
            # Preserve Phase 1 position
            from src.models.analysis import Position
            orig_pos = Position.WAIT
            orig_conf = 50
            for a in phase1_analyses:
                if a.agent_name == agent.name:
                    orig_pos = a.position
                    orig_conf = a.confidence
                    break
            return DebateResponse(
                agent_name=agent.name,
                updated_position=orig_pos,
                updated_confidence=orig_conf,
                raw_reasoning=f"Debate failed with error: {e}",
            )

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
