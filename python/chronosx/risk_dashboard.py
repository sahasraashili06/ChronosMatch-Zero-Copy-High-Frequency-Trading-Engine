"""
ChronosX -- Risk Dashboard

Aggregates all real-time risk signals into a single RiskStatus snapshot.
Acts as the single source of truth before any order is submitted.

Plugs together:
  - CircuitBreaker  (halt on volatility / loss / reject rate)
  - DrawdownTracker (equity peak-to-trough)
  - SpreadMonitor   (bid-ask spread z-score)
  - VpinEstimator   (order-flow toxicity)
  - KellySizer      (position sizing)

Usage:
    dash = RiskDashboard(capital=100_000.0)

    # feed on every tick / trade
    dash.on_price(101_500)
    dash.on_equity(99_200)
    dash.on_spread(book.spread())
    dash.on_trade(trade, Side.Buy)

    status = dash.status()
    if status.trading_allowed:
        size = status.recommended_size(ask_price)
        sor.route_buy(qty=size, quotes=quotes)
    else:
        print(f"HALTED: {status.halt_reason}")
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Optional

from .circuit_breaker import CircuitBreaker, BreakerConfig, BreakerState
from .drawdown import DrawdownTracker
from .spread_monitor import SpreadMonitor
from .vpin import VpinEstimator
from .kelly_sizer import KellySizer
from .types import Side, TradeEvent


class RiskLevel(IntEnum):
    GREEN  = 0   # all clear
    YELLOW = 1   # elevated risk, trade with caution
    RED    = 2   # halt trading


@dataclass
class RiskStatus:
    """Immutable snapshot of current risk state."""
    level:            RiskLevel
    trading_allowed:  bool
    halt_reason:      Optional[str]

    # Component readings
    drawdown_pct:     float
    max_drawdown_pct: float
    spread_z:         Optional[float]
    vpin:             float
    breaker_state:    BreakerState
    kelly_fraction:   Optional[float]

    # Alerts fired this snapshot
    active_alerts:    List[str] = field(default_factory=list)

    def recommended_size(self, price_fixed: int) -> int:
        """Kelly-recommended position size at given price. 0 if halted."""
        if not self.trading_allowed or self.kelly_fraction is None or price_fixed <= 0:
            return 0
        from .types import PRICE_MULT
        price_usd = price_fixed / PRICE_MULT
        from .kelly_sizer import KellySizer
        return max(0, int(0.0))   # placeholder resolved below

    def __str__(self) -> str:
        halted = "" if self.trading_allowed else f" | HALT: {self.halt_reason}"
        return (
            f"[{self.level.name}] "
            f"DD={self.drawdown_pct:.1f}%  "
            f"VPIN={self.vpin:.3f}  "
            f"SpreadZ={self.spread_z:.2f}" if self.spread_z else
            f"[{self.level.name}] "
            f"DD={self.drawdown_pct:.1f}%  VPIN={self.vpin:.3f}"
        ) + halted


class RiskDashboard:
    """
    Single aggregator for all ChronosX risk components.

    Args:
        capital          : Total trading capital in USD.
        max_drawdown_pct : Auto-halt if drawdown exceeds this %.
        max_vpin         : Auto-halt if VPIN exceeds this threshold.
        max_spread_z     : Caution if spread z-score exceeds this.
        breaker_cfg      : CircuitBreaker configuration (optional).
    """

    def __init__(
        self,
        capital:          float = 100_000.0,
        max_drawdown_pct: float = 10.0,
        max_vpin:         float = 0.7,
        max_spread_z:     float = 3.0,
        kelly_fraction:   float = 0.5,
        breaker_cfg:      Optional[BreakerConfig] = None,
    ) -> None:
        self._max_dd_pct   = max_drawdown_pct
        self._max_vpin     = max_vpin
        self._max_spread_z = max_spread_z
        self._capital      = capital

        self.breaker  = CircuitBreaker(breaker_cfg)
        self.drawdown = DrawdownTracker(initial_equity=capital,
                                        alert_pct=max_drawdown_pct)
        self.spread   = SpreadMonitor(z_threshold=max_spread_z)
        self.vpin     = VpinEstimator(bucket_size=500, window=10)
        self.kelly    = KellySizer(capital=capital, fraction=kelly_fraction,
                                   min_trades=10)

        self._halt_reason: Optional[str] = None
        self._manually_halted: bool = False

    # ── Feed methods ──────────────────────────────────────────────────────────

    def on_price(self, price: int) -> None:
        """Feed a new market price (fixed-point)."""
        self.breaker.on_price(price)

    def on_equity(self, equity: float) -> None:
        """Feed current equity in USD."""
        event = self.drawdown.update(equity)
        self.kelly.update_capital(equity)
        if event and abs(event.pct) >= self._max_dd_pct:
            self._halt_reason = f"Max drawdown {event.pct:.1f}%"
        self.breaker.on_pnl_update(
            realised=int((equity - self._capital) * 10_000), unrealised=0
        )

    def on_spread(self, spread: Optional[int]) -> None:
        """Feed current bid-ask spread (fixed-point)."""
        if spread and spread > 0:
            self.spread.update_raw(spread)

    def on_trade(self, trade: TradeEvent, aggressor: Side) -> None:
        """Feed a trade event for VPIN calculation."""
        self.vpin.on_trade(trade, aggressor)

    def on_trade_result(self, pnl: float) -> None:
        """Record completed trade P&L for Kelly sizing."""
        self.kelly.record_trade(pnl)
        self.breaker.on_order_result(pnl > 0)

    def halt(self, reason: str = "Manual halt") -> None:
        """Manually halt trading."""
        self._manually_halted = True
        self._halt_reason = reason

    def resume(self) -> None:
        """Manually resume trading and reset circuit breaker."""
        self._manually_halted = False
        self._halt_reason = None
        self.breaker.reset()

    # ── Status snapshot ───────────────────────────────────────────────────────

    def status(self) -> RiskStatus:
        """Build and return the current RiskStatus snapshot."""
        alerts: List[str] = []
        level = RiskLevel.GREEN
        halt_reason: Optional[str] = None

        # --- Circuit breaker ---
        breaker_open = self.breaker.is_open
        if breaker_open:
            level = RiskLevel.RED
            halt_reason = (self.breaker.events[-1].reason
                           if self.breaker.events else "Circuit breaker open")
            alerts.append(f"CircuitBreaker: {halt_reason}")

        # --- Drawdown ---
        dd_pct = self.drawdown.current_pct
        if abs(dd_pct) >= self._max_dd_pct:
            level = RiskLevel.RED
            halt_reason = halt_reason or f"Drawdown {dd_pct:.1f}%"
            alerts.append(f"Drawdown: {dd_pct:.1f}%")
        elif abs(dd_pct) >= self._max_dd_pct * 0.7:
            level = max(level, RiskLevel.YELLOW)
            alerts.append(f"Drawdown warning: {dd_pct:.1f}%")

        # --- VPIN ---
        vpin_val = self.vpin.current
        if vpin_val >= self._max_vpin:
            level = max(level, RiskLevel.YELLOW)
            alerts.append(f"VPIN elevated: {vpin_val:.3f}")

        # --- Spread ---
        sz = self.spread.z_score
        if sz is not None and sz > self._max_spread_z:
            level = max(level, RiskLevel.YELLOW)
            alerts.append(f"Spread wide: z={sz:.2f}")

        # --- Manual halt ---
        if self._manually_halted:
            level = RiskLevel.RED
            halt_reason = halt_reason or self._halt_reason

        trading_allowed = (
            level != RiskLevel.RED
            and not breaker_open
            and not self._manually_halted
        )

        return RiskStatus(
            level=level,
            trading_allowed=trading_allowed,
            halt_reason=halt_reason,
            drawdown_pct=dd_pct,
            max_drawdown_pct=self.drawdown.max_drawdown_pct,
            spread_z=sz,
            vpin=vpin_val,
            breaker_state=self.breaker.state,
            kelly_fraction=self.kelly.recommended_fraction(),
            active_alerts=alerts,
        )

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def is_green(self) -> bool:
        return self.status().level == RiskLevel.GREEN

    @property
    def is_halted(self) -> bool:
        return not self.status().trading_allowed

    def recommended_size(self, price_fixed: int) -> int:
        """Convenience wrapper for Kelly-based position size."""
        return self.kelly.position_size(price_fixed) or 0

    def __str__(self) -> str:
        return str(self.status())
