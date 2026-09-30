from src.config import Config
from src.data.tsetmc_client import TsetmcClient, TsetmcError
from src.data.brsapi_client import BrsApiProvider, ProviderError
from src.data.tindex_client import TindexProvider, TindexError
from src.analysis.signal_engine import score_signal
from src.analysis.screener import market_rows, top_gainers, top_volume
from src.dashboard.generate import write_dashboard
from src.trading.paper_account import PaperAccount
from src.trading.risk_manager import position_size, exit_reason
from src.telegram_bot import send_message


def main():
    cfg = Config()
    client = TsetmcClient(cfg)
    brs = BrsApiProvider(cfg.brs_api_key, cfg.brs_api_timeout)
    tindex = TindexProvider(cfg.tindex_api_key, cfg.tindex_api_timeout)
    account = PaperAccount.load(initial_cash=cfg.initial_cash)
    provider_name = "TSETMC"

    try:
        try:
            found = client.resolve_symbol(cfg.symbol)
            ins = found.get("insCode") or found.get("InsCode")
            symbol = found.get("lVal18AFC") or found.get("LVal18AFC") or cfg.symbol
            hist = client.history(str(ins), 120)
            flow = client.client_type(str(ins))
        except TsetmcError as primary_exc:
            # First fallback: legacy public TSETMC endpoints, no API key.
            try:
                found = client.legacy_search(cfg.symbol)
                if not found:
                    raise TsetmcError(f"Legacy TSETMC symbol not found: {cfg.symbol}")
                ins = found[0].get("insCode")
                symbol = found[0].get("lVal18AFC") or cfg.symbol
                hist = client.legacy_history(str(ins), 120)
                flow = client.legacy_client_type(str(ins))
                provider_name = "TSETMC-LEGACY"
                print(f"DATA PROVIDER FALLBACK | {provider_name} | reason={primary_exc}")
            except TsetmcError as legacy_exc:
                try:
                    if not tindex.available:
                        raise TindexError("TINDEX_API_KEY is not configured")
                    found = tindex.resolve(cfg.symbol)
                    slug = found["slug"]
                    symbol = found.get("ticker") or cfg.symbol
                    hist = tindex.history(slug, "3m")
                    detail = tindex.detail(slug)
                    closes = [tindex.rial_to_toman(r["close"]) for r in hist if r.get("close") is not None]
                    volumes = [float(detail.get("trade_volume") or 0)] * len(closes)
                    flow = [{"buy_I_Volume": detail.get("buy", {}).get("volume_real", 0), "buy_N_Volume": detail.get("buy", {}).get("volume_legal", 0), "sell_I_Volume": detail.get("sell", {}).get("volume_real", 0), "sell_N_Volume": detail.get("sell", {}).get("volume_legal", 0)}]
                    provider_name = "Tindex"
                    print(f"DATA PROVIDER FALLBACK | {provider_name} | reason={legacy_exc}")
                except TindexError as tindex_exc:
                    if not brs.available:
                        raise TsetmcError(f"TSETMC unavailable; Tindex unavailable: {tindex_exc}")
                    provider_name = "BrsApi"
                    raise legacy_exc
                provider_name = "BrsApi"
                symbol = cfg.symbol
                hist = brs.history(symbol, 120)
                flow = brs.client_type(symbol)
                print(f"DATA PROVIDER FALLBACK | {provider_name} | reason={legacy_exc}")

        closes = []
        volumes = []
        for row in hist:
            p = (
                row.get("pClosing")
                or row.get("pc")
                or row.get("closingPrice")
                or row.get("pcp")
            )
            v = (
                row.get("qTotTran5J")
                or row.get("tvol")
                or row.get("volume")
                or row.get("zTotTran")
            )
            if p is not None:
                closes.append(client.rial_to_toman(p))
                volumes.append(float(v or 0))

        if not closes:
            raise TsetmcError(
                f"{provider_name} returned no usable price history for {symbol}"
            )

        price = closes[-1]
        f = flow[0] if flow else {}
        bi = float(f.get("buy_I_Volume") or f.get("Buy_I_Volume") or 0)
        bn = float(f.get("buy_N_Volume") or f.get("Buy_N_Volume") or 0)
        si = float(f.get("sell_I_Volume") or f.get("Sell_I_Volume") or 0)
        sn = float(f.get("sell_N_Volume") or f.get("Sell_N_Volume") or 0)
        ratio = bi / (bi + bn) if bi + bn else None
        signal = score_signal(closes, volumes, ratio)

        action = "HOLD"
        reason = "بدون معامله"
        if symbol in account.positions:
            reason = exit_reason(account.positions[symbol], price)
            if reason or signal["action"] == "NO_TRADE":
                account.sell(symbol, price, reason or "SIGNAL")
                action = "SELL"
                reason = reason or "SIGNAL"
        elif signal["action"] == "BUY":
            qty = position_size(account.cash, price, cfg.max_position_pct)
            if account.buy(
                symbol, price, qty, cfg.stop_loss_pct, cfg.take_profit_pct
            ):
                action = "BUY"
                reason = f"score={signal['score']}"

        account.update_risk({symbol: price})

        try:
            rows = (
                market_rows(client.market_watch())
                if provider_name == "TSETMC"
                else []
            )
        except TsetmcError:
            rows = []

        snap = account.snapshot({symbol: price})
        payload = {
            "summary": {
                "symbol": symbol,
                "price_toman": price,
                "provider": provider_name,
            },
            "signal": signal,
            "paper": snap,
            "paper_action": action,
            "paper_reason": reason,
            "flow": {
                "real_buy_volume": bi,
                "legal_buy_volume": bn,
                "real_sell_volume": si,
                "legal_sell_volume": sn,
                "real_buy_ratio": ratio,
            },
            "top_gainers": top_gainers(rows),
            "top_volume": top_volume(rows),
        }
        write_dashboard(payload)
        account.save()
        print(
            f"IRAN STOCK PAPER | {symbol} | provider={provider_name} | "
            f"price={price:,.0f} | score={signal['score']} | "
            f"signal={signal['action']} | paper={action}"
        )
        print(
            f"Paper equity={snap['equity']:,.0f} | "
            f"P/L={snap['realized_pnl']:,.0f} | "
            f"DD={snap['max_drawdown_pct']:.2f}%"
        )

        if cfg.telegram_enabled:
            position = snap.get("positions", {}).get(symbol)
            pos_text = f"\nموقعیت: {position}" if position else "\nموقعیت باز: ندارد"
            send_message(
                "📊 ربات دمو بورس ایران\n"
                f"منبع داده: {provider_name}\n"
                f"نماد: {symbol}\n"
                f"قیمت: {price:,.0f} تومان\n"
                f"سیگنال: {signal['action']} | امتیاز: {signal['score']}\n"
                f"عملیات دمو: {action}\n"
                f"دلیل: {reason}\n"
                f"سرمایه: {snap['equity']:,.0f} تومان\n"
                f"سود/زیان تحقق‌یافته: {snap['realized_pnl']:,.0f} تومان\n"
                f"افت سرمایه: {snap['max_drawdown_pct']:.2f}%"
                + pos_text
            )

    except (TsetmcError, ProviderError, TindexError) as exc:
        write_dashboard(
            {
                "summary": {
                    "symbol": cfg.symbol,
                    "price_toman": 0,
                    "provider": "UNAVAILABLE",
                },
                "signal": {
                    "score": 0,
                    "action": "UNAVAILABLE",
                    "reasons": [str(exc)],
                },
                "paper": account.snapshot(),
                "paper_action": "NONE",
                "top_gainers": [],
                "top_volume": [],
            }
        )
        account.save()
        print(f"MARKET DATA UNAVAILABLE | {exc}")
        if cfg.telegram_enabled:
            send_message(
                "⚠️ ربات دمو بورس ایران\n"
                "داده معتبر بازار در این اجرا دریافت نشد؛ هیچ معامله DEMO انجام نشد.\n"
                f"جزئیات: {exc}"
            )


if __name__ == "__main__":
    main()
