from __future__ import annotations

from urllib.parse import quote

import requests


class TindexError(RuntimeError):
    pass


class TindexProvider:
    """Tindex public API provider using the current stock-market endpoints."""

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

    def market_data(self, symbol: str, range_: str = "3m"):
        """
        Fetch the current stock price series using the current Tindex endpoint.

        The current API accepts the Persian ticker directly here:
        /api/public/stock-market/symbol/{slug}/candles

        One API call is deliberately used per run because the free Tindex plan
        is rate-limited to one request per minute.
        """
        slug = quote(symbol.strip(), safe="")
        data = self._get(
            f"/stock-market/symbol/{slug}/candles",
            {"range": range_, "interval": "daily"},
        )
        if not isinstance(data, dict):
            raise TindexError("Unexpected Tindex candles response")

        closes = data.get("c") or []
        timestamps = data.get("t") or []
        if len(closes) < 30:
            raise TindexError(
                f"Tindex returned insufficient history for {symbol}: {len(closes)} points"
            )

        dates = []
        previous = 0
        for raw in timestamps:
            try:
                value = int(raw)
            except (TypeError, ValueError):
                value = 0
            # Tindex delta-encodes timestamps from the second element onward.
            if dates:
                value += previous
            previous = value
            dates.append(str(value))

        history = [
            {
                "dEven": dates[i] if i < len(dates) else "",
                "pClosing": closes[i],
                "qTotTran5J": 0,
            }
            for i in range(len(closes))
        ]

        return {
            "symbol": symbol,
            "slug": data.get("slug") or symbol,
            "unit": data.get("unit") or "ریال",
            "history": history,
            "flow": [],
            "source": data.get("source") or "Tindex",
        }

    # Compatibility helpers for older callers. New code should use market_data().
    def resolve(self, symbol):
        raise TindexError(
            "Tindex stock screener endpoint was replaced; use market_data()"
        )

    def history(self, slug, range_="3m"):
        encoded = quote(str(slug), safe="")
        data = self._get(
            f"/stock-market/symbol/{encoded}/candles",
            {"range": range_, "interval": "daily"},
        )
        if not isinstance(data, dict):
            raise TindexError("Unexpected Tindex candles response")
        closes = data.get("c") or []
        return [{"close": value} for value in closes]

    def detail(self, slug):
        encoded = quote(str(slug), safe="")
        data = self._get(f"/stock-market/symbol/{encoded}/overview")
        if not isinstance(data, dict):
            raise TindexError("Unexpected Tindex overview response")
        return data

    @staticmethod
    def rial_to_toman(value):
        try:
            return float(value) / 10
        except (TypeError, ValueError):
            return 0.0
