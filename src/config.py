import os
from dataclasses import dataclass


def _symbols():
    raw = os.getenv("PAPER_SYMBOLS", os.getenv("PAPER_SYMBOL", "فولاد"))
    return tuple(dict.fromkeys(x.strip() for x in raw.split(",") if x.strip()))


@dataclass(frozen=True)
class Config:
    initial_cash: float = float(os.getenv("PAPER_INITIAL_CASH", "100000000"))
    symbol: str = os.getenv("PAPER_SYMBOL", "فولاد")
    symbols: tuple = _symbols()
    max_symbols: int = int(os.getenv("MAX_SCAN_SYMBOLS", "10"))
    max_position_pct: float = float(os.getenv("MAX_POSITION_PCT", "0.20"))
    stop_loss_pct: float = float(os.getenv("STOP_LOSS_PCT", "0.04"))
    take_profit_pct: float = float(os.getenv("TAKE_PROFIT_PCT", "0.08"))
    min_score: int = int(os.getenv("MIN_SIGNAL_SCORE", "80"))
    request_timeout: int = int(os.getenv("TSETMC_TIMEOUT", "8"))
    retries: int = int(os.getenv("TSETMC_RETRIES", "1"))
    brs_api_key: str = os.getenv("BRS_API_KEY", "")
    brs_api_timeout: int = int(os.getenv("BRS_API_TIMEOUT", "10"))
    tindex_api_key: str = os.getenv("TINDEX_API_KEY", "")
    tindex_api_timeout: int = int(os.getenv("TINDEX_API_TIMEOUT", "12"))
    telegram_enabled: bool = os.getenv("TELEGRAM_ENABLED", "true").lower() == "true"
    trading_mode: str = os.getenv("TRADING_MODE", "PAPER").upper()

    @property
    def headers(self):
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept": "application/json,text/plain,*/*",
            "Referer": "https://www.tsetmc.com/",
            "Origin": "https://www.tsetmc.com",
        }
