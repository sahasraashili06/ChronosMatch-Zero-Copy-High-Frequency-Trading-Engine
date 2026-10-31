"""Tests for SmartOrderRouter."""
import pytest
from chronosx.smart_order_router import (
    SmartOrderRouter, RoutingStrategy, VenueQuote, VenueOrder
)


def _quotes():
    return [
        VenueQuote("NYSE",   ask=100_100, ask_qty=500, bid=99_900, bid_qty=400),
        VenueQuote("NASDAQ", ask=100_050, ask_qty=300, bid=100_000, bid_qty=300),
        VenueQuote("BATS",   ask=100_200, ask_qty=800, bid=99_800,  bid_qty=600),
    ]


# ── BestPrice ─────────────────────────────────────────────────────────────────

def test_best_price_buys_cheapest_first():
    sor = SmartOrderRouter(RoutingStrategy.BestPrice)
    slices = sor.route_buy(qty=200, quotes=_quotes())
    assert slices[0].venue_id == "NASDAQ"   # cheapest ask


def test_best_price_overflows_to_next():
    sor = SmartOrderRouter(RoutingStrategy.BestPrice)
    # NASDAQ has only 300 qty, request 400 → overflow to NYSE
    slices = sor.route_buy(qty=400, quotes=_quotes())
    ids = [s.venue_id for s in slices]
    assert "NASDAQ" in ids
    assert "NYSE" in ids


def test_best_price_sell_highest_bid_first():
    sor = SmartOrderRouter(RoutingStrategy.BestPrice)
    slices = sor.route_sell(qty=200, quotes=_quotes())
    assert slices[0].venue_id == "NASDAQ"   # highest bid=100_000


# ── ProRata ───────────────────────────────────────────────────────────────────

def test_pro_rata_total_qty_correct():
    sor = SmartOrderRouter(RoutingStrategy.ProRata)
    slices = sor.route_buy(qty=600, quotes=_quotes())
    assert sum(s.qty for s in slices) == 600


def test_pro_rata_multiple_venues():
    sor = SmartOrderRouter(RoutingStrategy.ProRata)
    slices = sor.route_buy(qty=600, quotes=_quotes())
    assert len(slices) >= 2


def test_pro_rata_sell_total_qty():
    sor = SmartOrderRouter(RoutingStrategy.ProRata)
    slices = sor.route_sell(qty=400, quotes=_quotes())
    assert sum(s.qty for s in slices) == 400


# ── EqualSplit ────────────────────────────────────────────────────────────────

def test_equal_split_distributes_evenly():
    sor = SmartOrderRouter(RoutingStrategy.EqualSplit)
    slices = sor.route_buy(qty=300, quotes=_quotes())
    qtys = sorted(s.qty for s in slices)
    # each should get 100
    assert all(q == 100 for q in qtys)


def test_equal_split_leftover_distributed():
    sor = SmartOrderRouter(RoutingStrategy.EqualSplit)
    slices = sor.route_buy(qty=301, quotes=_quotes())
    assert sum(s.qty for s in slices) == min(301, sum(
        q.ask_qty for q in _quotes()
    ))


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_empty_quotes_returns_empty():
    sor = SmartOrderRouter(RoutingStrategy.BestPrice)
    assert sor.route_buy(qty=100, quotes=[]) == []


def test_zero_qty_returns_empty():
    sor = SmartOrderRouter(RoutingStrategy.BestPrice)
    assert sor.route_buy(qty=0, quotes=_quotes()) == []


def test_total_routed_tracked():
    sor = SmartOrderRouter(RoutingStrategy.BestPrice)
    sor.route_buy(qty=100, quotes=_quotes())
    sor.route_buy(qty=200, quotes=_quotes())
    assert sor.total_routed == 300


def test_reset_clears_total():
    sor = SmartOrderRouter(RoutingStrategy.BestPrice)
    sor.route_buy(qty=100, quotes=_quotes())
    sor.reset()
    assert sor.total_routed == 0


def test_invalid_min_qty_raises():
    with pytest.raises(ValueError):
        SmartOrderRouter(min_qty=0)


def test_notional_usd_computed():
    sor = SmartOrderRouter(RoutingStrategy.BestPrice)
    slices = sor.route_buy(qty=100, quotes=_quotes())
    assert slices[0].notional_usd > 0
