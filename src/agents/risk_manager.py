from src.agents.base_agent import BaseAgent
from src.models.stock_data import StockDataPackage


class RiskManagerAgent(BaseAgent):
    """Risk assessment and portfolio protection specialist."""

    def __init__(self, **kwargs):
        super().__init__(
            name="Risk Manager",
            prompt_file="risk_manager.md",
            **kwargs,
        )

    def _format_data(self, data: StockDataPackage) -> str:
        """Risk manager gets ALL data — needs the full picture."""
        return data.to_summary_text()
