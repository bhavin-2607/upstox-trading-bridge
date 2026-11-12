"""Universal CLI entrypoint for Upstox Live Market Data Bridge."""

from __future__ import annotations

import argparse
import logging
import random
import sys
import time
from pathlib import Path

# Add project root to path if running directly
sys.path.insert(0, str(Path(__file__).resolve().parent))

from upstox_bridge.auth.oauth import UpstoxAuthManager
from upstox_bridge.core.config import settings
from upstox_bridge.core.market_store import MarketStore
from upstox_bridge.destinations.excel_syncer import ExcelSyncer
from upstox_bridge.destinations.gsheet_webhook import GoogleSheetWebhookSyncer
from upstox_bridge.destinations.local_feed_server import LocalFeedServer
from upstox_bridge.instruments.master import InstrumentMaster
from upstox_bridge.runner import BridgeRunner
from templates.create_template import generate_styled_template

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("MainCLI")


def cmd_run(args):
    """Run the live market data bridge."""
    runner = BridgeRunner()

    if args.symbols:
        custom_symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
        runner.initialize_instruments(custom_symbols)

    if args.no_excel:
        settings.config.setdefault("excel", {})["enabled"] = False
    if args.no_gsheet:
        settings.config.setdefault("google_sheets", {})["enabled"] = False

    runner.start()


def cmd_simulate(args):
    """Run simulation mode: feeds realistic live ticks for testing after-hours or on weekends."""
    print("=" * 65)
    print(" UPSTOX BRIDGE: SIMULATION MODE (Testing & Verification) ")
    print("=" * 65)
    print("Generates realistic real-time ticks to test Excel & Google Sheets")
    print("without needing an active Upstox market hours session.")
    print("=" * 65)

    store = MarketStore()
    master = InstrumentMaster()

    symbols = settings.watchlist_symbols or ["NIFTY 50", "NIFTY BANK", "RELIANCE", "TCS", "HDFCBANK", "INFY", "TATAMOTORS"]
    for sym in symbols:
        key = master.resolve_symbol(sym)
        store.register_instrument(instrument_key=key, symbol=sym)

    # Initialize simulated base prices
    base_prices = {}
    default_base = {
        "NIFTY 50": 24200.0,
        "NIFTY BANK": 51800.0,
        "RELIANCE": 2985.0,
        "TCS": 4120.0,
        "HDFCBANK": 1690.0,
        "INFY": 1845.0,
        "TATAMOTORS": 940.0,
    }
    for sym in symbols:
        base_prices[sym] = default_base.get(sym, round(random.uniform(500, 3500), 2))

    for sym, price in base_prices.items():
        key = master.resolve_symbol(sym)
        store.update_quote(
            instrument_key=key,
            ltp=price,
            open_price=price * 0.998,
            high_price=price * 1.005,
            low_price=price * 0.995,
            close_price=price * 0.997,
            vwap=round(price * 0.999, 2),
            volume=150000,
        )

    # Start Local HTTP server
    if settings.local_server_enabled:
        server = LocalFeedServer(store)
        server.start()

    # Start Excel syncer
    excel = ExcelSyncer(market_store=store)
    excel.start()

    # Start Google Sheet syncer if webhook provided
    gsheet = None
    if settings.gsheet_webhook_url:
        gsheet = GoogleSheetWebhookSyncer(market_store=store)
        gsheet.start()
    else:
        print("\nNote: GOOGLE_SHEET_WEBHOOK_URL is not set in .env. Skipping Google Sheets push.")

    print("\nSimulation is streaming ticks live! Press Ctrl+C to stop.")
    print("Tip: You can edit 'watchlist.txt' anytime while this is running to add/remove symbols!\n")

    last_txt_mtime = settings.watchlist_txt_path.stat().st_mtime if settings.watchlist_txt_path.exists() else 0.0

    try:
        while True:
            # Check if watchlist.txt was edited
            if settings.watchlist_txt_path.exists():
                curr_mtime = settings.watchlist_txt_path.stat().st_mtime
                if last_txt_mtime and curr_mtime != last_txt_mtime:
                    last_txt_mtime = curr_mtime
                    new_syms = settings.read_watchlist_txt()
                    if new_syms:
                        symbols = new_syms
                        pairs = []
                        for s in symbols:
                            k = master.resolve_symbol(s)
                            pairs.append((k, s))
                            if s not in base_prices:
                                base_prices[s] = default_base.get(s, round(random.uniform(500, 3500), 2))
                        store.sync_watchlist(pairs)
                        print(f"[Simulation Watchlist Updated] Active symbols ({len(symbols)}): {', '.join(symbols)}")
                elif not last_txt_mtime:
                    last_txt_mtime = curr_mtime

            # Pick 2-3 random stocks and nudge prices slightly
            sample_k = min(len(symbols), random.randint(2, 4))
            for sym in random.sample(symbols, k=sample_k):
                key = master.resolve_symbol(sym)
                current = base_prices.get(sym, 2000.0)
                delta = current * random.uniform(-0.0015, 0.0015)
                new_price = round(current + delta, 2)
                base_prices[sym] = new_price

                store.update_quote(
                    instrument_key=key,
                    ltp=new_price,
                    high_price=max(new_price, base_prices[sym]),
                    low_price=min(new_price, base_prices[sym]),
                    vwap=round(new_price * 0.999, 2),
                    volume=int(random.randint(1000, 50000)),
                )

            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping simulation...")
        excel.stop()
        if gsheet:
            gsheet.stop()
        print("Simulation stopped.")


def cmd_login(args):
    """Run interactive OAuth login."""
    auth = UpstoxAuthManager()
    token = auth.interactive_login()
    print("\nLogin completed successfully! Access token cached for today.")


def cmd_search(args):
    """Search Upstox instruments."""
    master = InstrumentMaster()
    print(f"Searching for '{args.query}' in Upstox instruments...")
    results = master.search_symbols(args.query, limit=args.limit)
    if not results:
        print("No matching symbols found.")
        return

    print(f"\nFound {len(results)} matches:")
    print(f"{'Trading Symbol':<20} {'Instrument Key':<30} {'Name':<35}")
    print("-" * 85)
    for item in results:
        sym = item.get("trading_symbol", "")
        key = item.get("instrument_key", "")
        name = item.get("name", "")
        print(f"{sym:<20} {key:<30} {name:<35}")


def cmd_test_gsheet(args):
    """Test connection to Google Sheets Webhook."""
    print("Testing connection to Google Sheets Webhook...")
    syncer = GoogleSheetWebhookSyncer(MarketStore())
    result = syncer.test_connection()
    if result.get("success"):
        print("\nSUCCESS! Google Sheet Webhook responded with HTTP 200.")
        print(f"Server response: {result.get('response')}")
        print("Check your Google Sheet 'LiveMarket' tab to see the test row.")
    else:
        print("\nFAILED: Could not write to Google Sheet Webhook.")
        print(f"Details: {result.get('error')}")


def cmd_test_excel(args):
    """Test writing to Excel."""
    print("Testing local Excel integration...")
    store = MarketStore()
    master = InstrumentMaster()
    for sym in ["NIFTY 50", "RELIANCE", "TCS"]:
        key = master.resolve_symbol(sym)
        store.register_instrument(key, sym)
        store.update_quote(key, ltp=25000.0, open_price=24900.0, close_price=24800.0, vwap=24950.0)

    syncer = ExcelSyncer(market_store=store)
    syncer.sync_once()
    print(f"Successfully wrote test rows to: {settings.excel_file_path}")
    print("You can open this file in Excel to inspect.")


def cmd_create_template(args):
    """Regenerate template Excel file."""
    out = settings.templates_dir / "Upstox_Live_Market.xlsx"
    generate_styled_template(out)
    print(f"Generated clean styled template at: {out}")


def main():
    parser = argparse.ArgumentParser(
        description="Upstox Live Market Data Bridge (Excel & Google Sheets)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Run
    p_run = subparsers.add_parser("run", help="Start the live market data bridge")
    p_run.add_argument("--symbols", help="Comma-separated symbols to stream (e.g. 'NIFTY 50,RELIANCE')")
    p_run.add_argument("--no-excel", action="store_true", help="Disable Excel sync")
    p_run.add_argument("--no-gsheet", action="store_true", help="Disable Google Sheets sync")

    # Simulate
    subparsers.add_parser("simulate", help="Start simulation mode with real-time ticks (ideal for testing after-hours)")

    # Login
    subparsers.add_parser("login", help="Authenticate with Upstox API and cache access token")

    # Search
    p_search = subparsers.add_parser("search", help="Search Upstox symbols & instrument keys")
    p_search.add_argument("query", help="Symbol or company name to search (e.g. 'RELIANCE')")
    p_search.add_argument("--limit", type=int, default=15, help="Max results (default: 15)")

    # Test GSheet
    subparsers.add_parser("test-gsheet", help="Test connection to Google Sheets Webhook")

    # Test Excel
    subparsers.add_parser("test-excel", help="Test writing to local Excel workbook")

    # Create Template
    subparsers.add_parser("create-template", help="Generate styled Excel template workbook")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "run": cmd_run,
        "simulate": cmd_simulate,
        "login": cmd_login,
        "search": cmd_search,
        "test-gsheet": cmd_test_gsheet,
        "test-excel": cmd_test_excel,
        "create-template": cmd_create_template,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
