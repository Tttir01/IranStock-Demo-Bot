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


def test_signal_contains_full_analysis():
    prices = [100 + i * 0.5 for i in range(80)]
    volumes = [1000] * 79 + [1500]
    result = score_signal(prices, volumes, min_score=80)
    assert "trend" in result
    assert "rsi" in result
    assert "macd" in result
    assert "volume_ratio" in result
    assert "breakdown" in result
    assert set(result["breakdown"]) == {
        "base",
        "trend",
        "trend_strength",
        "macd",
        "rsi",
        "volume",
        "flow",
        "rsi_divergence",
        "macd_divergence",
        "reversal_confirmation",
    }
    assert 0 <= result["trend_strength"] <= 100
    assert result["rsi_divergence"] in {"none", "bullish", "bearish"}
    assert result["macd_divergence"] in {"none", "bullish", "bearish"}
    assert result["volume_ratio"] is not None


def test_signal_explains_missing_flow():
    prices = [100 + i * 0.5 for i in range(80)]
    result = score_signal(prices, [1000] * 80, None)
    assert any("حقیقی/حقوقی" in reason for reason in result["reasons"])


def test_oversold_alone_does_not_add_rsi_points():
    prices = [
        100, 99, 98, 97, 96, 95, 94, 93, 92, 91,
        90, 89, 88, 87, 86, 85, 84, 83, 82, 81,
        80, 79, 78, 77, 76, 75, 74, 73, 72, 71,
        70, 69, 68, 67, 66, 65, 64, 63, 62, 61,
    ]
    result = score_signal(prices, [None] * len(prices), None)
    assert result["rsi"] < 30
    assert result["breakdown"]["rsi"] == 0
    assert result["reversal_confirmation"] is False


def test_missing_volume_is_not_reported_as_zero():
    prices = [100 + i * 0.3 for i in range(60)]
    result = score_signal(prices, [0] * 60, None)
    assert result["volume"] is None
    assert result["avg_volume_20"] is None
    assert result["volume_ratio"] is None
