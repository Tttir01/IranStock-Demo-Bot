from __future__ import annotations

def _num(row, *keys):
    for key in keys:
        value=row.get(key)
        try:
            if value is not None and value != "-":
                return float(value)
        except (TypeError, ValueError):
            pass
    return 0.0

def market_rows(rows):
    result=[]
    for r in rows:
        symbol=r.get("lVal18AFC") or r.get("lval18afc") or r.get("symbol") or ""
        if not symbol:
            continue
        last=_num(r,"pl","pDrCotVal","last")
        close=_num(r,"pc","pClosing","close")
        yesterday=_num(r,"py","priceYesterday","yesterday")
        volume=_num(r,"qTotTran5J","volume","zTotTran")
        value=_num(r,"qTotCap","value")
        pct=((last-yesterday)/yesterday*100) if yesterday else 0
        result.append({"symbol":symbol,"last_toman":last/10,"close_toman":close/10,
                       "change_pct":pct,"volume":volume,"value_toman":value/10,
                       "ins_code":str(r.get("insCode") or r.get("inscode") or "")})
    return result

def top_gainers(rows,n=10):
    return sorted(rows,key=lambda x:x["change_pct"],reverse=True)[:n]

def top_volume(rows,n=10):
    return sorted(rows,key=lambda x:x["volume"],reverse=True)[:n]
