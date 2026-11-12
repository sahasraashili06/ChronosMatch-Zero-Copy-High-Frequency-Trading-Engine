"""
ChronosX -- Position Ledger

Tracks open positions and realised P&L per symbol in real time.

For each symbol it maintains:
  - Net position (long = positive, short = negative)
  - Average entry price (FIFO cost basis)
  - Unrealised P&L at current mark price
  - Realised P&L from closed trades

Usage:
    ledger = PositionLedger()

    ledger.fill("AAPL", qty=+100, price=150_000)   # buy 100 @ $15.00
    ledger.fill("AAPL", qty=-60,  price=155_000)   # sell 60 @ $15.50

    pos = ledger.position("AAPL")
    print(pos.realised_pnl_usd)   # $30.00
    print(pos.net_qty)            # 40 long
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .types import PRICE_MULT


@dataclass
class Position:
    """Live position for one symbol."""
    symbol:        str
    net_qty:       int   = 0      # positive = long, negative = short
    avg_price:     int   = 0      # fixed-point cost basis
    realised_pnl:  int   = 0      # fixed-point
    fill_count:    int   = 0

    @property
    def is_flat(self) -> bool:
        return self.net_qty == 0

    @property
    def is_long(self) -> bool:
        return self.net_qty > 0

    @property
    def is_short(self) -> bool:
        return self.net_qty < 0

    @property
    def realised_pnl_usd(self) -> float:
        return self.realised_pnl / PRICE_MULT

    def unrealised_pnl(self, mark_price: int) -> int:
        """Unrealised P&L in fixed-point at the given mark price."""
        return self.net_qty * (mark_price - self.avg_price)

    def unrealised_pnl_usd(self, mark_price: int) -> float:
        return self.unrealised_pnl(mark_price) / PRICE_MULT

    def market_value(self, mark_price: int) -> float:
        """Absolute market value of position in USD."""
        return abs(self.net_qty) * mark_price / PRICE_MULT

    def __str__(self) -> str:
        side = "LONG" if self.is_long else ("SHORT" if self.is_short else "FLAT")
        return (
            f"Position[{self.symbol}]  {side}  "
            f"qty={self.net_qty}  "
            f"avg=${self.avg_price/PRICE_MULT:.4f}  "
            f"realised=${self.realised_pnl_usd:.2f}"
        )


class PositionLedger:
    """
    Multi-symbol position tracker with FIFO cost basis.

    Usage:
        ledger = PositionLedger()
        ledger.fill("AAPL", qty=+100, price=150_000)
        ledger.fill("AAPL", qty=-100, price=155_000)
        print(ledger.total_realised_pnl_usd)   # $50.00
    """

    def __init__(self) -> None:
        self._positions: Dict[str, Position] = {}
        self._fill_log:  List[dict] = []

    # ---- Feed ----------------------------------------------------------------

    def fill(self, symbol: str, qty: int, price: int) -> Position:
        """
        Record a fill.

        Args:
            symbol : instrument identifier (e.g. "AAPL")
            qty    : signed quantity (+buy / -sell)
            price  : fill price in fixed-point
        """
        if symbol not in self._positions:
            self._positions[symbol] = Position(symbol=symbol)

        pos = self._positions[symbol]
        self._fill_log.append({"symbol": symbol, "qty": qty, "price": price})
        pos.fill_count += 1

        # Same-direction fill → update average price
        if pos.net_qty == 0 or (pos.net_qty > 0) == (qty > 0):
            total_cost  = pos.net_qty * pos.avg_price + qty * price
            pos.net_qty += qty
            pos.avg_price = total_cost // pos.net_qty if pos.net_qty else 0

        # Opposite direction → realise P&L on the closing portion
        else:
            closing_qty = min(abs(qty), abs(pos.net_qty))
            pnl_per_unit = (price - pos.avg_price) * (1 if pos.is_long else -1)
            pos.realised_pnl += closing_qty * pnl_per_unit

            remaining_close = abs(qty) - closing_qty
            pos.net_qty += qty

            # If we flipped sides, reset avg price to the new fill
            if pos.net_qty != 0 and remaining_close > 0:
                pos.avg_price = price
            elif pos.net_qty == 0:
                pos.avg_price = 0

        return pos

    # ---- Queries -------------------------------------------------------------

    def position(self, symbol: str) -> Optional[Position]:
        """Return position for a symbol, or None if never traded."""
        return self._positions.get(symbol)

    def positions(self) -> Dict[str, Position]:
        return dict(self._positions)

    def open_positions(self) -> Dict[str, Position]:
        return {s: p for s, p in self._positions.items() if not p.is_flat}

    @property
    def symbol_count(self) -> int:
        return len(self._positions)

    @property
    def total_realised_pnl(self) -> int:
        return sum(p.realised_pnl for p in self._positions.values())

    @property
    def total_realised_pnl_usd(self) -> float:
        return self.total_realised_pnl / PRICE_MULT

    def total_unrealised_pnl_usd(self, marks: Dict[str, int]) -> float:
        """
        Compute total unrealised P&L across all open positions.

        Args:
            marks: {symbol: mark_price_fixed_point}
        """
        total = 0.0
        for sym, pos in self._positions.items():
            if not pos.is_flat and sym in marks:
                total += pos.unrealised_pnl_usd(marks[sym])
        return total

    def total_market_value(self, marks: Dict[str, int]) -> float:
        total = 0.0
        for sym, pos in self._positions.items():
            if sym in marks:
                total += pos.market_value(marks[sym])
        return total

    def reset(self, symbol: Optional[str] = None) -> None:
        if symbol:
            self._positions.pop(symbol, None)
        else:
            self._positions.clear()
            self._fill_log.clear()

    def __str__(self) -> str:
        lines = [str(p) for p in self._positions.values()]
        lines.append(f"Total realised P&L: ${self.total_realised_pnl_usd:.2f}")
        return "\n".join(lines)
