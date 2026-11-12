"""Generate pre-styled Excel template workbook with formulas and conditional formatting."""

from pathlib import Path
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from upstox_bridge.core.market_store import MarketStore


def generate_styled_template(output_path: Path) -> Path:
    """Create an aesthetically styled Excel template workbook."""
    wb = openpyxl.Workbook()

    # Sheet 1: LiveMarket
    ws_live = wb.active
    ws_live.title = "LiveMarket"

    # Styling definitions
    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    data_font = Font(name="Segoe UI", size=10)
    center_align = Alignment(horizontal="center", vertical="center")
    right_align = Alignment(horizontal="right", vertical="center")
    left_align = Alignment(horizontal="left", vertical="center")

    thin_border = Border(
        left=Side(style="thin", color="E2E8F0"),
        right=Side(style="thin", color="E2E8F0"),
        top=Side(style="thin", color="E2E8F0"),
        bottom=Side(style="thin", color="E2E8F0"),
    )

    # Write Headers
    headers = MarketStore.HEADERS
    ws_live.append(headers)

    for col_idx in range(1, len(headers) + 1):
        cell = ws_live.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align

    from upstox_bridge.core.config import settings
    from upstox_bridge.instruments.master import InstrumentMaster

    master = InstrumentMaster()
    active_symbols = settings.watchlist_symbols or ["NIFTY 50", "NIFTY BANK", "RELIANCE"]

    sample_symbols = []
    for sym in active_symbols:
        key = master.resolve_symbol(sym)
        sample_symbols.append((sym, key))

    for sym, key in sample_symbols:
        # Symbol, Instrument Key, LTP, Change, VWAP, Open, High, Low, Close, Volume, Updated At
        ws_live.append([sym, key, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, "--:--:--"])

    # Style data rows
    for row_idx in range(2, len(sample_symbols) + 2):
        for col_idx in range(1, len(headers) + 1):
            cell = ws_live.cell(row=row_idx, column=col_idx)
            cell.font = data_font
            cell.border = thin_border
            if col_idx in (1, 2):
                cell.alignment = left_align
            elif col_idx in (3, 4, 5, 6, 7, 8, 9):
                cell.alignment = right_align
                cell.number_format = "#,##0.00"
            elif col_idx == 10:
                cell.alignment = right_align
                cell.number_format = "#,##0"
            else:
                cell.alignment = center_align

    # Auto-adjust column widths
    column_widths = {
        "A": 16,  # Symbol
        "B": 24,  # Instrument Key
        "C": 14,  # LTP
        "D": 12,  # Change
        "E": 14,  # VWAP
        "F": 14,  # Open
        "G": 14,  # High
        "H": 14,  # Low
        "I": 14,  # Close
        "J": 16,  # Volume
        "K": 14,  # Updated At
    }
    for col_letter, width in column_widths.items():
        ws_live.column_dimensions[col_letter].width = width

    # Sheet 2: Watchlist
    ws_watch = wb.create_sheet(title="Watchlist")
    ws_watch.append(["Trading Symbol", "Status"])
    ws_watch.cell(row=1, column=1).font = header_font
    ws_watch.cell(row=1, column=1).fill = header_fill
    ws_watch.cell(row=1, column=2).font = header_font
    ws_watch.cell(row=1, column=2).fill = header_fill
    ws_watch.column_dimensions["A"].width = 20
    ws_watch.column_dimensions["B"].width = 15

    for sym, _ in sample_symbols:
        ws_watch.append([sym, "Active"])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    return output_path


if __name__ == "__main__":
    out = Path(__file__).parent / "Upstox_Live_Market.xlsx"
    generate_styled_template(out)
    print(f"Generated template at: {out}")
