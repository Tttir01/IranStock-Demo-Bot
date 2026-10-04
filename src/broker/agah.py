from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: str
    quantity: int
    price: float


class AgahBroker:
    """
    Safe broker adapter for Agah.

    The current integration is intentionally DRY_RUN-only until an official
    authenticated Agah trading API endpoint is provided. It never submits an
    order to Agah.
    """

    name = "AGAH"

    def __init__(self, mode: str | None = None):
        self.mode = (mode or os.getenv("TRADING_MODE", "PAPER")).upper()
        self.api_key = os.getenv("AGAH_API_KEY", "").strip()
        self.api_secret = os.getenv("AGAH_API_SECRET", "").strip()
        self.account_id = os.getenv("AGAH_ACCOUNT_ID", "").strip()

    @property
    def configured(self) -> bool:
        return bool(self.api_key or self.api_secret or self.account_id)

    def submit_order(self, order: OrderRequest) -> dict[str, Any]:
        if self.mode != "DRY_RUN":
            return {
                "ok": False,
                "status": "BLOCKED",
                "broker": self.name,
                "reason": "Agah live order API is not enabled; TRADING_MODE must be DRY_RUN.",
            }

        result = {
            "ok": True,
            "status": "DRY_RUN",
            "broker": self.name,
            "symbol": order.symbol,
            "side": order.side.upper(),
            "quantity": int(order.quantity),
            "price": float(order.price),
            "message": "سفارش فقط شبیه‌سازی شد و به آگاه ارسال نشد.",
        }
        print(
            f"AGAH DRY_RUN | {result['side']} | {result['symbol']} | "
            f"qty={result['quantity']} | price={result['price']:,.0f}"
        )
        return result

    def account_status(self) -> dict[str, Any]:
        return {
            "broker": self.name,
            "mode": self.mode,
            "configured": self.configured,
            "live_orders_enabled": False,
            "message": "اتصال واقعی سفارش‌دهی آگاه تا زمان وجود API رسمی و تأیید آن غیرفعال است.",
        }
