import csv
import json
from datetime import datetime
from pathlib import Path
from wallet_pnl.models import Transaction, Side


def _parse_iso(val: str) -> datetime:
    val = val.strip().replace("Z", "+00:00")
    return datetime.fromisoformat(val)


def parse_csv(path: Path | str) -> list[Transaction]:
    p = Path(path)
    txs = []
    with open(p, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # normalize header keys
            r = {k.strip().lower(): v.strip() for k, v in row.items() if k}
            side_raw = r.get("type", r.get("side", "")).upper()
            if side_raw in ("BUY", "B", "BID"):
                side = Side.BUY
            elif side_raw in ("SELL", "S", "ASK"):
                side = Side.SELL
            else:
                continue

            txs.append(Transaction(
                tx_id=r.get("id", r.get("tx_id", "")),
                timestamp=_parse_iso(r["timestamp"] if "timestamp" in r else r["date"]),
                item_name=r.get("item", r.get("item_name", r.get("type_name", ""))),
                side=side,
                quantity=float(r["quantity"] if "quantity" in r else r["qty"]),
                price=float(r["price"] if "price" in r else r["unit_price"]),
                fee=float(r.get("fee", r.get("tax", 0.0)) or 0.0),
            ))
    return txs


def parse_json(path: Path | str) -> list[Transaction]:
    p = Path(path)
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data if isinstance(data, list) else data.get("transactions", data.get("trades", []))
    txs = []
    for r in items:
        side_raw = str(r.get("type", r.get("side", ""))).upper()
        side = Side.BUY if side_raw in ("BUY", "B") else Side.SELL
        txs.append(Transaction(
            tx_id=str(r.get("id", r.get("tx_id", ""))),
            timestamp=_parse_iso(r.get("timestamp", r.get("date", ""))),
            item_name=str(r.get("item", r.get("item_name", ""))),
            side=side,
            quantity=float(r.get("quantity", r.get("qty", 0))),
            price=float(r.get("price", r.get("unit_price", 0))),
            fee=float(r.get("fee", r.get("tax", 0.0)) or 0.0),
        ))
    return txs
