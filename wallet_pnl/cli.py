import argparse
import sys
from pathlib import Path
from wallet_pnl.storage import Database
from wallet_pnl.parsers import parse_dump_file
from wallet_pnl.calculator import calculate_pnl, get_open_positions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wallet-pnl",
        description="Track in-game market trades, cost basis, and realized PnL.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("wallet.db"),
        help="path to sqlite database (default: wallet.db)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # import command
    import_parser = subparsers.add_parser("import", help="ingest trade dump file")
    import_parser.add_argument("file", type=Path, help="dump file path")
    import_parser.add_argument(
        "--format",
        choices=["eve_wallet", "gw2_tp", "generic_csv"],
        default="generic_csv",
        help="source file format",
    )

    # pnl report command
    pnl_parser = subparsers.add_parser("report", help="calculate realized and unrealized pnl")
    pnl_parser.add_argument("--item", type=str, help="filter by specific item name")
    pnl_parser.add_argument(
        "--method",
        choices=["fifo", "avg"],
        default="fifo",
        help="cost basis method (default: fifo)",
    )

    # positions command
    pos_parser = subparsers.add_parser("positions", help="list current open inventory lots")
    pos_parser.add_argument("--item", type=str, help="filter by item name")

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    db = Database(args.db)
    db.init_schema()

    if args.command == "import":
        if not args.file.exists():
            print(f"error: file not found: {args.file}", file=sys.stderr)
            return 1
        trades = parse_dump_file(args.file, parser_type=args.format)
        inserted = db.insert_trades(trades)
        print(f"Imported {inserted} new trades from {args.file.name}")
        return 0

    if args.command == "report":
        trades = db.get_trades(item_filter=args.item)
        if not trades:
            print("No trades found matching criteria.")
            return 0
        
        results = calculate_pnl(trades, method=args.method)
        total_realized = 0.0
        for item_name, stats in results.items():
            print(f"{item_name}:")
            print(f"  Qty Sold: {stats.qty_sold} | Realized PnL: {stats.realized_pnl:,.2f}")
            total_realized += stats.realized_pnl
        print(f"\nTotal Realized PnL: {total_realized:,.2f}")
        return 0

    if args.command == "positions":
        trades = db.get_trades(item_filter=args.item)
        positions = get_open_positions(trades)
        if not positions:
            print("No open positions.")
            return 0
        
        for item_name, lots in positions.items():
            total_qty = sum(lot.remaining_qty for lot in lots)
            print(f"{item_name}: {total_qty} units across {len(lots)} lots")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
