from src.analysis.indicators import ema,rsi,macd

def score_signal(closes,volumes=None,real_buy_ratio=None):
    closes=list(map(float,closes))
    if len(closes)<30:return {"score":0,"action":"NO_DATA","reasons":["حداقل ۳۰ قیمت لازم است"]}
    e9,e21=ema(closes,9)[-1],ema(closes,21)[-1]; rv=rsi(closes,14); ml,ms=macd(closes); score=50; reasons=[]
    if e9>e21:score+=15;reasons.append("EMA9 بالاتر از EMA21")
    else:score-=15;reasons.append("EMA9 پایین‌تر از EMA21")
    if ml>ms:score+=10;reasons.append("MACD مثبت")
    else:score-=10;reasons.append("MACD منفی")
    if 45<=rv<=65:score+=10;reasons.append("RSI متعادل صعودی")
    elif rv>75:score-=10;reasons.append("RSI بیش‌خرید")
    if volumes and len(volumes)>=20 and volumes[-1]>sum(volumes[-20:])/20:score+=10;reasons.append("حجم بالاتر از میانگین")
    if real_buy_ratio is not None:
        if real_buy_ratio>=0.60:score+=10;reasons.append("قدرت خرید حقیقی")
        elif real_buy_ratio<=0.40:score-=10;reasons.append("قدرت فروش حقیقی")
    score=max(0,min(100,int(score))); action="BUY" if score>=80 else ("WATCH" if score>=60 else "NO_TRADE")
    return {"score":score,"action":action,"rsi":round(rv,2),"ema9":e9,"ema21":e21,"macd":ml,"macd_signal":ms,"reasons":reasons}
