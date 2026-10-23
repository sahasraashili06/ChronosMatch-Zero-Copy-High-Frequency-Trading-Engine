"""
ChronosX -- FIX 4.2 Message Parser

Parses Financial Information eXchange (FIX) protocol messages —
the industry-standard protocol used by every major exchange and broker.

FIX message format:
    8=FIX.4.2|9=65|35=D|49=CLIENT|56=EXCHANGE|11=ORD001|54=1|38=100|44=100.50|10=128|

Key tags used:
    8  = BeginString   35 = MsgType    49 = SenderCompID
    56 = TargetCompID  11 = ClOrdID    54 = Side (1=Buy, 2=Sell)
    38 = OrderQty      44 = Price      40 = OrdType (1=Market, 2=Limit)
    10 = Checksum      60 = TransactTime
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from .types import Side, OrderType, PRICE_MULT


# ── FIX tag constants ─────────────────────────────────────────────────────────

class Tag:
    BEGIN_STRING   = 8
    BODY_LENGTH    = 9
    MSG_TYPE       = 35
    SENDER_COMP_ID = 49
    TARGET_COMP_ID = 56
    CL_ORD_ID      = 11
    SIDE           = 54
    ORDER_QTY      = 38
    PRICE          = 44
    ORD_TYPE       = 40
    CHECKSUM       = 10
    TRANSACT_TIME  = 60
    TEXT           = 58


class MsgType:
    NEW_ORDER_SINGLE   = "D"
    EXECUTION_REPORT   = "8"
    ORDER_CANCEL       = "F"
    HEARTBEAT          = "0"
    LOGON              = "A"
    LOGOUT             = "5"


# ── Parsed message ────────────────────────────────────────────────────────────

@dataclass
class FixMessage:
    """A parsed FIX message with raw tag dict and typed accessors."""
    raw_tags: Dict[int, str] = field(default_factory=dict)

    # ── Accessors ─────────────────────────────────────────────────────────────

    def get(self, tag: int, default: str = "") -> str:
        return self.raw_tags.get(tag, default)

    def get_int(self, tag: int, default: int = 0) -> int:
        v = self.raw_tags.get(tag)
        return int(v) if v is not None else default

    def get_float(self, tag: int, default: float = 0.0) -> float:
        v = self.raw_tags.get(tag)
        return float(v) if v is not None else default

    @property
    def msg_type(self) -> str:
        return self.get(Tag.MSG_TYPE)

    @property
    def cl_ord_id(self) -> str:
        return self.get(Tag.CL_ORD_ID)

    @property
    def side(self) -> Optional[Side]:
        v = self.get(Tag.SIDE)
        if v == "1":
            return Side.Buy
        if v == "2":
            return Side.Sell
        return None

    @property
    def order_qty(self) -> int:
        return self.get_int(Tag.ORDER_QTY)

    @property
    def price_fixed(self) -> int:
        """Price as fixed-point integer (×PRICE_MULT)."""
        fp = self.get_float(Tag.PRICE)
        return int(round(fp * PRICE_MULT))

    @property
    def ord_type(self) -> Optional[OrderType]:
        v = self.get(Tag.ORD_TYPE)
        if v == "1":
            return OrderType.Market
        if v == "2":
            return OrderType.Limit
        return None

    @property
    def sender(self) -> str:
        return self.get(Tag.SENDER_COMP_ID)

    @property
    def target(self) -> str:
        return self.get(Tag.TARGET_COMP_ID)

    def is_new_order(self) -> bool:
        return self.msg_type == MsgType.NEW_ORDER_SINGLE

    def is_cancel(self) -> bool:
        return self.msg_type == MsgType.ORDER_CANCEL

    def is_heartbeat(self) -> bool:
        return self.msg_type == MsgType.HEARTBEAT

    def __repr__(self) -> str:
        return (
            f"FixMessage(type={self.msg_type!r} "
            f"cl_ord_id={self.cl_ord_id!r} "
            f"side={self.side} "
            f"qty={self.order_qty} "
            f"price=${self.price_fixed / PRICE_MULT:.4f})"
        )


# ── Parser ────────────────────────────────────────────────────────────────────

class FixParser:
    """
    Parses raw FIX 4.2 message strings into FixMessage objects.

    Supports both pipe '|' and SOH (\\x01) delimiters.

    Usage:
        parser = FixParser()
        msg = parser.parse("8=FIX.4.2|35=D|49=CLIENT|54=1|38=100|44=99.50|40=2|11=ORD1|10=000|")
        print(msg.side)       # Side.Buy
        print(msg.order_qty)  # 100
        print(msg.price_fixed) # 995000
    """

    def __init__(self, delimiter: str = "|") -> None:
        self._delim = delimiter

    def parse(self, raw: str) -> FixMessage:
        """Parse a FIX message string. Returns a FixMessage."""
        tags: Dict[int, str] = {}
        # normalise SOH to pipe
        normalised = raw.replace("\x01", "|")
        for field_str in normalised.split("|"):
            field_str = field_str.strip()
            if not field_str:
                continue
            if "=" not in field_str:
                continue
            key, _, val = field_str.partition("=")
            try:
                tags[int(key)] = val
            except ValueError:
                pass   # skip malformed tags
        return FixMessage(raw_tags=tags)

    def validate_checksum(self, raw: str) -> bool:
        """
        Verify FIX checksum (tag 10).
        Sum of all bytes except the checksum field itself, mod 256.
        """
        # Find where checksum tag starts
        chk_tag = "\x01" + "10=" if "\x01" in raw else "|10="
        idx = raw.rfind(chk_tag)
        if idx == -1:
            return False
        body = raw[:idx + 1]   # include trailing delimiter
        expected = sum(ord(c) for c in body) % 256
        try:
            actual = int(self.parse(raw).get(Tag.CHECKSUM))
            return actual == expected
        except (ValueError, TypeError):
            return False


# ── Builder ───────────────────────────────────────────────────────────────────

class FixBuilder:
    """
    Builds FIX message strings from typed fields.

    Usage:
        msg = (FixBuilder()
               .msg_type(MsgType.NEW_ORDER_SINGLE)
               .sender("CLIENT").target("EXCHANGE")
               .cl_ord_id("ORD001")
               .side(Side.Buy).qty(100).limit_price(99.50)
               .build())
    """

    def __init__(self) -> None:
        self._tags: Dict[int, str] = {Tag.BEGIN_STRING: "FIX.4.2"}

    def msg_type(self, t: str)      -> "FixBuilder": self._tags[Tag.MSG_TYPE]       = t;      return self
    def sender(self, s: str)        -> "FixBuilder": self._tags[Tag.SENDER_COMP_ID] = s;      return self
    def target(self, t: str)        -> "FixBuilder": self._tags[Tag.TARGET_COMP_ID] = t;      return self
    def cl_ord_id(self, i: str)     -> "FixBuilder": self._tags[Tag.CL_ORD_ID]      = i;      return self
    def qty(self, q: int)           -> "FixBuilder": self._tags[Tag.ORDER_QTY]      = str(q); return self

    def side(self, s: Side) -> "FixBuilder":
        self._tags[Tag.SIDE] = "1" if s == Side.Buy else "2"
        return self

    def limit_price(self, p: float) -> "FixBuilder":
        self._tags[Tag.ORD_TYPE] = "2"
        self._tags[Tag.PRICE]    = f"{p:.2f}"
        return self

    def market(self) -> "FixBuilder":
        self._tags[Tag.ORD_TYPE] = "1"
        return self

    def build(self, delimiter: str = "|") -> str:
        body = delimiter.join(f"{k}={v}" for k, v in self._tags.items())
        body += delimiter
        checksum = sum(ord(c) for c in body) % 256
        return body + f"{Tag.CHECKSUM}={checksum:03d}{delimiter}"
