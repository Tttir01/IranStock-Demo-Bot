from src.trading.paper_account import PaperAccount
def test_buy_sell_profit():
    a=PaperAccount(cash=100000); assert a.buy("TEST",100,500); assert a.sell("TEST",110)==5000; assert a.cash==105000
