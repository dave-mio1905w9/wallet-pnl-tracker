import csv
import json
from datetime import datetime
from pathlib import Path
from wallet_pnl.models import Transaction, Side


def _parse_iso(val: str) -> datetime:
    val = val.strip().replace("Z", "+00:00")
    return datetime.fromisoformat(val)


