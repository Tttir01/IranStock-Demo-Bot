from __future__ import annotations

import requests
from urllib.parse import quote


class ProviderError(RuntimeError):
    pass


class BrsApiProvider:
    """Optional fallback provider. Requires BRS_API_KEY."""

    BASE = "https://Api.BrsApi.ir/Tsetmc/History.php"

    def __init__(self, api_key: str, timeout: int = 10):
        self.api_key = api_key.strip()
        self.timeout = timeout

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def _get(self, symbol: str, data_type: int):
        if not self.available:
            raise ProviderError("BRS_API_KEY is not configured")
        try:
            response = requests.get(
                self.BASE,
                params={"key": self.api_key, "type": data_type, "l18": symbol},
                timeout=self.timeout,
                headers={"User-Agent": "IranStock-Demo-Bot/1.0"},
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ProviderError(f"BrsApi request failed: {exc}") from exc

        if isinstance(payload, dict):
            for key in ("data", "result", "history", "items"):
                if isinstance(payload.get(key), list):
                    return payload[key]
            if payload.get("status") is False:
                raise ProviderError(str(payload.get("message") or "BrsApi rejected request"))
        if isinstance(payload, list):
            return payload
        raise ProviderError("Unexpected BrsApi response")

    def history(self, symbol: str, limit: int = 120):
        rows = self._get(symbol, 0)
        return rows[-limit:]

    def client_type(self, symbol: str):
        rows = self._get(symbol, 1)
        return rows[-1:] if rows else []
