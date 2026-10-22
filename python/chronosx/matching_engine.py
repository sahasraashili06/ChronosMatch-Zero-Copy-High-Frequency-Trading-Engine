"""
ChronosX — MatchingEngine

Core price-time priority (FIFO) matching engine.

Matching rules:
- Limit orders: rest in book if no crossing order; otherwise match greedily.
- Market orders: IOC — fill as much as possible, cancel residual immediately.
- Execution price = resting order price (maker price).
- FIFO within a price level.
"""
from __future__ import annotations

from .types import (
    Side, OrderType, OrderStatus,
    TradeEvent, CancelEvent, RejectEvent, MatchResult, INVALID_ORDER_ID
)
from .order import Order, NULL_IDX
from .memory_pool import ObjectPool
from .order_book import OrderBook

DEFAULT_POOL_CAPACITY = 65_536


class MatchingEngine:
    """
    Single-instrument limit order book with price-time priority matching.

    >>> engine = MatchingEngine()
    >>> r = engine.submit_limit(1, Side.Sell, 100_000, 50)
    >>> r.final_status.name
    'New'
    >>> r = engine.submit_limit(2, Side.Buy, 100_000, 50)
    >>> r.final_status.name
    'Filled'
    >>> len(r.trades)
    1
    """

    def __init__(self, capacity: int = DEFAULT_POOL_CAPACITY) -> None:
        self._pool     = ObjectPool(capacity)
        self._book     = OrderBook(self._pool)
        self._seq: int = 0

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def book(self) -> OrderBook:
        return self._book

    @property
    def seq_counter(self) -> int:
        return self._seq

    def submit_limit(
        self,
        order_id: int,
        side:     Side,
        price:    int,
        qty:      int,
    ) -> MatchResult:
        alloc = self._pool.alloc()
        if alloc is None:
            result = MatchResult(final_status=OrderStatus.Rejected)
            result.reject_event = RejectEvent(order_id=order_id)
            return result

        self._seq += 1
        idx, order = alloc
        order.order_id      = order_id
        order.price         = price
        order.initial_qty   = qty
        order.remaining_qty = qty
        order.seq_num       = self._seq
        order.side          = side
        order.type          = OrderType.Limit
        order.status        = OrderStatus.New
        order.prev_idx      = NULL_IDX
        order.next_idx      = NULL_IDX

        result = MatchResult()
        self._match_against_book(idx, result)

        if order.remaining_qty > 0:
            # Residual rests in the book
            self._book.add_order(idx)
            result.final_status = order.status
        else:
            order.status = OrderStatus.Filled
            result.final_status = OrderStatus.Filled
            self._pool.free(idx)

        return result

    def submit_market(
        self,
        order_id: int,
        side:     Side,
        qty:      int,
    ) -> MatchResult:
        alloc = self._pool.alloc()
        if alloc is None:
            result = MatchResult(final_status=OrderStatus.Rejected)
            result.reject_event = RejectEvent(order_id=order_id)
            return result

        self._seq += 1
        idx, order = alloc
        order.order_id      = order_id
        order.price         = 0          # market — match at any price
        order.initial_qty   = qty
        order.remaining_qty = qty
        order.seq_num       = self._seq
        order.side          = side
        order.type          = OrderType.Market
        order.status        = OrderStatus.New
        order.prev_idx      = NULL_IDX
        order.next_idx      = NULL_IDX

        result = MatchResult()
        self._match_against_book(idx, result)

        # IOC: cancel any unfilled residual
        if order.remaining_qty > 0:
            result.cancel_event = CancelEvent(
                order_id=order_id,
                remaining_qty=order.remaining_qty,
            )
            if result.trades:
                order.status = OrderStatus.PartiallyFilled
                result.final_status = OrderStatus.PartiallyFilled
            else:
                order.status = OrderStatus.Cancelled
                result.final_status = OrderStatus.Cancelled
        else:
            order.status = OrderStatus.Filled
            result.final_status = OrderStatus.Filled

        self._pool.free(idx)
        return result

    def cancel_order(self, order_id: int) -> MatchResult:
        result = MatchResult()
        idx = self._book.find_order_idx(order_id)
        if idx == NULL_IDX:
            result.reject_event = RejectEvent(order_id=order_id)
            result.final_status = OrderStatus.Rejected
            return result

        order = self._pool.at(idx)
        remaining = order.remaining_qty
        self._book.cancel_order(order_id)
        order.status = OrderStatus.Cancelled
        self._pool.free(idx)

        result.cancel_event = CancelEvent(
            order_id=order_id,
            remaining_qty=remaining,
        )
        result.final_status = OrderStatus.Cancelled
        return result

    # ── Internal matching logic ───────────────────────────────────────────────

    def _match_against_book(self, aggressor_idx: int, result: MatchResult) -> None:
        aggressor = self._pool.at(aggressor_idx)
        is_buy    = aggressor.side == Side.Buy

        while aggressor.remaining_qty > 0:
            # Find the best resting counterparty
            if is_buy:
                resting_price = self._book.best_ask()
                if resting_price is None:
                    break
                # Limit order: only match if aggressor price >= best ask
                if (aggressor.type == OrderType.Limit and
                        aggressor.price < resting_price):
                    break
                resting_idx = self._book.front_ask_idx()
            else:
                resting_price = self._book.best_bid()
                if resting_price is None:
                    break
                if (aggressor.type == OrderType.Limit and
                        aggressor.price > resting_price):
                    break
                resting_idx = self._book.front_bid_idx()

            if resting_idx == NULL_IDX:
                break

            resting  = self._pool.at(resting_idx)
            fill_qty = min(aggressor.remaining_qty, resting.remaining_qty)

            trade = TradeEvent(
                aggressor_id=aggressor.order_id,
                resting_id=resting.order_id,
                price=resting_price,
                qty=fill_qty,
            )
            result.trades.append(trade)

            aggressor.remaining_qty -= fill_qty
            resting.remaining_qty   -= fill_qty

            if aggressor.remaining_qty > 0:
                aggressor.status = OrderStatus.PartiallyFilled

            if resting.remaining_qty == 0:
                # Resting order fully consumed — remove from book
                resting.status = OrderStatus.Filled
                resting_id_copy = resting.order_id
                self._book.remove_front(resting_price,
                    Side.Sell if is_buy else Side.Buy)
                self._pool.free(resting_idx)
            else:
                # Resting partially filled — reduce level qty
                resting.status = OrderStatus.PartiallyFilled
                self._book.reduce_front_qty(
                    resting_price,
                    Side.Sell if is_buy else Side.Buy,
                    fill_qty,
                )
