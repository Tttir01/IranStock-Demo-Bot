from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path


@dataclass
class Position:
    symbol: str
    quantity: int
    entry: float
    stop_loss: float
    take_profit: float


@dataclass
class PaperAccount:
    cash: float = 100_000_000
    positions: dict = field(default_factory=dict)
    trades: list = field(default_factory=list)
    peak_equity: float = 100_000_000
    max_drawdown: float = 0.0

    def buy(self, symbol, price, quantity, stop_loss_pct=.04, take_profit_pct=.08):
        price = float(price)
        quantity = int(quantity)
        cost = price * quantity
        if quantity <= 0 or cost > self.cash or symbol in self.positions:
            return False
        self.cash -= cost
        self.positions[symbol] = Position(
            symbol,
            quantity,
            price,
            price * (1 - stop_loss_pct),
            price * (1 + take_profit_pct),
        )
        return True

    def sell(self, symbol, price, reason="SIGNAL"):
        p = self.positions.pop(symbol, None)
        if not p:
            return None
        price = float(price)
        self.cash += price * p.quantity
        pnl = (price - p.entry) * p.quantity
        self.trades.append(
            {
                "time": datetime.now(timezone.utc).isoformat(),
                "symbol": symbol,
                "entry": p.entry,
                "exit": price,
                "quantity": p.quantity,
                "pnl": pnl,
                "reason": reason,
            }
        )
        return pnl

    def equity(self, prices):
        return self.cash + sum(
            p.quantity * float(prices.get(s, p.entry))
            for s, p in self.positions.items()
        )

    def update_risk(self, prices):
        eq = self.equity(prices)
        self.peak_equity = max(self.peak_equity, eq)
        drawdown = (
            (self.peak_equity - eq) / self.peak_equity
            if self.peak_equity
            else 0
        )
        self.max_drawdown = max(self.max_drawdown, drawdown)
        return eq

    def snapshot(self, prices=None):
        prices = prices or {}
        equity = self.update_risk(prices)
        positions = {
            symbol: {
                "quantity": p.quantity,
                "entry": p.entry,
                "stop_loss": p.stop_loss,
                "take_profit": p.take_profit,
                "market_value": p.quantity * float(prices.get(symbol, p.entry)),
            }
            for symbol, p in self.positions.items()
        }
        return {
            "cash": self.cash,
            "equity": equity,
            "open_positions": len(self.positions),
            "positions": positions,
            "realized_pnl": sum(t["pnl"] for t in self.trades),
            "trades": len(self.trades),
            "max_drawdown_pct": self.max_drawdown * 100,
        }

    def save(self, path="data/paper-account.json"):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "cash": self.cash,
            "peak_equity": self.peak_equity,
            "max_drawdown": self.max_drawdown,
            "positions": {s: vars(v) for s, v in self.positions.items()},
            "trades": self.trades,
        }
        p.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path="data/paper-account.json", initial_cash=100_000_000):
        p = Path(path)
        if not p.exists():
            return cls(cash=initial_cash, peak_equity=initial_cash)

        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            # A corrupt state must not stop the whole demo bot.
            return cls(cash=initial_cash, peak_equity=initial_cash)

        a = cls(
            cash=float(d.get("cash", initial_cash)),
            peak_equity=float(d.get("peak_equity", initial_cash)),
            max_drawdown=float(d.get("max_drawdown", 0)),
        )
        a.trades = d.get("trades", [])
        for symbol, value in d.get("positions", {}).items():
            try:
                a.positions[symbol] = Position(**value)
            except (TypeError, ValueError):
                continue
        return a
