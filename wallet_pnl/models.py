from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from enum import Enum


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class Transaction:
    tx_id: str
    timestamp: datetime
    item_id: str
    item_name: str
    side: Side
    quantity: Decimal
    unit_price: Decimal
    fee: Decimal = Decimal("0")
    raw_ref: Optional[str] = None


@dataclass
class Lot:
    lot_id: str
    item_id: str
    buy_tx_id: str
    timestamp: datetime
    unit_cost: Decimal
    quantity_remaining: Decimal
    fee_allocated: Decimal = Decimal("0")


@dataclass
class TradePnL:
    sell_tx_id: str
    item_id: str
    item_name: str
    timestamp: datetime
    quantity: Decimal
    sell_price: Decimal
    cost_basis: Decimal
    revenue: Decimal
    fees_paid: Decimal
    realized_pnl: Decimal
    # IDs of lots consumed if calculated via FIFO
    consumed_lots: List[str] = field(default_factory=list)
