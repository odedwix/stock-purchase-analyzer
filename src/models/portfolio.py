from datetime import date, datetime

from pydantic import BaseModel, Field


class Transaction(BaseModel):
    """A single stock purchase or sale."""

    symbol: str
    action: str = "BUY"  # BUY or SELL
    shares: float
    price_per_share: float
    date: date
    fees: float = 0.0
    notes: str = ""

    @property
    def total_cost(self) -> float:
        return (self.shares * self.price_per_share) + self.fees


class Position(BaseModel):
    """Current position in a stock."""

    symbol: str
    total_shares: float
    avg_cost_basis: float
    total_invested: float
    current_price: float | None = None
    current_value: float | None = None
    unrealized_pnl: float | None = None
    unrealized_pnl_pct: float | None = None
    transactions: list[Transaction] = Field(default_factory=list)

    def update_current_price(self, price: float) -> None:
        self.current_price = price
        self.current_value = self.total_shares * price
        self.unrealized_pnl = self.current_value - self.total_invested
        if self.total_invested > 0:
            self.unrealized_pnl_pct = (self.unrealized_pnl / self.total_invested) * 100


class Portfolio(BaseModel):
    """User's complete portfolio."""

    positions: dict[str, Position] = Field(default_factory=dict)
    total_invested: float = 0.0
    total_current_value: float | None = None
    total_pnl: float | None = None
    total_pnl_pct: float | None = None
    last_updated: datetime = Field(default_factory=datetime.now)

    def add_transaction(self, txn: Transaction) -> None:
        if txn.symbol not in self.positions:
            self.positions[txn.symbol] = Position(
                symbol=txn.symbol,
                total_shares=0,
                avg_cost_basis=0,
                total_invested=0,
            )

        pos = self.positions[txn.symbol]

        if txn.action == "BUY":
            new_total_cost = pos.total_invested + txn.total_cost
            new_total_shares = pos.total_shares + txn.shares
            pos.avg_cost_basis = new_total_cost / new_total_shares if new_total_shares > 0 else 0
            pos.total_shares = new_total_shares
            pos.total_invested = new_total_cost
            self.total_invested += txn.total_cost
        elif txn.action == "SELL":
            pos.total_shares -= txn.shares
            sold_value = txn.shares * pos.avg_cost_basis
            pos.total_invested -= sold_value
            self.total_invested -= sold_value

        pos.transactions.append(txn)

        # Remove position if fully sold
        if pos.total_shares <= 0:
            del self.positions[txn.symbol]

    def recalculate_totals(self) -> None:
        if not self.positions:
            self.total_current_value = 0
            self.total_pnl = 0
            self.total_pnl_pct = 0
            return

        total_value = 0
        all_priced = True
        for pos in self.positions.values():
            if pos.current_value is not None:
                total_value += pos.current_value
            else:
                all_priced = False

        if all_priced:
            self.total_current_value = total_value
            self.total_pnl = total_value - self.total_invested
            if self.total_invested > 0:
                self.total_pnl_pct = (self.total_pnl / self.total_invested) * 100
