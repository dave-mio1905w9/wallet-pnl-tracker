from collections import deque
from decimal import Decimal
from typing import List, Dict, Tuple
from wallet_pnl.models import Transaction, Side, Lot, TradePnL


class CostCalculator:
    def __init__(self):
        self.queues: Dict[str, deque[Lot]] = {}
        self.lot_counter = 0

    def _next_lot_id(self) -> str:
        self.lot_counter += 1
        return f"lot-{self.lot_counter}"

    def process_transactions(self, txs: List[Transaction]) -> Tuple[List[TradePnL], Dict[str, List[Lot]]]:
        # In-game logs are often exported newest-first, so caller must sort or we do it here
        sorted_txs = sorted(txs, key=lambda t: t.timestamp)
        pnl_records: List[TradePnL] = []

        for tx in sorted_txs:
            if tx.item_id not in self.queues:
                self.queues[tx.item_id] = deque()

            queue = self.queues[tx.item_id]

            if tx.side == Side.BUY:
                # Buy fee adds directly to the cost basis of the acquired lot
                unit_cost = (tx.unit_price * tx.quantity + tx.fee) / tx.quantity
                lot = Lot(
                    lot_id=self._next_lot_id(),
                    item_id=tx.item_id,
                    buy_tx_id=tx.tx_id,
                    timestamp=tx.timestamp,
                    unit_cost=unit_cost,
                    quantity_remaining=tx.quantity,
                    fee_allocated=tx.fee
                )
                queue.append(lot)
            elif tx.side == Side.SELL:
                sell_qty_needed = tx.quantity
                cost_basis = Decimal("0")
                consumed_ids = []

                while sell_qty_needed > 0 and queue:
                    top_lot = queue[0]
                    if top_lot.quantity_remaining <= sell_qty_needed:
                        cost_basis += top_lot.quantity_remaining * top_lot.unit_cost
                        sell_qty_needed -= top_lot.quantity_remaining
                        consumed_ids.append(top_lot.lot_id)
                        queue.popleft()
                    else:
                        cost_basis += sell_qty_needed * top_lot.unit_cost
                        top_lot.quantity_remaining -= sell_qty_needed
                        consumed_ids.append(top_lot.lot_id)
                        sell_qty_needed = Decimal("0")

                # If sell_qty_needed > 0 here, user sold stock they didn't have in the dump
                revenue = tx.unit_price * (tx.quantity - sell_qty_needed)
                realized = revenue - cost_basis - tx.fee

                record = TradePnL(
                    sell_tx_id=tx.tx_id,
                    item_id=tx.item_id,
                    item_name=tx.item_name,
                    timestamp=tx.timestamp,
                    quantity=tx.quantity - sell_qty_needed,
                    sell_price=tx.unit_price,
                    cost_basis=cost_basis,
                    revenue=revenue,
                    fees_paid=tx.fee,
                    realized_pnl=realized,
                    consumed_lots=consumed_ids
                )
                pnl_records.append(record)

        remaining_lots = {k: list(v) for k, v in self.queues.items() if v}
        return pnl_records, remaining_lots
