from __future__ import annotations

from src.analysis.indicators import ema, rsi, macd


def _rsi_status(value: float) -> str:
    if value >= 70:
        return "بیش‌خرید"
    if value <= 30:
        return "بیش‌فروش"
    if value >= 55:
        return "متمایل به صعود"
    if value >= 45:
        return "خنثی"
    return "متمایل به نزول"


def _trend_status(e9: float, e21: float, price: float) -> str:
    if price > e9 > e21:
        return "صعودی قوی"
    if price >= e9 and e9 >= e21:
        return "صعودی"
    if price < e9 < e21:
        return "نزولی قوی"
    if price <= e9 and e9 <= e21:
        return "نزولی"
    return "خنثی"


def score_signal(closes, volumes=None, real_buy_ratio=None, min_score=80):
    closes = list(map(float, closes))
    volumes = list(map(float, volumes or []))
    min_score = max(50, min(100, int(min_score)))

    if len(closes) < 30:
        return {
            "score": 0,
            "action": "NO_DATA",
            "reasons": ["حداقل ۳۰ قیمت لازم است"],
            "breakdown": {},
        }

    e9 = float(ema(closes, 9)[-1])
    e21 = float(ema(closes, 21)[-1])
    price = float(closes[-1])
    rv = float(rsi(closes, 14))
    ml, ms = macd(closes)
    ml = float(ml)
    ms = float(ms)

    score = 50
    reasons = []
    breakdown = {
        "base": 50,
        "trend": 0,
        "macd": 0,
        "rsi": 0,
        "volume": 0,
        "flow": 0,
    }

    if e9 > e21:
        breakdown["trend"] = 15
        score += 15
        reasons.append("روند صعودی: EMA9 بالاتر از EMA21")
    else:
        breakdown["trend"] = -15
        score -= 15
        reasons.append("روند نزولی: EMA9 پایین‌تر از EMA21")

    if ml > ms:
        breakdown["macd"] = 10
        score += 10
        reasons.append("MACD بالاتر از خط سیگنال است")
    else:
        breakdown["macd"] = -10
        score -= 10
        reasons.append("MACD پایین‌تر از خط سیگنال است")

    if 45 <= rv <= 65:
        breakdown["rsi"] = 10
        score += 10
        reasons.append("RSI در محدوده متعادل و مناسب روند است")
    elif rv > 75:
        breakdown["rsi"] = -10
        score -= 10
        reasons.append("RSI در محدوده بیش‌خرید است")
    elif rv < 30:
        breakdown["rsi"] = 0
        reasons.append("RSI در محدوده بیش‌فروش است؛ نیاز به تأیید برگشت دارد")
    else:
        reasons.append("RSI سیگنال قوی صعودی/نزولی ایجاد نکرده است")

    volume_current = volumes[-1] if volumes else 0.0
    avg_volume = (
        sum(volumes[-20:]) / 20
        if len(volumes) >= 20
        else None
    )
    volume_ratio = (
        volume_current / avg_volume
        if avg_volume and avg_volume > 0
        else None
    )
    if volume_ratio is not None:
        if volume_ratio >= 1.20:
            breakdown["volume"] = 10
            score += 10
            reasons.append("حجم معاملات حداقل ۲۰٪ بالاتر از میانگین ۲۰ روزه است")
        elif volume_ratio <= 0.80:
            breakdown["volume"] = -5
            score -= 5
            reasons.append("حجم معاملات پایین‌تر از میانگین ۲۰ روزه است")
        else:
            reasons.append("حجم معاملات نزدیک به میانگین ۲۰ روزه است")
    else:
        reasons.append("داده کافی برای مقایسه حجم با میانگین ۲۰ روزه وجود ندارد")

    if real_buy_ratio is not None:
        if real_buy_ratio >= 0.60:
            breakdown["flow"] = 10
            score += 10
            reasons.append("قدرت خرید حقیقی بالاست")
        elif real_buy_ratio <= 0.40:
            breakdown["flow"] = -10
            score -= 10
            reasons.append("قدرت فروش حقیقی بالاست")
        else:
            reasons.append("قدرت خرید و فروش حقیقی متعادل است")
    else:
        reasons.append("داده حقیقی/حقوقی در دسترس نیست؛ امتیاز جریان نقدینگی اعمال نشد")

    score = max(0, min(100, int(score)))
    action = (
        "BUY"
        if score >= min_score
        else ("WATCH" if score >= 60 else "NO_TRADE")
    )

    return {
        "score": score,
        "action": action,
        "min_score": min_score,
        "price": price,
        "rsi": round(rv, 2),
        "rsi_status": _rsi_status(rv),
        "ema9": round(e9, 2),
        "ema21": round(e21, 2),
        "trend": _trend_status(e9, e21, price),
        "macd": round(ml, 4),
        "macd_signal": round(ms, 4),
        "macd_state": "بالای سیگنال" if ml > ms else "پایین سیگنال",
        "volume": round(volume_current, 2),
        "avg_volume_20": round(avg_volume, 2) if avg_volume is not None else None,
        "volume_ratio": round(volume_ratio, 2) if volume_ratio is not None else None,
        "volume_status": (
            "بالاتر از میانگین"
            if volume_ratio is not None and volume_ratio > 1
            else "پایین‌تر از میانگین"
            if volume_ratio is not None and volume_ratio < 1
            else "نامشخص"
        ),
        "breakdown": breakdown,
        "reasons": reasons,
    }
