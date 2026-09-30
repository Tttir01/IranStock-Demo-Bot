from src.config import Config
from src.data.tsetmc_client import TsetmcClient,TsetmcError
from src.analysis.signal_engine import score_signal

def main():
    cfg=Config(); client=TsetmcClient(cfg)
    try:
        found=client.resolve_symbol(cfg.symbol); ins=found.get("insCode") or found.get("InsCode"); symbol=found.get("lVal18AFC") or found.get("LVal18AFC") or cfg.symbol
        hist=client.history(str(ins),120); closes=[]; volumes=[]
        for row in hist:
            p=row.get("pClosing") or row.get("pc") or row.get("closingPrice"); v=row.get("qTotTran5J") or row.get("volume") or row.get("zTotTran")
            if p is not None: closes.append(client.rial_to_toman(p)); volumes.append(float(v or 0))
        signal=score_signal(closes,volumes)
        print(f"IRAN STOCK DEMO | {symbol} | price={closes[-1] if closes else 0:,.0f} Toman | score={signal['score']} | action={signal['action']}")
        print("Reasons:","، ".join(signal["reasons"]))
    except TsetmcError as exc: print(f"TSETMC UNAVAILABLE | {exc}")
if __name__=="__main__":main()
