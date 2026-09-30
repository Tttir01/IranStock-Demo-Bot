from __future__ import annotations
import time
import requests
from urllib.parse import quote
from src.config import Config

class TsetmcError(RuntimeError): pass

class TsetmcClient:
    BASE="https://cdn.tsetmc.com/api"
    def __init__(self, config=None, session=None):
        self.config=config or Config(); self.session=session or requests.Session(); self.session.headers.update(self.config.headers)
    def _get(self,path):
        last=None
        for attempt in range(self.config.retries+1):
            try:
                r=self.session.get(self.BASE+path,timeout=self.config.request_timeout)
                if r.status_code in (429,500,502,503,504): raise TsetmcError(f"temporary HTTP {r.status_code}")
                if r.status_code in (401,403): raise TsetmcError(f"TSETMC access blocked: HTTP {r.status_code}")
                r.raise_for_status()
                if any(x in r.text for x in ("مسدود","دسترسی شما","General Error Detected")): raise TsetmcError("TSETMC access appears blocked")
                return r.json()
            except (requests.RequestException,ValueError,TsetmcError) as exc:
                last=exc
                if attempt<self.config.retries: time.sleep(0.8*(2**attempt))
        raise TsetmcError(str(last))
    @staticmethod
    def _unwrap(payload,key):
        if not isinstance(payload,dict): raise TsetmcError("Unexpected TSETMC response")
        return payload.get(key,[])
    def search(self,query): return self._unwrap(self._get("/Instrument/GetInstrumentSearch/"+quote(query,safe="")),"instrumentSearch")
    def quote(self,ins_code): return self._unwrap(self._get(f"/ClosingPrice/GetClosingPriceInfo/{ins_code}"),"closingPriceInfo")
    def history(self,ins_code,top=120): return self._unwrap(self._get(f"/ClosingPrice/GetClosingPriceDailyList/{ins_code}/{top}"),"closingPriceDaily")
    def order_book(self,ins_code): return self._unwrap(self._get(f"/BestLimits/{ins_code}"),"bestLimits")
    def client_type(self,ins_code): return self._unwrap(self._get(f"/ClientType/GetClientType/{ins_code}/1/0"),"clientType")
    def resolve_symbol(self,symbol):
        rows=self.search(symbol)
        if not rows: raise TsetmcError(f"Symbol not found: {symbol}")
        return rows[0]
    @staticmethod
    def rial_to_toman(value):
        try: return float(value)/10.0
        except (TypeError,ValueError): return 0.0
