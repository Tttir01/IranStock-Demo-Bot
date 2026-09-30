import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Config:
    initial_cash: float = float(os.getenv("PAPER_INITIAL_CASH", "100000000"))
    symbol: str = os.getenv("PAPER_SYMBOL", "فولاد")
    max_position_pct: float = float(os.getenv("MAX_POSITION_PCT", "0.20"))
    stop_loss_pct: float = float(os.getenv("STOP_LOSS_PCT", "0.04"))
    take_profit_pct: float = float(os.getenv("TAKE_PROFIT_PCT", "0.08"))
    min_score: int = int(os.getenv("MIN_SIGNAL_SCORE", "80"))
    request_timeout: int = int(os.getenv("TSETMC_TIMEOUT", "8"))
    retries: int = int(os.getenv("TSETMC_RETRIES", "1"))
    telegram_enabled: bool = os.getenv("TELEGRAM_ENABLED", "true").lower() == "true"
    @property
    def headers(self):
        return {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36","Accept":"application/json,text/plain,*/*","Referer":"https://www.tsetmc.com/","Origin":"https://www.tsetmc.com"}
