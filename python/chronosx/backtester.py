"""
ChronosX -- Strategy Backtester

Runs a trading strategy over a sequence of ReplayEvents and computes
full performance metrics: P&L, Sharpe ratio, max drawdown, win rate.

Architecture:
    BacktestEngine
        ├── replays events in timestamp order
        ├── calls strategy.on_event(event, book) → List[OrderRequest]
        ├── submits returned orders through the OMS
        ├── tracks fills via PositionManager
        └── computes BacktestResult at the end

Usage:
    class MomentumStrategy(Strategy):
        def on_event(self, event, book, position):
            if book.best_bid() and book.best_ask():
                ...
            return []

    result = BacktestEngine(strategy=MomentumStrategy()).run(events)
    print(result.summary())
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional

from .types import Side, OrderType, OrderStatus, TradeEvent, PRICE_MULT
from .oms import OrderManagementSystem, OrderRequest, OmsResponse
from .risk_engine import RiskEngine, RiskLimits
from .position_manager import PositionManager, Position
from .order_book import OrderBook
from .replay import ReplayEvent


# ── Strategy interface ────────────────────────────────────────────────────────

class Strategy(ABC):
    """
    Abstract base class for backtest strategies.

    Implement on_event() to return orders you want to submit
    in response to each incoming market event.
    """

    @abstractmethod
    def on_event(
        self,
        event:    ReplayEvent,
        book:     OrderBook,
        position: Optional[Position],
    ) -> List[OrderRequest]:
        """
        Called for every replay event.
        Return a list of OrderRequests to submit (can be empty).
        """
        ...

    def on_trade(self, trade: TradeEvent, side: Side) -> None:
        """Called when one of your orders is filled. Override optionally."""
        pass

    def on_session_end(self) -> None:
        """Called after all events are processed. Override optionally."""
        pass


# ── Built-in simple strategies ────────────────────────────────────────────────

class PassiveStrategy(Strategy):
    """Always posts a limit bid 1 tick below best bid and ask 1 tick above."""

    def __init__(self, qty: int = 10, tick: int = 100, next_id: int = 10_000):
        self._qty     = qty
        self._tick    = tick
        self._next_id = next_id

    def on_event(self, event, book, position):
        bb = book.best_bid()
        ba = book.best_ask()
        if bb is None or ba is None:
            return []
        orders = [
            OrderRequest(self._next_id,     Side.Buy,  OrderType.Limit, bb - self._tick, self._qty),
            OrderRequest(self._next_id + 1, Side.Sell, OrderType.Limit, ba + self._tick, self._qty),
        ]
        self._next_id += 2
        return orders


# ── Backtest result ───────────────────────────────────────────────────────────

@dataclass
class BacktestResult:
    """Full performance report for one backtest run."""
    strategy_name:   str
    total_events:    int
    orders_sent:     int
    orders_filled:   int
    trade_count:     int
    total_volume:    int
    realised_pnl:    int        # fixed-point
    unrealised_pnl:  int        # fixed-point (mark-to-market at end)
    pnl_series:      List[int]  # cumulative P&L after each trade (fixed-point)
    win_trades:      int
    loss_trades:     int

    @property
    def total_pnl(self) -> int:
        return self.realised_pnl + self.unrealised_pnl

    @property
    def total_pnl_usd(self) -> float:
        return self.total_pnl / PRICE_MULT

    @property
    def fill_rate(self) -> float:
        return self.orders_filled / self.orders_sent if self.orders_sent else 0.0

    @property
    def win_rate(self) -> float:
        total = self.win_trades + self.loss_trades
        return self.win_trades / total if total else 0.0

    @property
    def sharpe(self) -> float:
        """Simplified Sharpe: mean(pnl_deltas) / std(pnl_deltas)."""
        if len(self.pnl_series) < 2:
            return 0.0
        deltas = [self.pnl_series[i] - self.pnl_series[i - 1]
                  for i in range(1, len(self.pnl_series))]
        mean = sum(deltas) / len(deltas)
        var  = sum((d - mean) ** 2 for d in deltas) / len(deltas)
        std  = math.sqrt(var)
        return mean / std if std > 0 else 0.0

    @property
    def max_drawdown(self) -> float:
        """Max peak-to-trough decline in USD."""
        if not self.pnl_series:
            return 0.0
        peak = self.pnl_series[0]
        max_dd = 0
        for v in self.pnl_series:
            peak  = max(peak, v)
            max_dd = max(max_dd, peak - v)
        return max_dd / PRICE_MULT

    def summary(self) -> str:
        return (
            f"\n{'='*50}\n"
            f"  Backtest: {self.strategy_name}\n"
            f"{'='*50}\n"
            f"  Events      : {self.total_events:,}\n"
            f"  Orders sent : {self.orders_sent:,}  filled={self.orders_filled:,}  "
            f"fill_rate={self.fill_rate:.1%}\n"
            f"  Trades      : {self.trade_count:,}  volume={self.total_volume:,}\n"
            f"  Win rate    : {self.win_rate:.1%}  "
            f"(W={self.win_trades} / L={self.loss_trades})\n"
            f"  Realised P&L: ${self.realised_pnl / PRICE_MULT:+.4f}\n"
            f"  Total P&L   : ${self.total_pnl_usd:+.4f}\n"
            f"  Sharpe      : {self.sharpe:.3f}\n"
            f"  Max Drawdown: ${self.max_drawdown:.4f}\n"
        )


# ── Engine ────────────────────────────────────────────────────────────────────

class BacktestEngine:
    """
    Replays events through a strategy and collects performance metrics.

    Args:
        strategy: Your Strategy subclass instance.
        risk:     Optional custom RiskLimits.
    """

    def __init__(
        self,
        strategy: Strategy,
        risk:     Optional[RiskEngine] = None,
    ) -> None:
        self._strategy = strategy
        limits = RiskLimits(max_order_qty=1_000_000, max_order_notional=10 ** 18)
        self._oms     = OrderManagementSystem(risk or RiskEngine(limits))
        self._pm      = PositionManager()

    def run(self, events: List[ReplayEvent]) -> BacktestResult:
        """Replay all events, return BacktestResult."""
        orders_sent    = 0
        orders_filled  = 0
        trade_count    = 0
        total_volume   = 0
        win_trades     = 0
        loss_trades    = 0
        pnl_series:    List[int] = []
        last_trade_pnl: int = 0

        for ev in events:
            # 1. Feed the market event into the OMS book
            self._oms.submit(OrderRequest(
                id    = ev.order_id,
                side  = ev.side,
                type  = ev.type,
                price = ev.price,
                qty   = ev.qty,
            ))

            # 2. Ask the strategy for orders
            pos = self._pm.get_position(1)   # strategy trades as participant 1
            strat_orders = self._strategy.on_event(ev, self._oms.book, pos)

            # 3. Submit strategy orders
            for req in strat_orders:
                resp = self._oms.submit(req)
                mr   = resp.match_result
                orders_sent += 1

                if mr.final_status in (OrderStatus.Filled, OrderStatus.PartiallyFilled):
                    orders_filled += 1

                for trade in mr.trades:
                    self._pm.record_trade(trade, ev.side)
                    self._strategy.on_trade(trade, ev.side)
                    trade_count  += 1
                    total_volume += trade.qty

                    # Win/loss per trade
                    cur_pnl = self._pm.get_position(1)
                    if cur_pnl:
                        delta = cur_pnl.realised_pnl - last_trade_pnl
                        if delta > 0:
                            win_trades += 1
                        elif delta < 0:
                            loss_trades += 1
                        last_trade_pnl = cur_pnl.realised_pnl
                        pnl_series.append(cur_pnl.realised_pnl)

        self._strategy.on_session_end()

        final_pos = self._pm.get_position(1)
        realised   = final_pos.realised_pnl if final_pos else 0
        unrealised = 0
        if final_pos and final_pos.net_qty != 0:
            mark = self._oms.book.best_bid() or self._oms.book.best_ask() or 0
            unrealised = int((mark - final_pos.avg_entry) * final_pos.net_qty)

        return BacktestResult(
            strategy_name  = type(self._strategy).__name__,
            total_events   = len(events),
            orders_sent    = orders_sent,
            orders_filled  = orders_filled,
            trade_count    = trade_count,
            total_volume   = total_volume,
            realised_pnl   = realised,
            unrealised_pnl = unrealised,
            pnl_series     = pnl_series,
            win_trades     = win_trades,
            loss_trades    = loss_trades,
        )
