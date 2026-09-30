from __future__ import annotations
import requests

class TindexError(RuntimeError):
    pass

class TindexProvider:
    BASE = "https://tindex.app/api/public"
    def __init__(self, api_key: str, timeout: int = 12):
        self.api_key = api_key.strip()
        self.timeout = timeout
    @property
    def available(self):
        return bool(self.api_key)
    def _get(self, path, params=None):
        if not self.available:
            raise TindexError("TINDEX_API_KEY is not configured")
        try:
            r = requests.get(self.BASE + path, params=params or {}, timeout=self.timeout,
                headers={"Authorization": f"Bearer {self.api_key}", "Accept": "application/json",
                         "User-Agent": "IranStock-Demo-Bot/1.0"})
            r.raise_for_status()
            payload = r.json()
        except (requests.RequestException, ValueError) as exc:
            raise TindexError(f"Tindex request failed: {exc}") from exc
        if not payload.get("success"):
            raise TindexError(str(payload.get("message") or "Tindex rejected request"))
        return payload.get("data")
    def resolve(self, symbol):
        data = self._get("/stocks/by-category/stock-energy", {"q": symbol, "per_page": 20})
        rows = data.get("rows", []) if isinstance(data, dict) else []
        exact = [r for r in rows if r.get("ticker") == symbol]
        row = exact[0] if exact else (rows[0] if rows else None)
        if not row:
            raise TindexError(f"Symbol not found: {symbol}")
        return row
    def history(self, slug, range_="3m"):
        data = self._get(f"/stocks/{slug}/history", {"range": range_})
        if not isinstance(data, dict):
            raise TindexError("Unexpected Tindex history response")
        return [{"date": d, "close": p} for d, p in zip(data.get("dates", []), data.get("points", []))]
    def detail(self, slug):
        data = self._get(f"/stocks/stock-energy/{slug}")
        if not isinstance(data, dict):
            raise TindexError("Unexpected Tindex detail response")
        return data
    @staticmethod
    def rial_to_toman(value):
        try:
            return float(value) / 10
        except (TypeError, ValueError):
            return 0.0
