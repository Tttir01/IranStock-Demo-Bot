from src.analysis.signal_engine import score_signal
def test_signal_returns_valid_range():
    prices=[100+i*.8 for i in range(60)]; result=score_signal(prices,[1000]*60)
    assert 0<=result["score"]<=100
    assert result["action"] in {"BUY","WATCH","NO_TRADE"}
