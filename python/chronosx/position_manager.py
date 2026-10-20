"""
ChronosX -- Position & P&L Manager

Tracks filled positions, realised/unrealised P&L, and exposure
for each participant as trades execute.

Key concepts:
- Net position = sum of all fills (buy = +qty, sell = -qty)
- Avg entry price = VWAP of open position
- Realised P&L  = closed portion × (exit price - entry price)
- Unrealised P&L = open qty × (mark price - avg entry price)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from .types import Side, TradeEvent, PRICE_MULT


@dataclass
class Fill:
    """Single fill record."""
    order_id:  int
    price:     int
    qty:       int
    side:      Side

    def notional(self) -> int:
        return self.price * self.qty


@dataclass
class Position:
    """Running position state for one participant."""
    participant_id: int
    net_qty:        int   = 0      # +ve = long, -ve = short
    avg_entry:      float = 0.0   # average entry price (float for accuracy)
    realised_pnl:   int   = 0     # in ticks × qty
    fills:          List[Fill] = field(default_factory=list)

    # ── Queries ───────────────────────────────────────────────────────────────

    def unrealised_pnl(self, mark_price: int) -> float:
        """P&L of the current open position at mark_price."""
        return self.net_qty * (mark_price - self.avg_entry)

    def total_pnl(self, mark_price: int) -> float:
        return self.realised_pnl + self.unrealised_pnl(mark_price)

    def is_flat(self) -> bool:
        return self.net_qty == 0

    def side(self) -> Optional[Side]:
        if self.net_qty > 0:
            return Side.Buy
        if self.net_qty < 0:
            return Side.Sell
        return None

    def exposure(self) -> int:
        """Absolute notional exposure in ticks."""
        return abs(self.net_qty) * int(self.avg_entry)

    def summary(self, mark_price: int) -> str:
        upnl = self.unrealised_pnl(mark_price)
        rpnl = self.realised_pnl
        return (
            f"Participant {self.participant_id:>4} | "
            f"NetQty={self.net_qty:>+7} | "
            f"AvgEntry=${self.avg_entry / PRICE_MULT:.4f} | "
            f"Realised=${rpnl / PRICE_MULT:.4f} | "
            f"Unrealised=${upnl / PRICE_MULT:.4f}"
        )

    # ── Mutation ──────────────────────────────────────────────────────────────

    def apply_fill(self, fill: Fill) -> None:
        """Update position state with a new fill."""
        self.fills.append(fill)
        signed_qty = fill.qty if fill.side == Side.Buy else -fill.qty

        if self.net_qty == 0:
            # Opening a new position
            self.avg_entry = float(fill.price)
            self.net_qty   = signed_qty

        elif (self.net_qty > 0 and signed_qty > 0) or \
             (self.net_qty < 0 and signed_qty < 0):
            # Adding to existing position — update VWAP
            total_cost     = self.avg_entry * abs(self.net_qty) + fill.price * fill.qty
            self.net_qty  += signed_qty
            self.avg_entry = total_cost / abs(self.net_qty)

        else:
            # Reducing or flipping position — realise P&L
            close_qty = min(fill.qty, abs(self.net_qty))
            if self.net_qty > 0:
                # Was long, selling
                self.realised_pnl += int(close_qty * (fill.price - self.avg_entry))
            else:
                # Was short, buying
                self.realised_pnl += int(close_qty * (self.avg_entry - fill.price))

            remainder = fill.qty - close_qty
            self.net_qty += signed_qty

            if remainder > 0 and self.net_qty != 0:
                # Flipped side — reset avg entry
                self.avg_entry = float(fill.price)
            elif self.net_qty == 0:
                self.avg_entry = 0.0


class PositionManager:
    """
    Maintains a position record for every participant that has traded.

    Usage:
        pm = PositionManager()

        # After a match result:
        for trade in result.trades:
            pm.record_trade(trade, aggressor_side=Side.Buy)

        # Query position:
        pos = pm.get_position(participant_id=42)
        print(pos.summary(mark_price=100_000))
    """

    def __init__(self) -> None:
        self._positions: Dict[int, Position] = {}
        self._all_trades: List[TradeEvent]   = []
        self._trade_count: int = 0
        self._total_volume: int = 0

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def trade_count(self) -> int:
        return self._trade_count

    @property
    def total_volume(self) -> int:
        return self._total_volume

    @property
    def participant_count(self) -> int:
        return len(self._positions)

    # ── Core API ──────────────────────────────────────────────────────────────

    def record_trade(self, trade: TradeEvent, aggressor_side: Side) -> None:
        """Record a trade, updating both aggressor and resting positions."""
        self._all_trades.append(trade)
        self._trade_count += 1
        self._total_volume += trade.qty

        resting_side = Side.Sell if aggressor_side == Side.Buy else Side.Buy

        # Aggressor fill
        self._apply(trade.aggressor_id, Fill(
            order_id=trade.aggressor_id,
            price=trade.price,
            qty=trade.qty,
            side=aggressor_side,
        ))
        # Resting fill
        self._apply(trade.resting_id, Fill(
            order_id=trade.resting_id,
            price=trade.price,
            qty=trade.qty,
            side=resting_side,
        ))

    def get_position(self, participant_id: int) -> Optional[Position]:
        return self._positions.get(participant_id)

    def all_positions(self) -> List[Position]:
        return list(self._positions.values())

    def vwap(self) -> Optional[float]:
        """Volume-weighted average price of all trades."""
        total_notional = sum(t.price * t.qty for t in self._all_trades)
        if self._total_volume == 0:
            return None
        return total_notional / self._total_volume

    def vwap_str(self) -> str:
        v = self.vwap()
        return f"${v / PRICE_MULT:.4f}" if v is not None else "N/A"

    def print_summary(self, mark_price: int) -> None:
        print("\n=== Position & P&L Summary ===")
        print(f"  Trades executed : {self._trade_count}")
        print(f"  Total volume    : {self._total_volume:,}")
        print(f"  Session VWAP    : {self.vwap_str()}")
        print(f"  Mark price      : ${mark_price / PRICE_MULT:.4f}")
        print()
        for pos in sorted(self.all_positions(), key=lambda p: p.participant_id):
            print(f"  {pos.summary(mark_price)}")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _apply(self, participant_id: int, fill: Fill) -> None:
        if participant_id not in self._positions:
            self._positions[participant_id] = Position(participant_id)
        self._positions[participant_id].apply_fill(fill)
