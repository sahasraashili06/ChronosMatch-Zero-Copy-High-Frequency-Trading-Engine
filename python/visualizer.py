#!/usr/bin/env python3
"""
ChronosX -- Live Order Book Visualizer

Prints a colour-coded order book depth table to the terminal.
Requires: pip install rich
Falls back to plain text if rich is not installed.
"""
from __future__ import annotations
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from typing import List, Optional

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich.columns import Columns
    from rich import box
    _HAS_RICH = True
except ImportError:
    _HAS_RICH = False

from chronosx.market_data import BookSnapshot, TradeReport, PriceLevelSnapshot
from chronosx.types import PRICE_MULT


# ── Plain text fallback ───────────────────────────────────────────────────────

def _plain_book(snap: BookSnapshot, last_trades: List[TradeReport]) -> None:
    print(f"\n  Order Book  [{snap.instrument_id}]  seq={snap.seq}")
    print(f"  {'ASK':>10}  {'Qty':>8}  {'Orders':>6}")
    print(f"  {'-'*10}  {'-'*8}  {'-'*6}")
    for lvl in reversed(snap.asks[:5]):
        print(f"  {lvl.price_str():>10}  {lvl.qty:>8,}  {lvl.count:>6}")
    if snap.spread is not None:
        print(f"  -- spread: {snap.spread_str()} --")
    for lvl in snap.bids[:5]:
        print(f"  {lvl.price_str():>10}  {lvl.qty:>8,}  {lvl.count:>6}")
    print(f"  {'BID':>10}  {'Qty':>8}  {'Orders':>6}")
    if last_trades:
        print("\n  Last Trades:")
        for t in last_trades[-3:]:
            side_str = "BUY " if t.aggressor_side.name == "Buy" else "SELL"
            print(f"    {side_str} {t.qty:>6} @ {t.price_str()}")


# ── Rich renderer ─────────────────────────────────────────────────────────────

def _rich_book(snap: BookSnapshot, last_trades: List[TradeReport]) -> None:
    console = Console()

    # ── Ask side (top) ────────────────────────────────────────────────────────
    ask_table = Table(box=box.SIMPLE, show_header=True, header_style="bold red")
    ask_table.add_column("Price",  style="red",   justify="right", min_width=12)
    ask_table.add_column("Qty",    style="white",  justify="right", min_width=8)
    ask_table.add_column("Orders", style="dim",    justify="right", min_width=6)

    for lvl in reversed(snap.asks[:8]):
        ask_table.add_row(lvl.price_str(), f"{lvl.qty:,}", str(lvl.count))

    # ── Spread row ────────────────────────────────────────────────────────────
    spread_txt = Text(f"  -- Spread: {snap.spread_str()} --", style="bold yellow")

    # ── Bid side (bottom) ─────────────────────────────────────────────────────
    bid_table = Table(box=box.SIMPLE, show_header=True, header_style="bold green")
    bid_table.add_column("Price",  style="green", justify="right", min_width=12)
    bid_table.add_column("Qty",    style="white", justify="right", min_width=8)
    bid_table.add_column("Orders", style="dim",   justify="right", min_width=6)

    for lvl in snap.bids[:8]:
        bid_table.add_row(lvl.price_str(), f"{lvl.qty:,}", str(lvl.count))

    # ── Trade tape ────────────────────────────────────────────────────────────
    tape = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
    tape.add_column("Side",  min_width=5)
    tape.add_column("Qty",   justify="right", min_width=6)
    tape.add_column("Price", justify="right", min_width=12)

    for t in reversed(last_trades[-8:]):
        side  = t.aggressor_side.name
        color = "green" if side == "Buy" else "red"
        tape.add_row(
            Text(side, style=f"bold {color}"),
            f"{t.qty:,}",
            t.price_str(),
        )

    title = f"[bold white]ChronosX Order Book[/bold white]  " \
            f"[dim]{snap.instrument_id}[/dim]  seq=[cyan]{snap.seq}[/cyan]"

    console.print()
    console.print(Panel(title, expand=False))
    console.print(ask_table)
    console.print(spread_txt)
    console.print(bid_table)

    if last_trades:
        console.print()
        console.print(Panel("[bold cyan]Trade Tape[/bold cyan]", expand=False))
        console.print(tape)


# ── Public entry point ────────────────────────────────────────────────────────

def render_book(snap: BookSnapshot, last_trades: Optional[List[TradeReport]] = None) -> None:
    """Render the order book snapshot to stdout."""
    trades = last_trades or []
    if _HAS_RICH:
        _rich_book(snap, trades)
    else:
        _plain_book(snap, trades)
