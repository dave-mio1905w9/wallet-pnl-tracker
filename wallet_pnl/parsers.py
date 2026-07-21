import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from wallet_pnl.models import Transaction, Side


def _clean_num(val: str | int | float) -> float:
    if isinstance(val, (int, float)):
        return float(val)
    if not val:
        return 0.0
    # some exports put commas in large quantities or prices
    # e.g. "1,500,000.00 ISK" or "1 200,50"
    s = str(val).strip().replace(" ", "")
    for suffix in ["isk", "g", "gold", "cr", "credits"]:
        if s.lower().endswith(suffix):
            s = s[: -len(suffix)].strip()
    # handle european comma as decimal separator if no period present
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")
    return float(s)


def _parse_date(val: str) -> datetime:
    val = val.strip()
    if not val:
        return datetime.now(timezone.utc)
    if val.endswith("Z"):
        val = val[:-1] + "+00:00"
    
    # game exports love weird date strings
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y.%m.%d %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(val, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.fromisoformat(val)


def parse_dump(path: Path | str) -> list[Transaction]:
    """Reads wallet dump files, sniffing delimiter for csv/tsv or falling back to json."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"file not found: {p}")

    if p.suffix.lower() == ".json":
        return parse_json(p)

    # sniffing delimiter because game dumps often come as tab-separated
    with open(p, "r", encoding="utf-8-sig", errors="replace") as f:
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;| ")
            delim = dialect.delimiter
        except csv.Error:
            delim = "\t" if "\t" in sample else ","

        reader = csv.DictReader(f, delimiter=delim)
        txs = []
        for line_num, raw_row in enumerate(reader, start=2):
            if not raw_row or not any(raw_row.values()):
                continue
            row = {k.strip().lower(): (v.strip() if v else "") for k, v in raw_row.items() if k}
            
            # some tools export buys as positive qty and sells as negative
            qty_val = row.get("quantity", row.get("qty", row.get("count", "0")))
            try:
                parsed_qty = _clean_num(qty_val)
            except ValueError:
                continue

            side_str = row.get("type", row.get("side", row.get("action", ""))).upper()
            if "BUY" in side_str or "BID" in side_str or side_str == "B":
                side = Side.BUY
            elif "SELL" in side_str or "ASK" in side_str or side_str == "S":
                side = Side.SELL
            elif parsed_qty < 0:
                side = Side.SELL
                parsed_qty = abs(parsed_qty)
            else:
                side = Side.BUY

            item = row.get("item", row.get("item_name", row.get("typename", row.get("name", ""))))
            if not item:
                continue

            price_raw = row.get("price", row.get("unit_price", row.get("unitprice", "0")))
            fee_raw = row.get("fee", row.get("tax", row.get("broker_fee", "0")))
            date_raw = row.get("date", row.get("timestamp", row.get("transactiondate", "")))
            tx_id = row.get("id", row.get("tx_id", row.get("transactionid", f"line_{line_num}")))

            txs.append(Transaction(
                tx_id=str(tx_id),
                timestamp=_parse_date(date_raw),
                item_name=item,
                side=side,
                quantity=abs(parsed_qty),
                price=abs(_clean_num(price_raw)),
                fee=abs(_clean_num(fee_raw)),
            ))
    return txs


def parse_json(path: Path | str) -> list[Transaction]:
    p = Path(path)
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data if isinstance(data, list) else data.get("transactions", data.get("trades", data.get("data", [])))
    txs = []
    for idx, r in enumerate(items):
        if not isinstance(r, dict):
            continue
        side_raw = str(r.get("type", r.get("side", ""))).upper()
        qty = _clean_num(r.get("quantity", r.get("qty", 1)))
        if "BUY" in side_raw or side_raw == "B":
            side = Side.BUY
        elif "SELL" in side_raw or side_raw == "S":
            side = Side.SELL
        elif qty < 0:
            side = Side.SELL
            qty = abs(qty)
        else:
            side = Side.BUY

        txs.append(Transaction(
            tx_id=str(r.get("id", r.get("tx_id", f"json_{idx}"))),
            timestamp=_parse_date(str(r.get("timestamp", r.get("date", "")))),
            item_name=str(r.get("item", r.get("item_name", r.get("name", "unknown")))),
            side=side,
            quantity=abs(qty),
            price=abs(_clean_num(r.get("price", r.get("unit_price", 0)))),
            fee=abs(_clean_num(r.get("fee", r.get("tax", 0.0)))),
        ))
    return txs
