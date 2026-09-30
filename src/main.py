from src.config import Config
from src.data.tsetmc_client import TsetmcClient, TsetmcError
from src.analysis.signal_engine import score_signal
from src.analysis.screener import market_rows, top_gainers, top_volume
from src.dashboard.generate import write_dashboard

def main():
    cfg=Config()
    client=TsetmcClient(cfg)
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
                closes.append(client.rial_to_toman(p))
                volumes.append(float(v or 0))
        signal=score_signal(closes,volumes)

        client_flow=client.client_type(str(ins))
        flow=client_flow[0] if client_flow else {}
        buy_i=float(flow.get("buy_I_Volume") or 0)
        buy_n=float(flow.get("buy_N_Volume") or 0)
        sell_i=float(flow.get("sell_I_Volume") or 0)
        sell_n=float(flow.get("sell_N_Volume") or 0)
        total_buy=buy_i+buy_n
        real_buy_ratio=(buy_i/total_buy) if total_buy else None
        signal=score_signal(closes,volumes,real_buy_ratio)

        try:
            watch=client.market_watch()
            rows=market_rows(watch)
        except TsetmcError:
            rows=[]
        payload={
            "summary":{"symbol":symbol,"price_toman":closes[-1] if closes else 0},
            "signal":signal,
            "flow":{"real_buy_volume":buy_i,"legal_buy_volume":buy_n,
                    "real_sell_volume":sell_i,"legal_sell_volume":sell_n,
                    "real_buy_ratio":real_buy_ratio},
            "top_gainers":top_gainers(rows),
            "top_volume":top_volume(rows),
        }
        write_dashboard(payload)
        print(f"IRAN STOCK DEMO | {symbol} | price={closes[-1] if closes else 0:,.0f} Toman | score={signal['score']} | action={signal['action']}")
        print("Reasons:", "، ".join(signal["reasons"]))
        print(f"Real buy ratio: {real_buy_ratio:.2%}" if real_buy_ratio is not None else "Real buy ratio: N/A")
    except TsetmcError as exc:
        write_dashboard({"summary":{"symbol":cfg.symbol,"price_toman":0},
                         "signal":{"score":0,"action":"UNAVAILABLE","reasons":[str(exc)]},
                         "top_gainers":[],"top_volume":[]})
        print(f"TSETMC UNAVAILABLE | {exc}")

if __name__=="__main__":
    main()
