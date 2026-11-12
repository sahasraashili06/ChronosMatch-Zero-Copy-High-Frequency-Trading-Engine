"""Tests for FIX parser, message accessors, and builder."""
import pytest
from chronosx.fix_parser import FixParser, FixBuilder, FixMessage, Tag, MsgType
from chronosx.types import Side, OrderType, PRICE_MULT

SAMPLE = "8=FIX.4.2|35=D|49=CLIENT|56=EXCHANGE|11=ORD001|54=1|38=100|44=99.50|40=2|10=000|"


@pytest.fixture
def parser():
    return FixParser()


def test_parse_msg_type(parser):
    msg = parser.parse(SAMPLE)
    assert msg.msg_type == "D"
    assert msg.is_new_order()


def test_parse_side_buy(parser):
    msg = parser.parse(SAMPLE)
    assert msg.side == Side.Buy


def test_parse_side_sell(parser):
    msg = parser.parse("35=F|54=2|38=50|11=X|10=000|")
    assert msg.side == Side.Sell


def test_parse_qty(parser):
    msg = parser.parse(SAMPLE)
    assert msg.order_qty == 100


def test_parse_price_fixed(parser):
    msg = parser.parse(SAMPLE)
    assert msg.price_fixed == int(round(99.50 * PRICE_MULT))


def test_parse_ord_type_limit(parser):
    msg = parser.parse(SAMPLE)
    assert msg.ord_type == OrderType.Limit


def test_parse_ord_type_market(parser):
    msg = parser.parse("35=D|40=1|54=1|38=10|11=M1|10=000|")
    assert msg.ord_type == OrderType.Market


def test_parse_sender_target(parser):
    msg = parser.parse(SAMPLE)
    assert msg.sender == "CLIENT"
    assert msg.target == "EXCHANGE"


def test_parse_cl_ord_id(parser):
    msg = parser.parse(SAMPLE)
    assert msg.cl_ord_id == "ORD001"


def test_parse_soh_delimiter(parser):
    soh_msg = SAMPLE.replace("|", "\x01")
    msg = parser.parse(soh_msg)
    assert msg.side == Side.Buy


def test_malformed_tags_skipped(parser):
    msg = parser.parse("8=FIX.4.2|BADTAG|35=D|10=000|")
    assert msg.msg_type == "D"


def test_missing_tag_returns_default(parser):
    msg = parser.parse("35=D|10=000|")
    assert msg.order_qty == 0
    assert msg.price_fixed == 0


def test_heartbeat(parser):
    msg = parser.parse("35=0|10=000|")
    assert msg.is_heartbeat()


def test_cancel(parser):
    msg = parser.parse("35=F|10=000|")
    assert msg.is_cancel()


def test_builder_round_trip():
    raw = (FixBuilder()
           .msg_type(MsgType.NEW_ORDER_SINGLE)
           .sender("CLIENT").target("EXCHANGE")
           .cl_ord_id("ORD001")
           .side(Side.Buy).qty(100).limit_price(99.50)
           .build())
    msg = FixParser().parse(raw)
    assert msg.msg_type   == MsgType.NEW_ORDER_SINGLE
    assert msg.side       == Side.Buy
    assert msg.order_qty  == 100
    assert abs(msg.price_fixed - int(round(99.50 * PRICE_MULT))) <= 1


def test_builder_market_order():
    raw = (FixBuilder()
           .msg_type(MsgType.NEW_ORDER_SINGLE)
           .side(Side.Sell).qty(50).market()
           .cl_ord_id("M1").build())
    msg = FixParser().parse(raw)
    assert msg.ord_type == OrderType.Market
    assert msg.side     == Side.Sell
