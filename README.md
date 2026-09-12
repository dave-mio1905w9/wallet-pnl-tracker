# wallet-pnl

Small CLI tool I use to parse wallet export dumps from in-game market logs, calculate cost basis (FIFO or average cost), and see realized vs unrealized PnL.

Currently handles standard CSV/TSV market transaction exports.

## Setup

```bash
pip install -e .
```

For development and running tests:
```bash
pip install -e ".[dev]"
pytest
```

## How I use it

Import a wallet dump file:
```bash
wallet-pnl import ~/Downloads/wallet_export_2024_10.csv
```

Show summary using FIFO accounting:
```bash
wallet-pnl report --method fifo
```

Show per-item breakdown for specific items with open positions:
```bash
wallet-pnl positions --open-only
wallet-pnl history "Tritanium"
```

Data is stored in a local SQLite db at `~/.wallet_pnl/trades.db` by default (override with `--db <path>`).

<!-- checked: 2026-09-12 -->
