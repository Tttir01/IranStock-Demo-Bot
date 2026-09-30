from src.config import Config
from src.data.tsetmc_client import TsetmcClient,TsetmcError
from src.analysis.signal_engine import score_signal
from src.analysis.screener import market_rows,top_gainers,top_volume
from src.dashboard.generate import write_dashboard
from src.trading.paper_account import PaperAccount
from src.trading.risk_manager import position_size,exit_reason
from src.telegram_bot import send_message

def main():
    cfg=Config(); client=TsetmcClient(cfg)
    account=PaperAccount.load(initial_cash=cfg.initial_cash)
    try:
        found=client.resolve_symbol(cfg.symbol)
        ins=found.get("insCode") or found.get("InsCode")
        symbol=found.get("lVal18AFC") or found.get("LVal18AFC") or cfg.symbol
        hist=client.history(str(ins),120)
        closes=[]; volumes=[]
        for row in hist:
            p=row.get("pClosing") or row.get("pc") or row.get("closingPrice")
            v=row.get("qTotTran5J") or row.get("volume") or row.get("zTotTran")
            if p is not None:
                closes.append(client.rial_to_toman(p)); volumes.append(float(v or 0))
        price=closes[-1] if closes else 0
        signal=score_signal(closes,volumes)

        flow=client.client_type(str(ins))
        f=flow[0] if flow else {}
        bi=float(f.get("buy_I_Volume") or 0); bn=float(f.get("buy_N_Volume") or 0)
        si=float(f.get("sell_I_Volume") or 0); sn=float(f.get("sell_N_Volume") or 0)
        ratio=bi/(bi+bn) if bi+bn else None
        signal=score_signal(closes,volumes,ratio)

        action="HOLD"
        reason="بدون معامله"
        if symbol in account.positions:
            reason=exit_reason(account.positions[symbol],price)
            if reason or signal["action"]=="NO_TRADE":
                account.sell(symbol,price,reason or "SIGNAL")
                action="SELL"
                reason=reason or "SIGNAL"
        elif signal["action"]=="BUY":
            qty=position_size(account.cash,price,cfg.max_position_pct)
            if account.buy(symbol,price,qty,cfg.stop_loss_pct,cfg.take_profit_pct):
                action="BUY"; reason=f"score={signal['score']}"
        account.update_risk({symbol:price})

        try: rows=market_rows(client.market_watch())
        except TsetmcError: rows=[]
        snap=account.snapshot({symbol:price})
        payload={"summary":{"symbol":symbol,"price_toman":price},
                 "signal":signal,"paper":snap,"paper_action":action,"paper_reason":reason,
                 "flow":{"real_buy_volume":bi,"legal_buy_volume":bn,"real_sell_volume":si,
                         "legal_sell_volume":sn,"real_buy_ratio":ratio},
                 "top_gainers":top_gainers(rows),"top_volume":top_volume(rows)}
        write_dashboard(payload); account.save()
        print(f"IRAN STOCK PAPER | {symbol} | price={price:,.0f} | score={signal['score']} | signal={signal['action']} | paper={action}")
        print(f"Paper equity={snap['equity']:,.0f} | P/L={snap['realized_pnl']:,.0f} | DD={snap['max_drawdown_pct']:.2f}%")
        if cfg.telegram_enabled:
            position = snap.get("positions", {}).get(symbol)
            pos_text = f"\nموقعیت: {position}" if position else "\nموقعیت باز: ندارد"
            send_message(
                "📊 ربات دمو بورس ایران\\n"
                f"نماد: {symbol}\\n"
                f"قیمت: {price:,.0f} تومان\\n"
                f"سیگنال: {signal['action']} | امتیاز: {signal['score']}\\n"
                f"عملیات دمو: {action}\\n"
                f"دلیل: {reason}\\n"
                f"سرمایه: {snap['equity']:,.0f} تومان\\n"
                f"سود/زیان تحقق‌یافته: {snap['realized_pnl']:,.0f} تومان\\n"
                f"افت سرمایه: {snap['max_drawdown_pct']:.2f}%"
                + pos_text
            )
    except TsetmcError as exc:
        write_dashboard({"summary":{"symbol":cfg.symbol,"price_toman":0},
                         "signal":{"score":0,"action":"UNAVAILABLE","reasons":[str(exc)]},
                         "paper":account.snapshot(),"paper_action":"NONE",
                         "top_gainers":[],"top_volume":[]})
        account.save()
        print(f"TSETMC UNAVAILABLE | {exc}")
        if cfg.telegram_enabled:\n            send_message(f"⚠️ ربات دمو بورس ایران\\nدسترسی به داده‌های TSETMC در این اجرا برقرار نشد.\\nجزئیات: {exc}")\n
if __name__=="__main__": main()
