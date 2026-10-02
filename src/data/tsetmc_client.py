from __future__ import annotations
import csv
import io
import time
import requests
from urllib.parse import quote
from src.config import Config


class TsetmcError(RuntimeError):
    pass


class TsetmcClient:
    BASES = (
        "https://cdn.tsetmc.com/api",
        "https://cdn10.tsetmc.com/api",
    )
    LEGACY_BASES = (
        "http://old.tsetmc.com/tsev2/data",
        "https://old.tsetmc.com/tsev2/data",
        "http://tsetmc.com/tsev2/data",
        "https://tsetmc.com/tsev2/data",
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

    def _legacy_get(self, path):
        last = None
        for base in self.LEGACY_BASES:
            try:
                r = self.session.get(
                    base + path,
                    timeout=max(self.config.request_timeout, 10),
                    headers={"Referer": "http://www.tsetmc.com/", **self.config.headers},
                )
                r.raise_for_status()
                text = r.text
                if not text.strip():
                    raise TsetmcError("legacy TSETMC returned empty response")
                self.active_base = base
                return text
            except requests.RequestException as exc:
                last = exc
                print(f"TSETMC legacy endpoint failed via {base}: {exc}")
        raise TsetmcError(str(last))

    def _unwrap(self, payload, key):
        if not isinstance(payload, dict):
            raise TsetmcError("Unexpected TSETMC response")
        return payload.get(key, [])

    def search(self, query):
        return self._unwrap(
            self._get("/Instrument/GetInstrumentSearch/" + quote(query, safe="")),
            "instrumentSearch",
        )

    def legacy_search(self, query):
        text = self._legacy_get("/search.aspx?skey=" + quote(query, safe=""))
        rows = []
        for raw in text.split(";"):
            raw = raw.strip()
            if not raw:
                continue
            fields = next(csv.reader([raw]), [])
            if len(fields) < 3:
                continue
            rows.append({
                "lVal18AFC": fields[0],
                "lVal30": fields[1],
                "insCode": fields[2],
                "flow": 0,
            })
        return rows

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

    def instrument_info(self, ins_code):
        return self._unwrap(
            self._get(f"/Instrument/GetInstrumentInfo/{ins_code}"),
            "instrumentInfo",
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

    def legacy_history(self, ins_code, limit=120):
        text = self._legacy_get(
            f"/Export-txt.aspx?t=i&a=1&b=0&i={quote(str(ins_code), safe='')}"
        )
        rows = []
        for line in text.replace("\r", "").split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                fields = next(csv.reader([line]))
            except csv.Error:
                continue
            if len(fields) < 12 or fields[1].lower() == "date":
                continue
            try:
                close = float(fields[5].replace(",", ""))
                volume = float(fields[7].replace(",", ""))
            except (ValueError, TypeError):
                continue
            rows.append({
                "dEven": fields[1],
                "pClosing": close,
                "qTotTran5J": volume,
                "pf": fields[2],
                "pMax": fields[3],
                "pMin": fields[4],
                "qTotCap": fields[6],
                "last": fields[11],
            })
        return rows[-limit:]

    def legacy_client_type(self, ins_code):
        try:
            text = self._legacy_get(
                f"/clienttype.aspx?i={quote(str(ins_code), safe='')}"
            )
        except TsetmcError:
            return []
        rows = []
        for line in text.replace("\r", "").split("\n"):
            fields = [x.strip() for x in line.split(",")]
            if len(fields) < 4:
                continue
            nums = []
            for x in fields:
                try:
                    nums.append(float(x))
                except ValueError:
                    nums.append(0.0)
            rows.append({
                "buy_I_Volume": nums[0] if len(nums) > 0 else 0,
                "buy_N_Volume": nums[1] if len(nums) > 1 else 0,
                "sell_I_Volume": nums[2] if len(nums) > 2 else 0,
                "sell_N_Volume": nums[3] if len(nums) > 3 else 0,
            })
        return rows[-1:] if rows else []

    def codal_prepared(self, ins_code, top=10):
        """Return recent Codal filing metadata for an instrument.

        This endpoint is used for discovery/freshness only. It does not
        pretend to contain audited financial-statement values.
        """
        return self._unwrap(
            self._get(f"/Codal/GetPreparedDataByInsCode/{int(top)}/{ins_code}"),
            "preparedData",
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

    def resolve_symbol_any(self, symbol):
        try:
            return self.resolve_symbol(symbol), "TSETMC"
        except TsetmcError as primary_exc:
            rows = self.legacy_search(symbol)
            if not rows:
                raise primary_exc
            return rows[0], "TSETMC-LEGACY"

    @staticmethod
    def rial_to_toman(value):
        try:
            return float(value) / 10
        except (TypeError, ValueError):
            return 0.0
