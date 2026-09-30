from __future__ import annotations
import time, requests
from urllib.parse import quote
from src.config import Config

class TsetmcError(RuntimeError):
    pass

class TsetmcClient:
    BASES = (
        "https://cdn.tsetmc.com/api",
        "https://cdn10.tsetmc.com/api",
    )

    def __init__(self, config=None, session=None):
        self.config = config or Config()
        self.session = session or requests.Session()
        self.session.headers.update(self.config.headers)
        self.active_base = None

    def _get(self, path):
        last = None
        for base in self.BASES:
            for attempt in range(self.config.retries + 1):
                try:
                    r = self.session.get(
                        base + path,
                        timeout=self.config.request_timeout,
                    )
                    if r.status_code in (429, 500, 502, 503, 504):
                        raise TsetmcError(f"temporary HTTP {r.status_code}")
                    if r.status_code in (401, 403):
                        raise TsetmcError(f"TSETMC access blocked: HTTP {r.status_code}")
                    r.raise_for_status()
                    if any(x in r.text for x in ("مسدود", "دسترسی شما", "General Error Detected")):
                        raise TsetmcError("TSETMC access appears blocked")
                    payload = r.json()
                    self.active_base = base
                    return payload
                except (requests.RequestException, ValueError, TsetmcError) as exc:
                    last = exc
                    if attempt < self.config.retries:
                        time.sleep(0.8 * (2 ** attempt))
            print(f"TSETMC endpoint failed via {base}: {last}")
        raise TsetmcError(str(last))

    @staticmethod
    def _unwrap(payload, key):
        if not isinstance(payload, dict):
            raise TsetmcError("Unexpected TSETMC response")
        return payload.get(key, [])

    def search(self, query):
        return self._unwrap(
            self._get("/Instrument/GetInstrumentSearch/" + quote(query, safe="")),
            "instrumentSearch",
        )

    def market_watch(self):
        return self._unwrap(
            self._get(
                "/ClosingPrice/GetMarketWatch?market=0"
                "&paperTypes[0]=1&paperTypes[1]=2&paperTypes[2]=3"
                "&paperTypes[3]=4&paperTypes[4]=5&paperTypes[5]=6"
                "&paperTypes[6]=7&paperTypes[7]=8&paperTypes[8]=9"
                "&withBestLimits=false&hEven=0&RefID=0"
            ),
            "marketwatch",
        )

    def quote(self, ins_code):
        return self._unwrap(
            self._get(f"/ClosingPrice/GetClosingPriceInfo/{ins_code}"),
            "closingPriceInfo",
        )

    def history(self, ins_code, top=120):
        return self._unwrap(
            self._get(f"/ClosingPrice/GetClosingPriceDailyList/{ins_code}/{top}"),
            "closingPriceDaily",
        )

    def order_book(self, ins_code):
        return self._unwrap(self._get(f"/BestLimits/{ins_code}"), "bestLimits")

    def client_type(self, ins_code):
        return self._unwrap(
            self._get(f"/ClientType/GetClientType/{ins_code}/1/0"),
            "clientType",
        )

    def client_type_all(self):
        return self._unwrap(
            self._get("/ClientType/GetClientTypeAll"),
            "clientTypeAllDto",
        )

    def market_overview(self, flow=0):
        return self._unwrap(
            self._get(f"/MarketData/GetMarketOverview/{flow}"),
            "marketOverview",
        )

    def resolve_symbol(self, symbol):
        rows = self.search(symbol)
        if not rows:
            raise TsetmcError(f"Symbol not found: {symbol}")
        return rows[0]

    @staticmethod
    def rial_to_toman(value):
        try:
            return float(value) / 10
        except (TypeError, ValueError):
            return 0.0
