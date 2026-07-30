from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict
from enum import Enum


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class CostBasisMethod(str, Enum):
    FIFO = "fifo"
    AVG = "average"


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
    station_or_market: Optional[str] = None
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


@dataclass
class Position:
    item_id: str
    item_name: str
    total_quantity: Decimal = Decimal("0")
    total_cost: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    total_fees: Decimal = Decimal("0")
    open_lots: List[Lot] = field(default_factory=list)

    @property
    def average_entry_price(self) -> Decimal:
        if self.total_quantity <= 0:
            return Decimal("0")
        return (self.total_cost / self.total_quantity).quantize(Decimal("0.01"))


@dataclass
class SummaryReport:
    """Aggregated results across all parsed trades and open lots."""
    generated_at: datetime
    method: CostBasisMethod
    positions: Dict[str, Position] = field(default_factory=dict)
    trade_records: List[TradePnL] = field(default_factory=list)
    untracked_sells: int = 0
    total_realized_pnl: Decimal = Decimal("0")
    total_fees_paid: Decimal = Decimal("0")
