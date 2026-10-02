from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path
from urllib.parse import quote

import requests


class TindexError(RuntimeError):
    pass


class TindexProvider:
    """Tindex provider with API-first and website-history fallback.

    Tindex changed its public stock API surface; the older
    /api/public/stocks/by-category/... route now returns HTTP 410.
    The public stock pages remain available and expose daily history.
    """

    BASE = "https://tindex.app/api/public"
    WEB_BASE = "https://tindex.app/stocks"
    CACHE_FILE = Path("data/tindex-symbols.json")

    def __init__(self, api_key: str, timeout: int = 12):
        self.api_key = api_key.strip()
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json,text/html",
                "User-Agent": "IranStock-Demo-Bot/2.0",
            }
        )

    @property
    def available(self):
        return bool(self.api_key)

    def _get(self, path, params=None):
        if not self.available:
            raise TindexError("TINDEX_API_KEY is not configured")
        try:
            response = self.session.get(
                self.BASE + path,
                params=params or {},
                timeout=self.timeout,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Accept": "application/json",
                    "User-Agent": "IranStock-Demo-Bot/2.0",
                },
            )
            if response.status_code == 410:
                raise TindexError(
                    "Tindex stock API route was retired (HTTP 410); "
                    "using public stock-page history fallback"
                )
            response.raise_for_status()
            payload = response.json()
        except TindexError:
            raise
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

    @staticmethod
    def _parse_history_html(html):
        """Extract date/open/high/low/close rows from Tindex history HTML."""
        html = unescape(html)
        rows = []

        # The public history table contains five numeric columns after date:
        # Open, High, Low, Close, Change. Ignore rows containing dashes.
        row_pattern = re.compile(
            r"<tr[^>]*>\\s*"
            r"<td[^>]*>(.*?)</td>\\s*"
            r"<td[^>]*>(.*?)</td>\\s*"
            r"<td[^>]*>(.*?)</td>\\s*"
            r"<td[^>]*>(.*?)</td>\\s*"
            r"<td[^>]*>(.*?)</td>\\s*"
            r"<td[^>]*>(.*?)</td>",
            re.I | re.S,
        )

        def clean(value):
            value = re.sub(r"<[^>]+>", "", value)
            value = value.replace("\u066c", "").replace(",", "").strip()
            value = value.replace("−", "-")
            return value

        for match in row_pattern.finditer(html):
            cells = [clean(x) for x in match.groups()]
            if len(cells) < 6:
                continue
            date_text = cells[0]
            if not re.search(r"\\d", date_text):
                continue
            try:
                o = float(cells[1])
                h = float(cells[2])
                low = float(cells[3])
                close = float(cells[4])
            except ValueError:
                continue
            rows.append(
                {
                    "dEven": date_text,
                    "open": o,
                    "high": h,
                    "low": low,
                    "close": close,
                    "pClosing": close,
                    "qTotTran5J": 0,
                }
            )
        return rows

    def _web_history(self, symbol, pages=8):
        """Fetch enough public history pages to provide >=30 daily closes."""
        symbol = symbol.strip()
        all_rows = []
        seen = set()

        for page in range(1, pages + 1):
            url = f"{self.WEB_BASE}/{quote(symbol, safe='')}/history/"
            params = {} if page == 1 else {"page": page}
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
                response.raise_for_status()
            except requests.RequestException as exc:
                raise TindexError(
                    f"Tindex public stock page failed for {symbol}: {exc}"
                ) from exc

            parsed = self._parse_history_html(response.text)
            if not parsed:
                break

            before = len(all_rows)
            for row in parsed:
                key = (row["dEven"], row["pClosing"])
                if key not in seen:
                    seen.add(key)
                    all_rows.append(row)

            if len(all_rows) == before or len(all_rows) >= 120:
                break

        if len(all_rows) < 30:
            raise TindexError(
                f"Tindex public history returned only {len(all_rows)} usable rows for {symbol}"
            )

        return all_rows[-120:]

    def resolve(self, symbol):
        """Resolve ticker to its current public Tindex stock URL slug.

        Tindex public stock URLs currently use the Persian ticker directly,
        so no API quota request is needed for resolution.
        """
        symbol = symbol.strip()
        cached = self._load_slugs().get(symbol)
        if cached:
            return cached

        url = f"{self.WEB_BASE}/{quote(symbol, safe='')}/"
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise TindexError(f"Tindex stock not found: {symbol}") from exc

        if f"{symbol}" not in response.text:
            raise TindexError(f"Tindex stock not found: {symbol}")

        cache = self._load_slugs()
        cache[symbol] = symbol
        self._save_slugs(cache)
        return symbol

    def market_data(self, symbol: str, range_: str = "3m"):
        symbol = symbol.strip()
        slugs = self._load_slugs()
        slug = slugs.get(symbol) or self.resolve(symbol)

        # Current Tindex stock API route used by the old implementation is
        # retired. Use the public history page, whose data source is Tsetmc.
        history = self._web_history(slug)
        return {
            "symbol": symbol,
            "slug": str(slug),
            "unit": "ریال",
            "history": history,
            "flow": [],
            "source": "Tindex public stock page / Tsetmc",
        }

    def history(self, slug, range_="3m"):
        return self._web_history(str(slug))

    def detail(self, slug):
        encoded = quote(str(slug), safe="")
        return self._get(f"/indicators/stock-energy/{encoded}")

    @staticmethod
    def rial_to_toman(value):
        try:
            return float(value) / 10
        except (TypeError, ValueError):
            return 0.0
