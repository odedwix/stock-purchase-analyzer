import csv
import io
import logging
from datetime import date, datetime

from src.models.portfolio import Portfolio, Transaction

logger = logging.getLogger(__name__)


class PortfolioService:
    """Manages portfolio and CSV import."""

    def __init__(self):
        self.portfolio = Portfolio()

    def import_csv(self, csv_content: str) -> tuple[int, list[str]]:
        """Import transactions from CSV content.

        Expected CSV columns: symbol, action, shares, price, date
        Optional columns: fees, notes

        Returns: (num_imported, list_of_errors)
        """
        errors = []
        imported = 0

        reader = csv.DictReader(io.StringIO(csv_content))

        # Normalize header names
        if reader.fieldnames is None:
            return 0, ["Empty CSV file"]

        fieldnames = {f.strip().lower(): f for f in reader.fieldnames}

        for row_num, row in enumerate(reader, start=2):
            try:
                # Normalize keys
                normalized = {k.strip().lower(): v.strip() for k, v in row.items()}

                symbol = normalized.get("symbol", normalized.get("ticker", ""))
                if not symbol:
                    errors.append(f"Row {row_num}: Missing symbol")
                    continue

                action = normalized.get("action", normalized.get("type", "BUY")).upper()
                if action not in ("BUY", "SELL"):
                    action = "BUY"

                shares_str = normalized.get("shares", normalized.get("quantity", "0"))
                shares = float(shares_str.replace(",", ""))

                price_str = normalized.get("price", normalized.get("price_per_share", "0"))
                price = float(price_str.replace("$", "").replace(",", ""))

                date_str = normalized.get("date", normalized.get("purchase_date", ""))
                txn_date = self._parse_date(date_str)

                fees_str = normalized.get("fees", normalized.get("commission", "0"))
                fees = float(fees_str.replace("$", "").replace(",", "")) if fees_str else 0

                notes = normalized.get("notes", "")

                txn = Transaction(
                    symbol=symbol.upper(),
                    action=action,
                    shares=shares,
                    price_per_share=price,
                    date=txn_date,
                    fees=fees,
                    notes=notes,
                )
                self.portfolio.add_transaction(txn)
                imported += 1

            except (ValueError, KeyError) as e:
                errors.append(f"Row {row_num}: {e}")

        return imported, errors

    def _parse_date(self, date_str: str) -> date:
        """Try multiple date formats."""
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%m-%d-%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        raise ValueError(f"Could not parse date: {date_str}")

    def get_portfolio(self) -> Portfolio:
        return self.portfolio
