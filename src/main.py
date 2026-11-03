from __future__ import annotations

from src.config import Config
from src.data.tsetmc_client import TsetmcClient
from src.data.brsapi_client import BrsApiProvider
from src.data.tindex_client import TindexProvider
from src.analysis.scanner import scan_symbols
from src.analysis.screener import market_rows, top_gainers, top_volume
from src.dashboard.generate import write_dashboard
from src.trading.paper_account import PaperAccount
from src.trading.risk_manager import position_size, exit_reason
from src.shadow.logger import log_shadow_signals, DEFAULT_SHADOW_PATH
from src.telegram_bot import send_message
from src.broker.agah import AgahBroker, OrderRequest


def _paper_actions(results, account, cfg):
    prices = {}
    actions = []

    for item in results:
        symbol = item["symbol"]
        price = float(item.get("price") or 0)
        signal = item.get("signal", {})
        if price <= 0:
            actions.append({"symbol": symbol, "action": "NONE", "reason": "داده معتبر ندارد"})
            continue

        prices[symbol] = price

        if symbol in account.positions:
            reason = exit_reason(account.positions[symbol], price)
            if reason or signal.get("action") == "NO_TRADE":
                account.sell(symbol, price, reason or "SIGNAL")
                actions.append({"symbol": symbol, "action": "SELL", "reason": reason or "SIGNAL"})
            else:
                actions.append({"symbol": symbol, "action": "HOLD", "reason": "موقعیت باز و سیگنال خروج فعال نیست"})
        elif signal.get("action") == "BUY":
            qty = position_size(account.cash, price, cfg.max_position_pct)
            if account.buy(symbol, price, qty, cfg.stop_loss_pct, cfg.take_profit_pct):
                actions.append({
                    "symbol": symbol,
                    "action": "BUY",
                    "reason": f"score={signal.get('score', 0)}",
                    "quantity": qty,
                })
            else:
                actions.append({"symbol": symbol, "action": "NONE", "reason": "سرمایه/حجم سفارش کافی نیست"})
        else:
            actions.append({
                "symbol": symbol,
                "action": "WATCH" if signal.get("action") == "WATCH" else "NONE",
                "reason": signal.get("action", "NO_TRADE"),
            })

    account.update_risk(prices)
    return actions, prices



def _agah_dry_run(results, actions, snap, cfg):
    broker = AgahBroker(cfg.trading_mode)
    if cfg.trading_mode != "DRY_RUN":
        return broker.account_status(), []

    orders = []
    positions = snap.get("positions", {})
    for action in actions:
        side = action.get("action")
        if side not in {"BUY", "SELL"}:
            continue
        item = next((x for x in results if x.get("symbol") == action.get("symbol")), None)
        if not item or float(item.get("price") or 0) <= 0:
            continue
        qty = int(action.get("quantity") or positions.get(action["symbol"], {}).get("quantity") or 0)
        if qty <= 0:
            continue
        orders.append(
            broker.submit_order(
                OrderRequest(action["symbol"], side, qty, float(item["price"]))
            )
        )
    return broker.account_status(), orders

def _telegram_report(results, actions, snap, cfg, broker_status=None, broker_orders=None):
    usable = [x for x in results if x.get("price", 0) > 0]
    ranked = sorted(
        usable,
        key=lambda x: x.get("signal", {}).get("score", 0),
        reverse=True,
    )

    lines = [
        "📊 ربات حرفه‌ای دمو بورس ایران",
        "━━━━━━━━━━━━━━━━━━",
        f"🔎 تعداد نمادهای بررسی‌شده: {len(results)}",
        f"💰 سرمایه/ارزش پرتفوی: {snap['equity']:,.0f} تومان",
        f"📉 افت سرمایه: {snap['max_drawdown_pct']:.2f}٪",
        "",
        "🏆 خروجی اسکن",
    ]

    for item in ranked[:10]:
        s = item["signal"]
        action = next(
            (a["action"] for a in actions if a["symbol"] == item["symbol"]),
            "NONE",
        )
        lines.append(
            f"• {item['symbol']} | امتیاز {s.get('score', 0)}/100 | "
            f"{s.get('action', 'UNAVAILABLE')} | عملیات: {action}"
        )

    if not ranked:
        lines.append("• هیچ نماد دارای داده معتبر در این اجرا نبود.")

    top_score = ranked[0]["signal"].get("score", 0) if ranked else 0
    if ranked:
        lines.append("")
        lines.append(
            f"🎚 بالاترین امتیاز: {top_score}/100 | آستانه خرید: {cfg.min_score}"
        )
        if top_score < cfg.min_score:
            lines.append(
                f"هیچ سیگنال خریدی به آستانه نرسید (فاصله: {cfg.min_score - top_score} امتیاز)."
            )

    lines.extend(["", "📌 جزئیات نمادهای منتخب"])

    for item in ranked[:5]:
        s = item["signal"]
        f = s.get("fundamental", {})
        b = s.get("breakdown", {})
        flow = item.get("flow", {}).get("real_buy_ratio")
        flow_text = f"{flow * 100:.1f}٪" if flow is not None else "نامشخص"
        lines.extend([
            "",
            f"🔹 {item['symbol']} | {item['price']:,.0f} تومان",
            f"سیگنال: {s.get('action')} | امتیاز: {s.get('score', 0)}/100",
            f"روند: {s.get('trend', 'نامشخص')} | قدرت روند: {s.get('trend_strength', 0):.1f}/100",
            f"RSI: {s.get('rsi', 0):.2f} | MACD: {s.get('macd_state', 'نامشخص')}",
            f"واگرایی RSI: {s.get('rsi_divergence', 'ندارد')} | واگرایی MACD: {s.get('macd_divergence', 'ندارد')}",
            f"برگشت از اشباع فروش: {'تأیید' if s.get('reversal_confirmation') else 'تأیید نشده'}",
            f"حجم: {s.get('volume_ratio') if s.get('volume_ratio') is not None else 'نامشخص'}x میانگین",
            f"خرید حقیقی: {flow_text}",
            f"فاندامنتال: {b.get('fundamental', 0):+d}/20 | EPS: {f.get('eps') if f.get('eps') is not None else 'نامشخص'} | P/E: {f.get('pe') if f.get('pe') is not None else 'نامشخص'}",
            f"ROE: {f.get('roe') if f.get('roe') is not None else 'نامشخص'}٪ | P/B: {f.get('pb') if f.get('pb') is not None else 'نامشخص'}",
        ])

    lines.extend([
        "",
        "🧠 توجه: این گزارش اطلاعات تحلیلی و Paper Trading است و به‌تنهایی به معنی توصیه سرمایه‌گذاری نیست.",
        f"⚙️ حداقل امتیاز خرید تنظیم‌شده: {cfg.min_score}",
        f"🏦 کارگزاری: آگاه | حالت: {cfg.trading_mode}",
    ])
    if broker_status and cfg.trading_mode == "DRY_RUN":
        lines.extend([
            "🧪 DRY_RUN فعال است؛ هیچ سفارش واقعی به آگاه ارسال نشده است.",
            f"📨 سفارش‌های شبیه‌سازی‌شده: {len(broker_orders or [])}",
        ])
    return "\n".join(lines)


def _shadow_summary():
    """خلاصه سبک از لاگ shadow برای داشبورد؛ خطا هرگز اجرای اصلی را نمی‌شکند."""
    try:
        from pathlib import Path
        p = DEFAULT_SHADOW_PATH
        if not Path(p).exists():
            return {"records": 0, "note": "هنوز لاگی ثبت نشده"}
        # بدون محاسبات سنگین: فقط تعداد رکورد و آخرین تحلیل آستانه را اگر داده کافی باشد
        from src.shadow.evaluate import evaluate_shadow_log
        ev = evaluate_shadow_log(p)
        # فقط بخش‌های سبک را نگه می‌داریم تا data.json حجیم نشود
        return {
            "records": ev.get("total_records", 0),
            "symbols": ev.get("symbols", [])[:10],
            "date_range": ev.get("date_range"),
            "thresholds": ev.get("thresholds"),
            "horizons": ev.get("horizons"),
            "per_threshold": ev.get("per_threshold"),
        }
    except Exception as exc:
        return {"records": 0, "error": str(exc)}


def _build_payload(results, actions, snap, gainers, volume, cfg):
    available = [r for r in results if float(r.get("price") or 0) > 0]
    return {
        "summary": {
            "symbols": list(cfg.symbols)[: cfg.max_symbols],
            "scanned": len(results),
            "available": len(available),
            "top_score": max(
                (int(r.get("signal", {}).get("score") or 0) for r in available),
                default=0,
            ),
            "min_score": cfg.min_score,
            "mode": cfg.trading_mode,
            "provider": "MULTI",
        },
        "scan_results": results,
        "actions": actions,
        "paper": snap,
        "top_gainers": gainers,
        "top_volume": volume,
        "shadow": _shadow_summary(),
    }


def main():
    cfg = Config()
    client = TsetmcClient(cfg)
    brs = BrsApiProvider(cfg.brs_api_key, cfg.brs_api_timeout)
    tindex = TindexProvider(cfg.tindex_api_key, cfg.tindex_api_timeout)
    account = PaperAccount.load(initial_cash=cfg.initial_cash)

    results = scan_symbols(cfg.symbols, client, brs, tindex, cfg)
    # Shadow logging — همیشه و بدون تأثیر بر Paper/Telegram
    try:
        log_shadow_signals(results, cfg)
    except Exception as exc:
        print(f"SHADOW LOG FAILED | {exc}")
    actions, prices = _paper_actions(results, account, cfg)
    snap = account.snapshot(prices)
    account.save()
    broker_status, broker_orders = _agah_dry_run(results, actions, snap, cfg)
    print(f"BROKER | {broker_status}")

    try:
        rows = market_rows(client.market_watch())
        gainers = top_gainers(rows)
        volume = top_volume(rows)
    except Exception as exc:
        print(f"MARKET WATCH UNAVAILABLE | {exc}")
        gainers, volume = [], []

    write_dashboard(_build_payload(results, actions, snap, gainers, volume, cfg))

    print(
        f"IRAN STOCK PROFESSIONAL PAPER | scanned={len(results)} | "
        f"equity={snap['equity']:,.0f} | P/L={snap['realized_pnl']:,.0f} | "
        f"DD={snap['max_drawdown_pct']:.2f}%"
    )

    if cfg.telegram_enabled:
        send_message(_telegram_report(results, actions, snap, cfg, broker_status, broker_orders))


if __name__ == "__main__":
    main()
