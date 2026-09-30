from dataclasses import dataclass,field
@dataclass
class Position:
    symbol:str; quantity:int; entry:float; stop_loss:float; take_profit:float
@dataclass
class PaperAccount:
    cash:float=100_000_000; positions:dict=field(default_factory=dict); trades:list=field(default_factory=list)
    def buy(self,symbol,price,quantity,stop_loss_pct=.04,take_profit_pct=.08):
        cost=price*quantity
        if quantity<=0 or cost>self.cash:return False
        self.cash-=cost; self.positions[symbol]=Position(symbol,quantity,price,price*(1-stop_loss_pct),price*(1+take_profit_pct)); return True
    def sell(self,symbol,price):
        p=self.positions.pop(symbol,None)
        if not p:return None
        self.cash+=price*p.quantity; pnl=(price-p.entry)*p.quantity; self.trades.append({"symbol":symbol,"entry":p.entry,"exit":price,"quantity":p.quantity,"pnl":pnl}); return pnl
    def equity(self,prices): return self.cash+sum(p.quantity*float(prices.get(s,p.entry)) for s,p in self.positions.items())
