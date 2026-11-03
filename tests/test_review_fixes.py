"""Regression tests for the review fixes (dashboard contract, validation, ratio)."""

from pathlib import Path

from src.analysis.scanner import analyze_symbol
from src.analysis.screener import market_rows
from src.main import _build_payload
from src.telegram_bot import split_message
from src.trading.paper_account import PaperAccount


class _StubClient:
    """Minimal TSETMC stand-in; every price is in rial like the real API."""

    def __init__(self, flow):
        self._flow = flow

    def resolve_symbol(self, symbol):
        return {"insCode": "123", "lVal18AFC": symbol}

    def history(self, ins_code, top=120):
        return [
            {"pClosing": 10_000 + i * 10, "qTotTran5J": 1_000 + i} for i in range(40)
        ]

    def instrument_info(self, ins_code):
        raise RuntimeError("fundamentals unavailable in this stub")

    def codal_prepared(self, ins_code, top=10):
        return []

    def client_type(self, ins_code):
        return [self._flow]

    @staticmethod
    def rial_to_toman(value):
        return float(value) / 10


class _StubCfg:
    min_score = 80
    max_symbols = 10
    symbols = ("فولاد",)
    trading_mode = "DRY_RUN"


def test_buy_rejects_non_positive_price():
    account = PaperAccount(cash=1_000)
    assert account.buy("TEST", -5, 100) is False
    assert account.buy("TEST", 0, 100) is False
    assert account.cash == 1_000
    assert account.positions == {}


def test_buy_rejects_non_positive_quantity():
    account = PaperAccount(cash=1_000)
    assert account.buy("TEST", 10, 0) is False
    assert account.buy("TEST", 10, -3) is False
    assert account.cash == 1_000


def test_sell_with_invalid_price_keeps_position():
    account = PaperAccount(cash=1_000)
    assert account.buy("TEST", 10, 50)
    assert account.sell("TEST", 0) is None
    assert "TEST" in account.positions
    assert account.cash == 500


def test_halted_symbol_is_not_a_minus_100_percent_mover():
    rows = market_rows(
        [
            {"lVal18AFC": "ح", "pl": 0, "pc": 5_000, "py": 5_000, "qTotTran5J": 0},
            {"lVal18AFC": "ب", "pl": 5_500, "pc": 5_500, "py": 5_000, "qTotTran5J": 10},
        ]
    )
    by_symbol = {r["symbol"]: r for r in rows}
    assert by_symbol["ح"]["change_pct"] == 0
    assert by_symbol["ح"]["last_toman"] == 500
    assert round(by_symbol["ب"]["change_pct"], 2) == 10.0


def test_real_buy_ratio_compares_real_buys_with_real_sells():
    flow = {
        "buy_I_Volume": 900,
        "buy_N_Volume": 100,
        "sell_I_Volume": 300,
        "sell_N_Volume": 700,
    }
    result = analyze_symbol("فولاد", _StubClient(flow), None, None, _StubCfg())
    assert result["provider"] == "TSETMC"
    assert result["flow"]["real_buy_ratio"] == 0.75
    # Retail share of total buys is reported separately and stays 0.9.
    assert result["flow"]["retail_share"] == 0.9


def test_real_buy_ratio_falls_back_when_sell_side_missing():
    flow = {"buy_I_Volume": 60, "buy_N_Volume": 40}
    result = analyze_symbol("فولاد", _StubClient(flow), None, None, _StubCfg())
    assert result["flow"]["real_buy_ratio"] == 0.6


def test_dashboard_payload_matches_frontend_contract():
    results = [
        {
            "symbol": "فولاد",
            "provider": "TSETMC",
            "price": 2_900,
            "signal": {"score": 72, "action": "WATCH", "reasons": ["r"]},
            "flow": {"real_buy_ratio": 0.6},
        },
        {
            "symbol": "فملی",
            "provider": "UNAVAILABLE",
            "price": 0,
            "signal": {"score": 0, "action": "UNAVAILABLE", "reasons": ["x"]},
        },
    ]
    snap = PaperAccount(cash=1_000).snapshot()

    payload = _build_payload(results, [], snap, [], [], _StubCfg())

    assert set(payload) >= {
        "summary",
        "scan_results",
        "actions",
        "paper",
        "top_gainers",
        "top_volume",
    }
    summary = payload["summary"]
    assert summary["scanned"] == 2
    assert summary["available"] == 1
    assert summary["top_score"] == 72
    assert summary["min_score"] == 80
    assert summary["mode"]

    paper = payload["paper"]
    for key in (
        "equity",
        "cash",
        "realized_pnl",
        "max_drawdown_pct",
        "open_positions",
        "trades",
        "positions",
    ):
        assert key in paper

    html = Path("dashboard/index.html").read_text(encoding="utf-8")
    assert "scan_results" in html
    # The old template read a single-symbol payload that is no longer written.
    assert "summary.price_toman" not in html
    assert "d.signal" not in html


def test_split_message_respects_telegram_limit():
    lines = [f"خط شماره {i} با متن نمونه برای آزمون تقسیم پیام" for i in range(300)]
    text = "\n".join(lines)

    chunks = split_message(text, limit=1000)

    assert len(chunks) > 1
    assert all(len(chunk) <= 1000 for chunk in chunks)
    assert "".join(chunks) == text
    # No chunk may start mid-line of another chunk.
    for chunk in chunks:
        assert chunk.startswith("خط شماره") or chunk == ""


def test_split_message_keeps_short_text_single_chunk():
    assert split_message("سلام") == ["سلام"]
    assert split_message("") == [""]
