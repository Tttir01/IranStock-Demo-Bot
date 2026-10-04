from src.broker.agah import AgahBroker, OrderRequest


def test_agah_dry_run_never_sends_live_order(monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "DRY_RUN")
    broker = AgahBroker()
    result = broker.submit_order(OrderRequest("فولاد", "BUY", 100, 1000))
    assert result["ok"] is True
    assert result["status"] == "DRY_RUN"
    assert result["broker"] == "AGAH"


def test_agah_live_is_blocked(monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "LIVE")
    broker = AgahBroker()
    result = broker.submit_order(OrderRequest("فولاد", "BUY", 100, 1000))
    assert result["ok"] is False
    assert result["status"] == "BLOCKED"
