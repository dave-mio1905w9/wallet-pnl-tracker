from collections import deque
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Optional, Tuple
from wallet_pnl.models import (
    Transaction,
    Side,
    Lot,
    TradePnL,
    Position,
    SummaryReport,
    CostBasisMethod,
)


def round_isk(val: Decimal) -> Decimal:
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class CostCalculator:
    """Calculates inventory basis and realized profit per trade using FIFO or Average cost."""

    def __init__(self, method: CostBasisMethod = CostBasisMethod.FIFO):
        self.method = method
        self.queues: Dict[str, deque[Lot]] = {}
        # Fallback state for weighted-average cost tracking
        self._avg_qty: Dict[str, Decimal] = {}
        self._avg_unit_cost: Dict[str, Decimal] = {}
        self._lot_counter = 0

    def _next_lot_id(self) -> str:
        self._lot_counter += 1
        return f"lot-{self._lot_counter}"

    def run(self, txs: List[Transaction]) -> SummaryReport:
        # Market dumps often have duplicated timestamps for batches; stable sort keeps original file order
        sorted_txs = sorted(txs, key=lambda t: t.timestamp)
        pnl_records: List[TradePnL] = []
        positions: Dict[str, Position] = {}
        untracked_sells = 0

        for tx in sorted_txs:
            if tx.item_id not in positions:
                positions[tx.item_id] = Position(item_id=tx.item_id, item_name=tx.item_name)
            pos = positions[tx.item_id]

            if tx.side == Side.BUY:
                self._handle_buy(tx, pos)
            elif tx.side == Side.SELL:
                pnl_item, missed = self._handle_sell(tx, pos)
                if missed:
                    untracked_sells += 1
                if pnl_item:
                    pnl_records.append(pnl_item)

        # Sync remaining open lots into final positions
        for item_id, q in self.queues.items():
            if item_id in positions:
                positions[item_id].open_lots = [l for l in q if l.quantity_remaining > 0]

        tot_pnl = sum((r.realized_pnl for r in pnl_records), Decimal("0"))
        tot_fees = sum((t.fee for t in sorted_txs), Decimal("0"))

        return SummaryReport(
            generated_at=datetime.utcnow(),
            method=self.method,
            positions=positions,
            trade_records=pnl_records,
            untracked_sells=untracked_sells,
            total_realized_pnl=round_isk(tot_pnl),
            total_fees_paid=round_isk(tot_fees)
        )

    def _handle_buy(self, tx: Transaction, pos: Position):
        effective_cost = (tx.unit_price * tx.quantity) + tx.fee
        unit_cost = effective_cost / tx.quantity

        pos.total_quantity += tx.quantity
        pos.total_cost += effective_cost
        pos.total_fees += tx.fee

        if self.method == CostBasisMethod.FIFO:
            if tx.item_id not in self.queues:
                self.queues[tx.item_id] = deque()
            self.queues[tx.item_id].append(
                Lot(
                    lot_id=self._next_lot_id(),
                    item_id=tx.item_id,
                    buy_tx_id=tx.tx_id,
                    timestamp=tx.timestamp,
                    unit_cost=unit_cost,
                    quantity_remaining=tx.quantity,
                    fee_allocated=tx.fee
                )
            )
        else:
            # Weighted average cost update
            curr_qty = self._avg_qty.get(tx.item_id, Decimal("0"))
            curr_cost = self._avg_unit_cost.get(tx.item_id, Decimal("0"))
            new_qty = curr_qty + tx.quantity
            if new_qty > 0:
                self._avg_unit_cost[tx.item_id] = ((curr_qty * curr_cost) + effective_cost) / new_qty
            self._avg_qty[tx.item_id] = new_qty

    def _handle_sell(self, tx: Transaction, pos: Position) -> Tuple[Optional[TradePnL], bool]:
        if pos.total_quantity <= 0:
            # FIXME: track deficit instead of dropping when history begins after initial purchase
            pos.realized_pnl -= tx.fee
            pos.total_fees += tx.fee
            return None, True

        matched_qty = min(tx.quantity, pos.total_quantity)
        untracked = tx.quantity > pos.total_quantity

        # If the sell is only partially matched against known inventory, split the sale fee proportionally
        applicable_fee = tx.fee if matched_qty == tx.quantity else (tx.fee * (matched_qty / tx.quantity))

        cost_basis = Decimal("0")
        consumed_ids: List[str] = []

        if self.method == CostBasisMethod.FIFO:
            queue = self.queues.get(tx.item_id, deque())
            needed = matched_qty
            while needed > 0 and queue:
                lot = queue[0]
                if lot.quantity_remaining <= needed:
                    cost_basis += lot.quantity_remaining * lot.unit_cost
                    needed -= lot.quantity_remaining
                    consumed_ids.append(lot.lot_id)
                    queue.popleft()
                else:
                    cost_basis += needed * lot.unit_cost
                    lot.quantity_remaining -= needed
                    consumed_ids.append(lot.lot_id)
                    needed = Decimal("0")
                    # print(f"DEBUG: partially split lot {lot.lot_id}, left: {lot.quantity_remaining}")
        else:
            avg_cost = self._avg_unit_cost.get(tx.item_id, Decimal("0"))
            cost_basis = matched_qty * avg_cost
            self._avg_qty[tx.item_id] = self._avg_qty.get(tx.item_id, Decimal("0")) - matched_qty

        gross_revenue = tx.unit_price * matched_qty
        realized = gross_revenue - cost_basis - applicable_fee

        pos.total_quantity -= matched_qty
        pos.total_cost -= cost_basis
        pos.realized_pnl += realized
        pos.total_fees += tx.fee

        record = TradePnL(
            sell_tx_id=tx.tx_id,
            item_id=tx.item_id,
            item_name=tx.item_name,
            timestamp=tx.timestamp,
            quantity=matched_qty,
            sell_price=tx.unit_price,
            cost_basis=round_isk(cost_basis),
            revenue=round_isk(gross_revenue),
            fees_paid=round_isk(applicable_fee),
            realized_pnl=round_isk(realized),
            consumed_lots=consumed_ids
        )
        return record, untracked
