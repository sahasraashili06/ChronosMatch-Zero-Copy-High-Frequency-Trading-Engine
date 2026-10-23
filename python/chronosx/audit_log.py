"""
ChronosX -- Audit Log / Trade Blotter

Persists every trade fill, order event, and risk rejection to a
rotating CSV file on disk for post-trade analysis and compliance.

Writes three separate CSV files:
  - trades.csv    : every fill (aggressor_id, resting_id, price, qty, side, ts)
  - orders.csv    : every order submission with final status
  - rejects.csv   : every risk or validation rejection
"""
from __future__ import annotations

import csv
import os
import time
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Optional

from .types import (
    Side, OrderStatus, RiskResult, PRICE_MULT,
    TradeEvent, RejectEvent,
)


def _ts_iso() -> str:
    """Current time as ISO-8601 string."""
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + \
           f".{time.perf_counter_ns() % 1_000_000_000:09d}Z"


class AuditLog:
    """
    Append-only CSV trade blotter.

    Usage:
        log = AuditLog(output_dir="logs/")
        log.log_trade(trade, aggressor_side=Side.Buy)
        log.log_order(order_id=1, side=Side.Buy, price=100_000,
                      qty=50, status=OrderStatus.Filled)
        log.log_reject(order_id=2, reason=RiskResult.RejectedQty)
        log.close()
    """

    TRADE_HEADER  = ["ts", "aggressor_id", "resting_id", "price", "price_str",
                     "qty", "aggressor_side"]
    ORDER_HEADER  = ["ts", "order_id", "side", "price", "price_str",
                     "qty", "status"]
    REJECT_HEADER = ["ts", "order_id", "reason"]

    def __init__(self, output_dir: str = "logs") -> None:
        self._dir = Path(output_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

        self._trade_path  = self._dir / "trades.csv"
        self._order_path  = self._dir / "orders.csv"
        self._reject_path = self._dir / "rejects.csv"

        self._trade_f  = open(self._trade_path,  "a", newline="", encoding="utf-8")
        self._order_f  = open(self._order_path,  "a", newline="", encoding="utf-8")
        self._reject_f = open(self._reject_path, "a", newline="", encoding="utf-8")

        self._trade_w  = csv.writer(self._trade_f)
        self._order_w  = csv.writer(self._order_f)
        self._reject_w = csv.writer(self._reject_f)

        self._trade_count  = 0
        self._order_count  = 0
        self._reject_count = 0

        # Write headers only for new files
        if self._trade_path.stat().st_size == 0:
            self._trade_w.writerow(self.TRADE_HEADER)
        if self._order_path.stat().st_size == 0:
            self._order_w.writerow(self.ORDER_HEADER)
        if self._reject_path.stat().st_size == 0:
            self._reject_w.writerow(self.REJECT_HEADER)

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def trade_count(self) -> int:
        return self._trade_count

    @property
    def order_count(self) -> int:
        return self._order_count

    @property
    def reject_count(self) -> int:
        return self._reject_count

    @property
    def output_dir(self) -> Path:
        return self._dir

    # ── Logging API ───────────────────────────────────────────────────────────

    def log_trade(self, trade: TradeEvent, aggressor_side: Side) -> None:
        self._trade_w.writerow([
            _ts_iso(),
            trade.aggressor_id,
            trade.resting_id,
            trade.price,
            f"${trade.price / PRICE_MULT:.4f}",
            trade.qty,
            aggressor_side.name,
        ])
        self._trade_count += 1

    def log_order(
        self,
        order_id: int,
        side:     Side,
        price:    int,
        qty:      int,
        status:   OrderStatus,
    ) -> None:
        self._order_w.writerow([
            _ts_iso(),
            order_id,
            side.name,
            price,
            f"${price / PRICE_MULT:.4f}",
            qty,
            status.name,
        ])
        self._order_count += 1

    def log_reject(self, order_id: int, reason: RiskResult) -> None:
        self._reject_w.writerow([
            _ts_iso(),
            order_id,
            reason.name,
        ])
        self._reject_count += 1

    def flush(self) -> None:
        self._trade_f.flush()
        self._order_f.flush()
        self._reject_f.flush()

    def close(self) -> None:
        self.flush()
        self._trade_f.close()
        self._order_f.close()
        self._reject_f.close()

    def summary(self) -> str:
        return (
            f"AuditLog -> {self._dir}\n"
            f"  trades.csv  : {self._trade_count:,} rows\n"
            f"  orders.csv  : {self._order_count:,} rows\n"
            f"  rejects.csv : {self._reject_count:,} rows"
        )

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
