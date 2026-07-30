import argparse
import sys
from datetime import datetime
from pathlib import Path
from wallet_pnl.storage import Database
from wallet_pnl.parsers import parse_dump_file
from wallet_pnl.calculator import calculate_pnl, get_open_positions


def parse_iso_date(val: str) -> datetime:
    try:
        return datetime.fromisoformat(val)
    except ValueError:
        # fallback for simple YYYY-MM-DD
        try:
            return datetime.strptime(val, "%Y-%m-%d")
        except ValueError:
            raise argparse.ArgumentTypeError(f"invalid date format: '{val}' (expected YYYY-MM-DD or ISO timestamp)")


def _format_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return ""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    separator = "  ".join("-" * w for w in widths)
    
    lines = [fmt.format(*headers), separator]
    for row in rows:
        lines.append(fmt.format(*row))
    return "\n".join(lines)


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
    import_parser.add_argument(
        "--tax-rate",
        type=float,
        default=None,
        help="override sales tax rate (e.g. 0.08 for 8%%)",
    )

    # pnl report command
    pnl_parser = subparsers.add_parser("report", help="calculate realized and unrealized pnl")
    pnl_parser.add_argument("--item", type=str, help="filter by specific item name")
    pnl_parser.add_argument("--since", type=parse_iso_date, help="start date filter (YYYY-MM-DD)")
    pnl_parser.add_argument("--until", type=parse_iso_date, help="end date filter (YYYY-MM-DD)")
    pnl_parser.add_argument(
        "--method",
        choices=["fifo", "avg"],
        default="fifo",
        help="cost basis method (default: fifo)",
    )
    pnl_parser.add_argument(
        "--raw",
        action="store_true",
        help="print raw tab-separated output instead of formatted table",
    )

    # positions command
    pos_parser = subparsers.add_parser("positions", help="list current open inventory lots")
    pos_parser.add_argument("--item", type=str, help="filter by item name")
    pos_parser.add_argument("--detailed", action="store_true", help="show individual lots instead of aggregated totals")

    # wipe command for testing
    wipe_parser = subparsers.add_parser("wipe", help="wipe all imported trades from db")
    wipe_parser.add_argument("--yes", action="store_true", help="confirm deletion without prompt")

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
        trades = parse_dump_file(args.file, parser_type=args.format, tax_override=args.tax_rate)
        inserted = db.insert_trades(trades)
        print(f"Imported {inserted} new trades from {args.file.name}")
        return 0

    if args.command == "report":
        trades = db.get_trades(item_filter=args.item, since=args.since, until=args.until)
        # print(f"DEBUG: fetched {len(trades)} trades for report")
        if not trades:
            print("No trades found matching criteria.")
            return 0

        results = calculate_pnl(trades, method=args.method)
        if not results:
            print("No closed positions or sales recorded.")
            return 0

        if args.raw:
            for item_name, stats in sorted(results.items()):
                print(f"{item_name}\t{stats.qty_sold}\t{stats.cost_basis:.2f}\t{stats.revenue:.2f}\t{stats.realized_pnl:.2f}")
            return 0

        headers = ["Item", "Sold", "Cost Basis", "Revenue", "Realized PnL", "Margin"]
        rows = []
        total_cost = 0.0
        total_rev = 0.0
        total_realized = 0.0

        for item_name, stats in sorted(results.items()):
            margin = (stats.realized_pnl / stats.revenue * 100.0) if stats.revenue > 0 else 0.0
            rows.append([
                item_name,
                str(stats.qty_sold),
                f"{stats.cost_basis:,.2f}",
                f"{stats.revenue:,.2f}",
                f"{stats.realized_pnl:,.2f}",
                f"{margin:+.1f}%%",
            ])
            total_cost += stats.cost_basis
            total_rev += stats.revenue
            total_realized += stats.realized_pnl

        print(_format_table(headers, rows))
        total_margin = (total_realized / total_rev * 100.0) if total_rev > 0 else 0.0
        print("-" * 60)
        print(f"Total Cost: {total_cost:,.2f} | Revenue: {total_rev:,.2f} | PnL: {total_realized:,.2f} ({total_margin:+.1f}%%)")
        return 0

    if args.command == "positions":
        trades = db.get_trades(item_filter=args.item)
        positions = get_open_positions(trades)
        if not positions:
            print("No open positions.")
            return 0

        if args.detailed:
            # FIXME: lot breakdown should probably include remaining broker fee allocation
            headers = ["Item", "Date", "Lot Qty", "Remaining", "Unit Cost"]
            rows = []
            for item_name, lots in sorted(positions.items()):
                for lot in lots:
                    rows.append([
                        item_name,
                        lot.timestamp.strftime("%Y-%m-%d %H:%M"),
                        str(lot.initial_qty),
                        str(lot.remaining_qty),
                        f"{lot.unit_cost:,.2f}",
                    ])
            print(_format_table(headers, rows))
        else:
            headers = ["Item", "Open Units", "Est Cost Basis", "Avg Cost/Unit"]
            rows = []
            for item_name, lots in sorted(positions.items()):
                total_qty = sum(lot.remaining_qty for lot in lots)
                total_val = sum(lot.remaining_qty * lot.unit_cost for lot in lots)
                avg_cost = (total_val / total_qty) if total_qty > 0 else 0.0
                rows.append([
                    item_name,
                    str(total_qty),
                    f"{total_val:,.2f}",
                    f"{avg_cost:,.2f}",
                ])
            print(_format_table(headers, rows))
        return 0

    if args.command == "wipe":
        if not args.yes:
            confirm = input("Are you sure you want to wipe all trade history? [y/N]: ")
            if confirm.lower() != "y":
                print("Aborted.")
                return 0
        deleted = db.wipe_trades()
        print(f"Deleted {deleted} records from database.")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
