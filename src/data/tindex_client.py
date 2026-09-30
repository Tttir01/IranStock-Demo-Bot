from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

import requests


class TindexError(RuntimeError):
    pass


class TindexProvider:
    """Tindex public API provider for Tehran Stock Exchange data."""

    BASE = "https://tindex.app/api/public"
    CACHE_FILE = Path("data/tindex-symbols.json")

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
            response = requests.get(
                self.BASE + path,
                params=params or {},
                timeout=self.timeout,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Accept": "application/json",
                    "User-Agent": "IranStock-Demo-Bot/1.0",
                },
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise TindexError(f"Tindex request failed: {exc}") from exc

        if not isinstance(payload, dict) or not payload.get("success"):
            message = (
                payload.get("message")
                if isinstance(payload, dict)
                else "Invalid Tindex response"
            )
            raise TindexError(str(message or "Tindex rejected request"))
        return payload.get("data")

    def _load_slugs(self):
        try:
            if self.CACHE_FILE.exists():
                data = json.loads(self.CACHE_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except (OSError, ValueError):
            pass
        return {}

    def _save_slugs(self, data):
        try:
            self.CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            self.CACHE_FILE.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            raise TindexError(f"Could not save Tindex symbol cache: {exc}") from exc

    def resolve(self, symbol):
        """Resolve Persian ticker to Tindex stock slug.

        This consumes one API request. The result is persisted so later runs
        can use the one-request-per-minute free-plan quota for history only.
        """
        symbol = symbol.strip()
        cached = self._load_slugs().get(symbol)
        if cached:
            return cached

        data = self._get(
            "/stocks/by-category/stock-energy",
            {"q": symbol, "page": 1, "per_page": 20},
        )
        rows = data if isinstance(data, list) else (data or {}).get("rows", [])
        if not isinstance(rows, list):
            rows = []

        exact = None
        for row in rows:
            if not isinstance(row, dict):
                continue
            ticker = str(row.get("ticker") or row.get("symbol") or "").strip()
            name = str(row.get("name") or "").strip()
            if ticker == symbol or symbol == name:
                exact = row
                break

        exact = exact or (rows[0] if rows else None)
        if not exact:
            raise TindexError(f"Tindex stock not found: {symbol}")

        slug = exact.get("slug")
        if not slug:
            raise TindexError(f"Tindex returned no slug for stock: {symbol}")

        cache = self._load_slugs()
        cache[symbol] = str(slug)
        self._save_slugs(cache)
        return str(slug)

    def market_data(self, symbol: str, range_: str = "3m"):
        """Fetch stock history using the documented stock slug endpoint."""
        symbol = symbol.strip()
        slugs = self._load_slugs()
        slug = slugs.get(symbol)

        if not slug:
            slug = self.resolve(symbol)
            raise TindexError(
                f"Tindex symbol resolved to {slug}; history will be fetched on the next run "
                "to respect the free-plan one-request-per-minute limit"
            )

        data = self._get(
            f"/stocks/{quote(str(slug), safe='')}/history",
            {"range": range_},
        )
        if not isinstance(data, dict):
            raise TindexError("Unexpected Tindex stock history response")

        closes = data.get("points") or data.get("prices") or data.get("close") or []
        dates = data.get("dates") or []
        if not isinstance(closes, list) or len(closes) < 30:
            raise TindexError(
                f"Tindex returned insufficient history for {symbol}: {len(closes) if isinstance(closes, list) else 0} points"
            )

        history = []
        for i, close in enumerate(closes):
            history.append(
                {
                    "dEven": str(dates[i]) if i < len(dates) else "",
                    "pClosing": close,
                    "qTotTran5J": 0,
                }
            )

        return {
            "symbol": symbol,
            "slug": str(slug),
            "unit": data.get("unit") or "تومان",
            "history": history,
            "flow": [],
            "source": data.get("source") or "Tindex",
        }

    def history(self, slug, range_="3m"):
        data = self._get(
            f"/stocks/{quote(str(slug), safe='')}/history",
            {"range": range_},
        )
        if not isinstance(data, dict):
            raise TindexError("Unexpected Tindex stock history response")
        closes = data.get("points") or data.get("prices") or data.get("close") or []
        return [{"close": value} for value in closes]

    def detail(self, slug):
        encoded = quote(str(slug), safe="")
        return self._get(f"/stocks/{encoded}")

    @staticmethod
    def rial_to_toman(value):
        try:
            return float(value) / 10
        except (TypeError, ValueError):
            return 0.0
