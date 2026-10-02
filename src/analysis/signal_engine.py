from __future__ import annotations

import math

import numpy as np

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


def _rsi_series(values, period=14):
    values = np.asarray(values, dtype=float)
    if len(values) < 2:
        return np.full(len(values), 50.0, dtype=float)

    out = np.full(len(values), 50.0, dtype=float)
    delta = np.diff(values)
    gains = np.maximum(delta, 0.0)
    losses = np.maximum(-delta, 0.0)

    for i in range(1, len(values)):
        n = min(period, i)
        avg_gain = gains[i - n : i].mean()
        avg_loss = losses[i - n : i].mean()
        if avg_loss == 0:
            out[i] = 100.0 if avg_gain > 0 else 50.0
        else:
            rs = avg_gain / avg_loss
            out[i] = 100.0 - (100.0 / (1.0 + rs))
    return out


def _macd_series(values):
    values = np.asarray(values, dtype=float)
    line = ema(values, 12) - ema(values, 26)
    signal = ema(line, 9)
    return line.astype(float), signal.astype(float)


def _pivot_indices(values, kind="low", window=3):
    values = np.asarray(values, dtype=float)
    pivots = []
    if len(values) < (window * 2 + 1):
        return pivots

    for i in range(window, len(values) - window):
        left = values[i - window : i]
        right = values[i + 1 : i + window + 1]
        if kind == "low":
            if values[i] <= left.min() and values[i] <= right.min():
                pivots.append(i)
        else:
            if values[i] >= left.max() and values[i] >= right.max():
                pivots.append(i)
    return pivots


def _detect_divergence(prices, indicator_values, kind="bullish", lookback=60):
    prices = np.asarray(prices, dtype=float)
    indicator_values = np.asarray(indicator_values, dtype=float)

    n = min(len(prices), len(indicator_values))
    if n < 15:
        return "none"

    prices = prices[-lookback:]
    indicator_values = indicator_values[-lookback:]

    if kind == "bullish":
        pivots = _pivot_indices(prices, "low", window=2)
        if len(pivots) < 2:
            return "none"
        a, b = pivots[-2], pivots[-1]
        if prices[b] < prices[a] and indicator_values[b] > indicator_values[a]:
            return "bullish"
    else:
        pivots = _pivot_indices(prices, "high", window=2)
        if len(pivots) < 2:
            return "none"
        a, b = pivots[-2], pivots[-1]
        if prices[b] > prices[a] and indicator_values[b] < indicator_values[a]:
            return "bearish"

    return "none"


def _trend_strength(prices, e9_series, e21_series):
    """Close-only trend strength proxy, 0..100.

    This intentionally avoids pretending to be ADX because the current
    provider pipeline does not reliably expose OHLC highs/lows for every
    fallback source. It combines normalized EMA separation and short-term
    EMA slope.
    """
    prices = np.asarray(prices, dtype=float)
    e9_series = np.asarray(e9_series, dtype=float)
    e21_series = np.asarray(e21_series, dtype=float)

    if len(prices) < 25:
        return 0.0, "نامشخص"

    price = max(abs(float(prices[-1])), 1e-9)
    gap_pct = abs(float(e9_series[-1] - e21_series[-1])) / price * 100.0

    lookback = min(10, len(e9_series) - 1)
    slope_pct = (
        abs(float(e9_series[-1] - e9_series[-1 - lookback]))
        / price
        * 100.0
    )

    strength = min(100.0, gap_pct * 20.0 + slope_pct * 12.0)

    if strength >= 70:
        status = "بسیار قوی"
    elif strength >= 50:
        status = "قوی"
    elif strength >= 30:
        status = "متوسط"
    elif strength >= 15:
        status = "ضعیف"
    else:
        status = "خنثی"

    return round(strength, 1), status


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fundamental_analysis(fundamentals=None, price=None):
    f = fundamentals or {}
    eps = _safe_float(f.get("eps"))
    estimated_eps = _safe_float(f.get("estimated_eps"))
    pe = _safe_float(f.get("pe"))
    sector_pe = _safe_float(f.get("sector_pe"))
    psr = _safe_float(f.get("psr"))
    pb = _safe_float(f.get("pb"))
    roe = _safe_float(f.get("roe"))
    roa = _safe_float(f.get("roa"))
    debt_to_equity = _safe_float(f.get("debt_to_equity"))
    revenue_growth = _safe_float(f.get("revenue_growth_pct"))
    profit_growth = _safe_float(f.get("profit_growth_pct"))
    score = 0
    reasons = []
    breakdown = {
        "eps": 0,
        "pe": 0,
        "growth": 0,
        "relative_valuation": 0,
        "psr": 0,
        "pb": 0,
        "profitability": 0,
        "growth_quality": 0,
        "leverage": 0,
    }

    if eps is not None:
        if eps > 0:
            breakdown["eps"] = 3; score += 3
            reasons.append(f"EPS مثبت است ({eps:,.0f})")
        elif eps < 0:
            breakdown["eps"] = -5; score -= 5
            reasons.append(f"EPS منفی است ({eps:,.0f})")
    else:
        reasons.append("EPS در دسترس نیست")

    if pe is None and price is not None and eps is not None and eps > 0:
        pe = float(price) / eps

    if pe is not None:
        if 0 < pe <= 8:
            breakdown["pe"] = 4; score += 4
            reasons.append(f"P/E در محدوده پایین است ({pe:.2f})")
        elif pe > 20:
            breakdown["pe"] = -4; score -= 4
            reasons.append(f"P/E بالا است ({pe:.2f})")
        elif pe > 0:
            breakdown["pe"] = 1; score += 1
            reasons.append(f"P/E مثبت و متوسط است ({pe:.2f})")
        else:
            reasons.append("P/E معتبر نیست")
    else:
        reasons.append("P/E در دسترس نیست")

    if estimated_eps is not None and eps is not None and eps != 0:
        growth = (estimated_eps / abs(eps) - 1.0) * 100.0
        if growth >= 20:
            breakdown["growth"] = 4; score += 4
        elif growth >= 5:
            breakdown["growth"] = 2; score += 2
        elif growth <= -20:
            breakdown["growth"] = -4; score -= 4
        reasons.append(f"رشد EPS برآوردی: {growth:.1f}٪")
    else:
        reasons.append("رشد EPS قابل محاسبه نیست")

    if pe is not None and sector_pe is not None and pe > 0 and sector_pe > 0:
        ratio = pe / sector_pe
        if ratio <= 0.75:
            breakdown["relative_valuation"] = 3; score += 3
        elif ratio >= 1.30:
            breakdown["relative_valuation"] = -3; score -= 3
        reasons.append(f"P/E نسبت به صنعت: {ratio:.2f}x")
    else:
        reasons.append("P/E صنعت برای مقایسه در دسترس نیست")

    if psr is not None:
        if psr <= 2:
            breakdown["psr"] = 2; score += 2
        elif psr >= 8:
            breakdown["psr"] = -2; score -= 2
        reasons.append(f"PSR: {psr:.2f}")
    else:
        reasons.append("PSR در دسترس نیست")

    if pb is not None:
        if 0 < pb <= 1.2:
            breakdown["pb"] = 2; score += 2
        elif pb >= 4:
            breakdown["pb"] = -2; score -= 2
        reasons.append(f"P/B: {pb:.2f}")
    else:
        reasons.append("P/B در دسترس نیست")

    profitability_points = 0
    if roe is not None:
        if roe >= 25:
            profitability_points += 3
        elif roe >= 15:
            profitability_points += 2
        elif roe < 5:
            profitability_points -= 2
        reasons.append(f"ROE: {roe:.1f}٪")
    if roa is not None:
        if roa >= 12:
            profitability_points += 2
        elif roa < 3:
            profitability_points -= 1
        reasons.append(f"ROA: {roa:.1f}٪")
    breakdown["profitability"] = max(-3, min(4, profitability_points))
    score += breakdown["profitability"]
    if roe is None and roa is None:
        reasons.append("ROE/ROA در دسترس نیست")

    growth_quality = 0
    if revenue_growth is not None:
        if revenue_growth >= 20:
            growth_quality += 2
        elif revenue_growth <= -20:
            growth_quality -= 2
        reasons.append(f"رشد درآمد: {revenue_growth:.1f}٪")
    if profit_growth is not None:
        if profit_growth >= 20:
            growth_quality += 3
        elif profit_growth <= -20:
            growth_quality -= 3
        reasons.append(f"رشد سود خالص: {profit_growth:.1f}٪")
    breakdown["growth_quality"] = max(-4, min(4, growth_quality))
    score += breakdown["growth_quality"]
    if revenue_growth is None and profit_growth is None:
        reasons.append("رشد درآمد/سود در دسترس نیست")

    if debt_to_equity is not None:
        if debt_to_equity <= 0.5:
            breakdown["leverage"] = 2
            score += 2
        elif debt_to_equity >= 2:
            breakdown["leverage"] = -3
            score -= 3
        reasons.append(f"بدهی به حقوق صاحبان سهام: {debt_to_equity:.2f}x")
    else:
        reasons.append("نسبت بدهی به حقوق صاحبان سهام در دسترس نیست")

    score = max(-20, min(20, score))
    return {
        "score": score,
        "eps": eps,
        "estimated_eps": estimated_eps,
        "eps_growth_pct": round((estimated_eps / abs(eps) - 1.0) * 100.0, 2) if estimated_eps is not None and eps not in (None, 0) else None,
        "pe": round(pe, 2) if pe is not None else None,
        "sector_pe": sector_pe,
        "psr": psr,
        "pb": pb,
        "roe": roe,
        "roa": roa,
        "debt_to_equity": debt_to_equity,
        "revenue_growth_pct": revenue_growth,
        "profit_growth_pct": profit_growth,
        "breakdown": breakdown,
        "reasons": reasons,
    }


def score_signal(closes, volumes=None, real_buy_ratio=None, min_score=80, fundamentals=None):
    closes = list(map(float, closes))
    raw_volumes = volumes or []
    clean_volumes = []
    for value in raw_volumes:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        # Zero is treated as missing because fallback providers may not
        # expose historical volume and previously encoded it as 0.
        if number > 0:
            clean_volumes.append(number)

    min_score = max(50, min(100, int(min_score)))

    if len(closes) < 30:
        return {
            "score": 0,
            "action": "NO_DATA",
            "reasons": ["حداقل ۳۰ قیمت لازم است"],
            "breakdown": {},
        }

    prices = np.asarray(closes, dtype=float)
    e9_series = ema(prices, 9)
    e21_series = ema(prices, 21)
    price = float(prices[-1])
    e9 = float(e9_series[-1])
    e21 = float(e21_series[-1])

    rsi_values = _rsi_series(prices, 14)
    rv = float(rsi_values[-1])

    macd_values, macd_signal_values = _macd_series(prices)
    ml = float(macd_values[-1])
    ms = float(macd_signal_values[-1])
    histogram = ml - ms
    previous_histogram = (
        float(macd_values[-2] - macd_signal_values[-2])
        if len(prices) >= 2
        else histogram
    )

    trend = _trend_status(e9, e21, price)
    trend_strength, trend_strength_status = _trend_strength(
        prices, e9_series, e21_series
    )

    rsi_divergence = _detect_divergence(
        prices, rsi_values, kind="bullish", lookback=60
    )
    rsi_bearish_divergence = _detect_divergence(
        prices, rsi_values, kind="bearish", lookback=60
    )
    macd_divergence = _detect_divergence(
        prices, macd_values, kind="bullish", lookback=60
    )
    macd_bearish_divergence = _detect_divergence(
        prices, macd_values, kind="bearish", lookback=60
    )

    score = 35
    reasons = []
    fundamentals_result = fundamental_analysis(fundamentals, price)
    fundamental_score = fundamentals_result["score"]
    breakdown = {
        "base": 35,
        "trend": 0,
        "trend_strength": 0,
        "macd": 0,
        "rsi": 0,
        "volume": 0,
        "flow": 0,
        "rsi_divergence": 0,
        "macd_divergence": 0,
        "reversal_confirmation": 0,
    }

    # 1) Direction / EMA structure: +/-10
    if price > e9 > e21:
        breakdown["trend"] = 10
        score += 10
        reasons.append("ساختار EMA صعودی است: قیمت بالای EMA9 و EMA9 بالای EMA21")
    elif price < e9 < e21:
        breakdown["trend"] = -10
        score -= 10
        reasons.append("ساختار EMA نزولی است: قیمت زیر EMA9 و EMA9 زیر EMA21")
    elif e9 > e21:
        breakdown["trend"] = 5
        score += 5
        reasons.append("EMA9 بالاتر از EMA21 است اما تأیید کامل روند صعودی وجود ندارد")
    elif e9 < e21:
        breakdown["trend"] = -5
        score -= 5
        reasons.append("EMA9 پایین‌تر از EMA21 است اما ساختار نزولی کامل نیست")

    # 2) Trend strength proxy: +/-5
    if trend_strength >= 50:
        if trend in {"صعودی", "صعودی قوی"}:
            breakdown["trend_strength"] = 5
            score += 5
            reasons.append(f"قدرت روند صعودی {trend_strength:.1f}/100 و قوی است")
        elif trend in {"نزولی", "نزولی قوی"}:
            breakdown["trend_strength"] = -5
            score -= 5
            reasons.append(f"قدرت روند نزولی {trend_strength:.1f}/100 و قوی است")
    elif trend_strength < 20:
        reasons.append(f"قدرت روند پایین است ({trend_strength:.1f}/100)؛ بازار می‌تواند خنثی باشد")
    else:
        reasons.append(f"قدرت روند متوسط است ({trend_strength:.1f}/100)")

    # 3) MACD: +/-8. A positive crossover below zero is deliberately
    # weaker than a bullish MACD above zero.
    if ml > ms:
        if ml >= 0:
            breakdown["macd"] = 8
            score += 8
            reasons.append("MACD بالای خط سیگنال و بالای صفر است؛ مومنتوم صعودی")
        else:
            breakdown["macd"] = 4
            score += 4
            reasons.append("MACD بالای خط سیگنال است اما هنوز زیر صفر قرار دارد؛ بهبود مومنتوم در روند منفی")
    else:
        breakdown["macd"] = -8
        score -= 8
        reasons.append("MACD پایین‌تر از خط سیگنال است؛ مومنتوم ضعیف/نزولی")

    if histogram > previous_histogram and ml < 0:
        reasons.append("هیستوگرام MACD در ناحیه منفی در حال بهبود است")
    elif histogram < previous_histogram and ml > 0:
        reasons.append("هیستوگرام MACD در ناحیه مثبت در حال تضعیف است")

    # 4) RSI: +/-7. Oversold alone never earns positive points.
    if 50 <= rv <= 65:
        breakdown["rsi"] = 7
        score += 7
        reasons.append("RSI در محدوده حمایتی/صعودی قرار دارد")
    elif rv > 75:
        breakdown["rsi"] = -7
        score -= 7
        reasons.append("RSI در محدوده بیش‌خرید است")
    elif rv < 30:
        reasons.append("RSI در محدوده بیش‌فروش است؛ بدون تأیید برگشت امتیاز مثبت نمی‌گیرد")
    elif rv < 45:
        reasons.append("RSI متمایل به نزول است")

    # 5) Volume: +/-5
    avg_volume = (
        sum(clean_volumes[-20:]) / 20 if len(clean_volumes) >= 20 else None
    )
    volume_current = clean_volumes[-1] if clean_volumes else None
    volume_ratio = (
        volume_current / avg_volume
        if volume_current is not None and avg_volume and avg_volume > 0
        else None
    )
    if volume_ratio is not None:
        if volume_ratio >= 1.20:
            breakdown["volume"] = 5
            score += 5
            reasons.append("حجم معاملات حداقل ۲۰٪ بالاتر از میانگین ۲۰ روزه است")
        elif volume_ratio <= 0.80:
            breakdown["volume"] = -5
            score -= 5
            reasons.append("حجم معاملات پایین‌تر از میانگین ۲۰ روزه است")
        else:
            reasons.append("حجم معاملات نزدیک به میانگین ۲۰ روزه است")
    else:
        reasons.append("حجم تاریخی معتبر برای محاسبه میانگین ۲۰روزه در دسترس نیست")

    # 6) Real/legal flow: +/-5
    if real_buy_ratio is not None:
        if real_buy_ratio >= 0.60:
            breakdown["flow"] = 5
            score += 5
            reasons.append("قدرت خرید حقیقی بالاست")
        elif real_buy_ratio <= 0.40:
            breakdown["flow"] = -5
            score -= 5
            reasons.append("قدرت فروش حقیقی بالاست")
        else:
            reasons.append("قدرت خرید و فروش حقیقی متعادل است")
    else:
        reasons.append("داده حقیقی/حقوقی در دسترس نیست؛ امتیاز جریان نقدینگی اعمال نشد")

    # 7) RSI divergence: +/-8
    if rsi_divergence == "bullish":
        breakdown["rsi_divergence"] = 8
        score += 8
        reasons.append("واگرایی مثبت RSI: قیمت کف پایین‌تر ساخته ولی RSI کف بالاتری ساخته است")
    elif rsi_bearish_divergence == "bearish":
        breakdown["rsi_divergence"] = -8
        score -= 8
        reasons.append("واگرایی منفی RSI: قیمت سقف بالاتر ساخته ولی RSI سقف پایین‌تری ساخته است")

    # 8) MACD divergence: +/-7
    if macd_divergence == "bullish":
        breakdown["macd_divergence"] = 7
        score += 7
        reasons.append("واگرایی مثبت MACD شناسایی شد؛ فشار نزولی در حال تضعیف است")
    elif macd_bearish_divergence == "bearish":
        breakdown["macd_divergence"] = -7
        score -= 7
        reasons.append("واگرایی منفی MACD شناسایی شد؛ مومنتوم صعودی در حال تضعیف است")

    # 9) Oversold reversal confirmation: 0..10
    previous_rsi = float(rsi_values[-2])
    rsi_delta = rv - previous_rsi

    if previous_rsi < 30 <= rv:
        breakdown["reversal_confirmation"] = 10
        score += 10
        reasons.append("تأیید برگشت از اشباع فروش: RSI از زیر ۳۰ به بالای ۳۰ برگشته است")
    elif previous_rsi < 35 and rv > previous_rsi and rsi_delta >= 2:
        breakdown["reversal_confirmation"] = 6
        score += 6
        reasons.append("نشانه اولیه برگشت از اشباع فروش: RSI حداقل ۲ واحد بهبود یافته است")
    elif rv < 35 and rsi_delta >= 2:
        breakdown["reversal_confirmation"] = 3
        score += 3
        reasons.append("RSI از ناحیه پایین در حال بهبود است، اما هنوز تأیید کامل برگشت ندارد")
    elif rv < 30:
        reasons.append("RSI همچنان زیر ۳۰ است؛ برگشت از اشباع فروش هنوز تأیید نشده است")

    # 10) Fundamental layer, capped at +/-15.
    breakdown["fundamental"] = fundamental_score
    score += fundamental_score
    reasons.extend([f"فاندامنتال: {item}" for item in fundamentals_result["reasons"]])

    # Divergence without price confirmation is an early warning, not a
    # standalone entry trigger.
    if (rsi_divergence == "bullish" or macd_divergence == "bullish") and rv < 35:
        reasons.append("واگرایی مثبت در کنار RSI پایین دیده می‌شود؛ برای تأیید نهایی، برگشت قیمت لازم است")

    score = max(0, min(100, int(round(score))))
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
        "rsi_previous": round(previous_rsi, 2),
        "rsi_delta": round(rsi_delta, 2),
        "rsi_status": _rsi_status(rv),
        "ema9": round(e9, 2),
        "ema21": round(e21, 2),
        "trend": trend,
        "trend_strength": trend_strength,
        "trend_strength_status": trend_strength_status,
        "macd": round(ml, 4),
        "macd_signal": round(ms, 4),
        "macd_histogram": round(histogram, 4),
        "macd_state": (
            "بالای صفر و بالای سیگنال"
            if ml >= 0 and ml > ms
            else "زیر صفر ولی بالای سیگنال"
            if ml < 0 and ml > ms
            else "بالای صفر ولی زیر سیگنال"
            if ml >= 0 and ml <= ms
            else "زیر صفر و زیر سیگنال"
        ),
        "rsi_divergence": rsi_divergence
        if rsi_divergence != "none"
        else rsi_bearish_divergence,
        "macd_divergence": macd_divergence
        if macd_divergence != "none"
        else macd_bearish_divergence,
        "reversal_confirmation": breakdown["reversal_confirmation"] > 0,
        "fundamental": fundamentals_result,
        "volume": round(volume_current, 2) if volume_current is not None else None,
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
