"""Tests for PositionLedger."""
import pytest
from chronosx.position_ledger import PositionLedger, Position
from chronosx.types import PRICE_MULT


@pytest.fixture
def ledger():
    return PositionLedger()


# ---- Basic fills ------------------------------------------------------------

def test_buy_creates_long_position(ledger):
    pos = ledger.fill("AAPL", qty=100, price=150_000)
    assert pos.net_qty == 100
    assert pos.is_long is True
    assert pos.avg_price == 150_000


def test_sell_creates_short_position(ledger):
    pos = ledger.fill("AAPL", qty=-50, price=150_000)
    assert pos.net_qty == -50
    assert pos.is_short is True


def test_same_direction_updates_avg_price(ledger):
    ledger.fill("AAPL", qty=100, price=100_000)   # $10.00
    pos = ledger.fill("AAPL", qty=100, price=120_000)  # $12.00
    assert pos.avg_price == 110_000   # avg = $11.00
    assert pos.net_qty == 200


# ---- Realised P&L -----------------------------------------------------------

def test_close_long_realises_profit(ledger):
    ledger.fill("AAPL", qty=100, price=100_000)   # buy @ $10
    pos = ledger.fill("AAPL", qty=-100, price=110_000)  # sell @ $11
    assert pos.realised_pnl_usd == pytest.approx(100.0, abs=0.01)
    assert pos.is_flat is True


def test_close_long_realises_loss(ledger):
    ledger.fill("AAPL", qty=100, price=100_000)
    pos = ledger.fill("AAPL", qty=-100, price=90_000)
    assert pos.realised_pnl_usd == pytest.approx(-100.0, abs=0.01)


def test_partial_close_realises_partial_pnl(ledger):
    ledger.fill("AAPL", qty=100, price=100_000)
    pos = ledger.fill("AAPL", qty=-60, price=110_000)
    assert pos.realised_pnl_usd == pytest.approx(60.0, abs=0.01)
    assert pos.net_qty == 40


def test_flip_long_to_short(ledger):
    ledger.fill("AAPL", qty=100, price=100_000)
    pos = ledger.fill("AAPL", qty=-150, price=110_000)
    assert pos.is_short is True
    assert pos.net_qty == -50
    assert pos.realised_pnl_usd == pytest.approx(100.0, abs=0.01)


# ---- Unrealised P&L ---------------------------------------------------------

def test_unrealised_pnl_long(ledger):
    ledger.fill("AAPL", qty=100, price=100_000)
    pos = ledger.position("AAPL")
    upnl = pos.unrealised_pnl_usd(mark_price=105_000)
    assert upnl == pytest.approx(50.0, abs=0.01)   # 100 * $0.50


def test_unrealised_pnl_short(ledger):
    ledger.fill("AAPL", qty=-100, price=100_000)
    pos = ledger.position("AAPL")
    upnl = pos.unrealised_pnl_usd(mark_price=95_000)
    assert upnl == pytest.approx(50.0, abs=0.01)   # short profits on drop


# ---- Multi-symbol -----------------------------------------------------------

def test_multi_symbol_independent(ledger):
    ledger.fill("AAPL", qty=100, price=100_000)
    ledger.fill("GOOG", qty=50,  price=200_000)
    assert ledger.symbol_count == 2
    assert ledger.position("AAPL").net_qty == 100
    assert ledger.position("GOOG").net_qty == 50


def test_total_realised_pnl(ledger):
    ledger.fill("AAPL", qty=100, price=100_000)
    ledger.fill("AAPL", qty=-100, price=110_000)
    ledger.fill("GOOG", qty=50, price=200_000)
    ledger.fill("GOOG", qty=-50, price=210_000)
    assert ledger.total_realised_pnl_usd == pytest.approx(150.0, abs=0.01)


def test_total_unrealised_pnl(ledger):
    ledger.fill("AAPL", qty=100, price=100_000)
    ledger.fill("GOOG", qty=50,  price=200_000)
    marks = {"AAPL": 105_000, "GOOG": 205_000}
    upnl = ledger.total_unrealised_pnl_usd(marks)
    assert upnl == pytest.approx(75.0, abs=0.01)   # $50 + $25


def test_open_positions_excludes_flat(ledger):
    ledger.fill("AAPL", qty=100, price=100_000)
    ledger.fill("AAPL", qty=-100, price=110_000)
    ledger.fill("GOOG", qty=50, price=200_000)
    open_pos = ledger.open_positions()
    assert "AAPL" not in open_pos
    assert "GOOG" in open_pos


# ---- Reset ------------------------------------------------------------------

def test_reset_all(ledger):
    ledger.fill("AAPL", qty=100, price=100_000)
    ledger.reset()
    assert ledger.symbol_count == 0


def test_reset_single_symbol(ledger):
    ledger.fill("AAPL", qty=100, price=100_000)
    ledger.fill("GOOG", qty=50, price=200_000)
    ledger.reset("AAPL")
    assert ledger.position("AAPL") is None
    assert ledger.position("GOOG") is not None


def test_position_none_for_unknown(ledger):
    assert ledger.position("TSLA") is None


def test_str_representation(ledger):
    ledger.fill("AAPL", qty=100, price=100_000)
    s = str(ledger)
    assert "AAPL" in s
    assert "realised" in s
