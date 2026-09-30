from __future__ import annotations
import numpy as np

def ema(values,period):
    values=np.asarray(values,dtype=float)
    if len(values)==0:return np.array([])
    alpha=2/(period+1); out=np.empty(len(values)); out[0]=values[0]
    for i in range(1,len(values)): out[i]=alpha*values[i]+(1-alpha)*out[i-1]
    return out

def rsi(values,period=14):
    v=np.asarray(values,dtype=float)
    if len(v)<2:return 50.0
    d=np.diff(v); gain=np.maximum(d,0); loss=np.maximum(-d,0); n=min(period,len(gain)); ag=gain[-n:].mean(); al=loss[-n:].mean()
    return 100.0 if al==0 else 100-100/(1+ag/al)

def macd(values):
    line=ema(values,12)-ema(values,26); signal=ema(line,9)
    return float(line[-1]),float(signal[-1])
