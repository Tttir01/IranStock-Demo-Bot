from src.analysis.signal_engine import score_signal
from src.trading.paper_account import PaperAccount


def test_signal_returns_valid_range():
    prices = [100 + i * 0.8 for i in range(60)]
    result = score_signal(prices, [1000] * 60)
    assert 0 <= result["score"] <= 100
    assert result["action"] in {"BUY", "WATCH", "NO_TRADE"}


def test_signal_honors_custom_threshold():
    prices = [100 + i * 0.8 for i in range(60)]
    result = score_signal(prices, [1000] * 60, min_score=95)
    assert result["action"] != "BUY"


def test_paper_snapshot_contains_positions():
    account = PaperAccount(cash=100_000)
    assert account.buy("TEST", 100, 500)
    snapshot = account.snapshot({"TEST": 105})
    assert snapshot["open_positions"] == 1
    assert snapshot["positions"]["TEST"]["quantity"] == 500
    assert snapshot["positions"]["TEST"]["market_value"] == 52_500


def test_buy_sell_profit():
    account = PaperAccount(cash=100_000)
    assert account.buy("TEST", 100, 500)
    assert account.sell("TEST", 110) == 5_000
    assert account.cash == 105_000
