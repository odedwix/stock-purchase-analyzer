from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Position(str, Enum):
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"


class Argument(BaseModel):
    """A single argument made by an agent."""

    claim: str
    evidence: str
    strength: Literal["strong", "moderate", "weak"] = "moderate"


class AgentAnalysis(BaseModel):
    """Output from a single agent's independent analysis (Phase 1)."""

    agent_name: str
    position: Position
    confidence: int = Field(ge=0, le=100, description="Confidence 0-100")
    key_arguments: list[Argument] = Field(default_factory=list)
    risks_identified: list[str] = Field(default_factory=list)
    entry_price: float | None = None
    exit_price: float | None = None
    stop_loss: float | None = None
    time_horizon: str = ""  # e.g., "3-6 months"
    data_gaps: list[str] = Field(default_factory=list)
    raw_reasoning: str = ""  # Full text from LLM for debate transcript


class Rebuttal(BaseModel):
    """A response to another agent's argument."""

    target_agent: str
    target_claim: str
    response: str
    concedes: bool = False


class DebateResponse(BaseModel):
    """Output from an agent during debate rounds (Phase 2)."""

    agent_name: str
    rebuttals: list[Rebuttal] = Field(default_factory=list)
    concessions: list[str] = Field(default_factory=list)
    updated_position: Position
    updated_confidence: int = Field(ge=0, le=100)
    strongest_opposing_point: str = ""
    raw_reasoning: str = ""


class HistoricalMatch(BaseModel):
    """A matched historical scenario."""

    title: str
    description: str
    similarity_score: float = Field(ge=0, le=1)
    outcome: str
    time_period: str = ""


class Recommendation(BaseModel):
    """Final recommendation produced by the moderator after debate."""

    symbol: str
    position: Position
    confidence: int = Field(ge=0, le=100)

    # Price targets
    entry_price: float | None = None
    exit_price: float | None = None
    stop_loss: float | None = None

    # Risk/reward
    risk_reward_ratio: float | None = None
    estimated_upside_pct: float | None = None
    estimated_downside_pct: float | None = None

    # Analysis
    bull_case: str = ""
    bear_case: str = ""
    time_horizon: str = ""
    key_factors: list[str] = Field(default_factory=list)

    # Agreement
    agent_agreement_level: float = Field(
        default=0.0, ge=0, le=1, description="0=total disagreement, 1=unanimous"
    )

    # Context
    historical_matches: list[HistoricalMatch] = Field(default_factory=list)
    sector_etf_suggestion: str | None = None

    # Metadata
    created_at: datetime = Field(default_factory=datetime.now)
    total_tokens_used: int = 0
    analysis_duration_seconds: float = 0.0


class DebateTranscript(BaseModel):
    """Full record of the multi-agent debate."""

    symbol: str
    phase1_analyses: list[AgentAnalysis] = Field(default_factory=list)
    phase2_rounds: list[list[DebateResponse]] = Field(default_factory=list)
    moderator_synthesis: str = ""
    recommendation: Recommendation | None = None
    created_at: datetime = Field(default_factory=datetime.now)
