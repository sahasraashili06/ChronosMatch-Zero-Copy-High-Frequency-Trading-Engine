"""
ChronosX — OrderManagementSystem (OMS)

Sits above the MatchingEngine and RiskEngine.
Assigns sequence IDs, runs pre-trade risk checks, and tracks live orders.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional
from .types import (
    Side, OrderType, OrderStatus, RiskResult,
    RejectEvent, MatchResult,
)
from .risk_engine import RiskEngine, RiskLimits
from .matching_engine import MatchingEngine


@dataclass
class OrderRequest:
    """Inbound order request from a client."""
    id:    int       = 0
    side:  Side      = Side.Buy
    type:  OrderType = OrderType.Limit
    price: int       = 0
    qty:   int       = 0


@dataclass
class OmsResponse:
    """Full lifecycle outcome returned to the client."""
    order_id:     int
    match_result: MatchResult
    risk_result:  RiskResult = RiskResult.Approved


class OrderManagementSystem:
    """
    Full-stack order lifecycle manager.

    >>> risk = RiskEngine()
    >>> oms  = OrderManagementSystem(risk)
    >>> req  = OrderRequest(id=1, side=Side.Buy, type=OrderType.Limit, price=100_000, qty=10)
    >>> resp = oms.submit(req)
    >>> resp.match_result.final_status.name
    'New'
    """

    def __init__(self, risk: RiskEngine) -> None:
        self._risk    = risk
        self._engine  = MatchingEngine()
        self._seq:    int = 0
        self._orders: Dict[int, OrderStatus] = {}

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def order_count(self) -> int:
        return len(self._orders)

    @property
    def book(self):  # -> OrderBook
        return self._engine.book

    # ── Public API ────────────────────────────────────────────────────────────

    def submit(self, req: OrderRequest) -> OmsResponse:
        # 1. Pre-trade risk check
        risk_result = self._risk.check_order(req.side, req.price, req.qty)
        if risk_result != RiskResult.Approved:
            mr = MatchResult(final_status=OrderStatus.Rejected)
            mr.reject_event = RejectEvent(
                order_id=req.id, reason=risk_result
            )
            return OmsResponse(
                order_id=req.id,
                match_result=mr,
                risk_result=risk_result,
            )

        # 2. Validate
        if req.qty <= 0:
            mr = MatchResult(final_status=OrderStatus.Rejected)
            mr.reject_event = RejectEvent(order_id=req.id)
            return OmsResponse(order_id=req.id, match_result=mr,
                               risk_result=RiskResult.RejectedQty)

        # 3. Route to matching engine
        self._seq += 1
        if req.type == OrderType.Market:
            mr = self._engine.submit_market(req.id, req.side, req.qty)
        else:
            mr = self._engine.submit_limit(req.id, req.side, req.price, req.qty)

        self._orders[req.id] = mr.final_status
        return OmsResponse(order_id=req.id, match_result=mr)

    def cancel(self, order_id: int) -> OmsResponse:
        mr = self._engine.cancel_order(order_id)
        if order_id in self._orders:
            self._orders[order_id] = mr.final_status
        return OmsResponse(order_id=order_id, match_result=mr)
