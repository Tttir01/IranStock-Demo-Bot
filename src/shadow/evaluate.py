from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from src.shadow.logger import DEFAULT_SHADOW_PATH, DEFAULT_THRESHOLDS, read_shadow_log


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        # fromisoformat handles +00:00 but not 'Z'
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _forward_return(entry: float, future: float) -> float | None:
    if not entry or not future or entry <= 0 or future <= 0:
        return None
    return (future - entry) / entry * 100.0


def evaluate_shadow_log(
    path: str | Path = DEFAULT_SHADOW_PATH,
    thresholds: list[int] | None = None,
    horizons: list[int] | None = None,
) -> dict:
    """لاگ shadow را برای تحلیل آستانه و بازده آتی ارزیابی کن.

    - horizons به روز (تقویمی) تفسیر می‌شود: برای هر سیگنال، اولین
      رکورد آینده همان نماد که >= N روز بعد باشد به‌عنوان قیمت آتی
      در نظر گرفته می‌شود. اگر چنین رکوردی نباشد، به روش fallback
      تعداد N رکورد بعدی همان نماد استفاده می‌شود.
    - thresholds: تحلیل counterfactual — هر سیگنال score>=T به‌عنوان
      «فرضاً خرید» شمرده می‌شود بدون اینکه رفتار زنده تغییر کند.

    خروجی شامل:
      - total_records, symbols, date_range
      - per_threshold: برای هر T → count, per_horizon stats
      - per_horizon_all: بدون فیلتر آستانه (برای دیدن توزیع خام امتیاز)
    """
    thresholds = thresholds or DEFAULT_THRESHOLDS
    horizons = horizons or [5, 10, 20]

    records = read_shadow_log(path)
    if not records:
        return {
            "path": str(path),
            "total_records": 0,
            "symbols": [],
            "date_range": None,
            "thresholds": thresholds,
            "horizons": horizons,
            "per_threshold": {},
            "note": "لاگ خالی است؛ هنوز اجرایی ثبت نشده.",
        }

    # مرتب‌سازی زمانی کلی؛ گروه‌بندی per-symbol برای جستجوی آتی
    def _key(r):
        dt = _parse_time(r.get("time") or "")
        return dt or datetime.min.replace(tzinfo=timezone.utc)

    records.sort(key=_key)

    by_symbol: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_symbol[str(r.get("symbol") or "")].append(r)

    # برای هر entry، نگاشت horizon -> future_price (یا None)
    # پیش‌محاسبه برای سرعت
    forward_cache: dict[int, dict[int, float | None]] = defaultdict(dict)
    # کلید: index در records کلی نیست؛ بلکه per-symbol index
    # برای هر نماد، لیست زمان‌ها را نیز نگه می‌داریم
    for symbol, lst in by_symbol.items():
        times = [_parse_time(x.get("time") or "") for x in lst]
        prices = [float(x.get("price") or 0) for x in lst]
        for i, rec in enumerate(lst):
            t0 = times[i]
            p0 = prices[i]
            if not t0 or not p0:
                continue
            for h in horizons:
                future_price = None
                # روش 1: اختلاف تقویمی >= h روز
                for j in range(i + 1, len(lst)):
                    tj = times[j]
                    pj = prices[j]
                    if not tj or not pj:
                        continue
                    delta_days = (tj - t0).total_seconds() / 86400.0
                    if delta_days >= h:
                        future_price = pj
                        break
                # روش 2: fallback اگر اختلاف تقویمی هرگز به h نرسید (مثلاً لاگ ساعتی)
                if future_price is None:
                    idx = i + h
                    if idx < len(lst):
                        pj = prices[idx]
                        if pj and pj > 0:
                            future_price = pj
                # ذخیره با کلید ترکیبی (id(rec) + h)
                forward_cache[id(rec)][h] = future_price

    # آمار per-threshold
    per_threshold: dict[str, dict] = {}
    for T in thresholds:
        bucket: dict[int, list[float]] = {h: [] for h in horizons}
        count_signals = 0
        for _, lst in by_symbol.items():
            for rec in lst:
                score = int(rec.get("score") or 0)
                price = float(rec.get("price") or 0)
                if price <= 0:
                    continue
                if score < T:
                    continue
                count_signals += 1
                for h in horizons:
                    fp = forward_cache.get(id(rec), {}).get(h)
                    if fp is None:
                        continue
                    ret = _forward_return(price, fp)
                    if ret is not None:
                        bucket[h].append(ret)

        per_h: dict[str, dict] = {}
        for h in horizons:
            rets = bucket[h]
            if not rets:
                per_h[str(h)] = {
                    "n": 0,
                    "avg": None,
                    "median": None,
                    "win_rate": None,
                    "best": None,
                    "worst": None,
                }
                continue
            per_h[str(h)] = {
                "n": len(rets),
                "avg": round(statistics.mean(rets), 2),
                "median": round(statistics.median(rets), 2),
                "win_rate": round(sum(1 for x in rets if x > 0) / len(rets) * 100, 1),
                "best": round(max(rets), 2),
                "worst": round(min(rets), 2),
            }
        per_threshold[str(T)] = {
            "signals": count_signals,
            "horizons": per_h,
        }

    # بازه زمانی
    times_all = [_parse_time(r.get("time") or "") for r in records if _parse_time(r.get("time") or "")]
    date_range = None
    if times_all:
        date_range = {
            "from": min(times_all).isoformat(),
            "to": max(times_all).isoformat(),
            "days": round((max(times_all) - min(times_all)).total_seconds() / 86400, 1),
        }

    symbols = sorted(by_symbol.keys())

    return {
        "path": str(path),
        "total_records": len(records),
        "symbols": symbols,
        "date_range": date_range,
        "thresholds": thresholds,
        "horizons": horizons,
        "per_threshold": per_threshold,
    }


def hypothetical_drawdown(
    path: str | Path = DEFAULT_SHADOW_PATH,
    threshold: int = 60,
    horizon: int = 10,
    max_position_pct: float = 0.20,
    initial_cash: float = 100_000_000,
) -> dict:
    """افت سرمایه فرضی اگر هر سیگنال >=threshold با horizon روز نگه‌داری می‌شد.

    مدل ساده: هر سیگنال واجد شرایط با 20٪ سرمایه وارد می‌شود،
    پس از horizon روز با بازده forward خارج می‌شود. معاملات
    به ترتیب زمانی اعمال می‌شوند؛ همپوشانی نادیده گرفته می‌شود
    (تقریب محافظه‌کارانه برای سنجش drawdown).
    """
    records = read_shadow_log(path)
    if not records:
        return {"threshold": threshold, "horizon": horizon, "trades": 0, "note": "لاگ خالی"}

    # نگاشت forward مشابه evaluate
    from collections import defaultdict as _dd

    by_symbol: dict[str, list[dict]] = _dd(list)
    for r in records:
        by_symbol[str(r.get("symbol") or "")].append(r)
    for lst in by_symbol.values():
        lst.sort(key=lambda x: _parse_time(x.get("time") or "") or datetime.min.replace(tzinfo=timezone.utc))

    # همه سیگنال‌های واجد شرایط را جمع‌آوری با زمان
    events: list[dict] = []
    for symbol, lst in by_symbol.items():
        times = [_parse_time(x.get("time") or "") for x in lst]
        prices = [float(x.get("price") or 0) for x in lst]
        for i, rec in enumerate(lst):
            if int(rec.get("score") or 0) < threshold:
                continue
            price = float(rec.get("price") or 0)
            if price <= 0:
                continue
            t0 = times[i]
            if not t0:
                continue
            # جستجوی آتی مشابه evaluate
            future_price = None
            for j in range(i + 1, len(lst)):
                tj = times[j]
                pj = prices[j]
                if not tj or not pj:
                    continue
                if (tj - t0).total_seconds() / 86400.0 >= horizon:
                    future_price = pj
                    break
            if future_price is None:
                idx = i + horizon
                if idx < len(lst):
                    pj = prices[idx]
                    if pj and pj > 0:
                        future_price = pj
            if future_price is None:
                continue
            ret = _forward_return(price, future_price)
            if ret is None:
                continue
            events.append({"time": t0, "symbol": symbol, "entry": price, "exit": future_price, "ret": ret})

    events.sort(key=lambda x: x["time"])
    equity = initial_cash
    peak = initial_cash
    max_dd = 0.0
    for ev in events:
        # هر معامله: 20٪ سرمایه در آن لحظه
        qty_value = equity * max_position_pct
        # بازده معامله روی همان بخش اعمال می‌شود؛ بقیه نقد می‌ماند
        equity = equity + qty_value * (ev["ret"] / 100.0)
        peak = max(peak, equity)
        dd = (peak - equity) / peak * 100 if peak else 0
        max_dd = max(max_dd, dd)

    return {
        "threshold": threshold,
        "horizon": horizon,
        "trades": len(events),
        "final_equity": round(equity, 0),
        "return_pct": round((equity - initial_cash) / initial_cash * 100, 2) if initial_cash else 0,
        "max_drawdown_pct": round(max_dd, 2),
        "peak_equity": round(peak, 0),
    }


def format_report(result: dict) -> str:
    lines: list[str] = []
    lines.append("📊 گزارش Shadow — تحلیل آستانه و بازده آتی")
    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append(f"فایل: {result.get('path')}")
    lines.append(f"تعداد رکورد: {result.get('total_records', 0)} | نمادها: {', '.join(result.get('symbols') or []) or '—'}")
    dr = result.get("date_range")
    if dr:
        lines.append(f"بازه: {dr['from']} تا {dr['to']} ({dr['days']} روز)")
    lines.append(f"آستانه‌ها: {result.get('thresholds')} | افق‌ها(روز): {result.get('horizons')}")
    lines.append("")
    per = result.get("per_threshold") or {}
    if not per:
        lines.append(result.get("note") or "داده‌ای برای تحلیل نیست.")
        return "\n".join(lines)

    # جدول ساده
    for T in sorted(per.keys(), key=lambda x: int(x)):
        info = per[T]
        lines.append(f"— آستانه {T}: سیگنال‌ها {info['signals']}")
        for h in sorted(info["horizons"].keys(), key=lambda x: int(x)):
            s = info["horizons"][h]
            if s["n"] == 0:
                lines.append(f"  افق {h} روز: n=0 (آتی کافی نیست)")
            else:
                lines.append(
                    f"  افق {h} روز: n={s['n']} | میانگین {s['avg']}٪ | میانه {s['median']}٪ | "
                    f"برد {s['win_rate']}٪ | بهترین {s['best']}٪ | بدترین {s['worst']}٪"
                )
        # drawdown فرضی برای آستانه
        dd = hypothetical_drawdown(result["path"], threshold=int(T), horizon=10)
        lines.append(
            f"  افت سرمایه فرضی (افق 10 روز، 20٪ هر معامله): "
            f"معاملات {dd['trades']} | بازده {dd['return_pct']}٪ | افت {dd['max_drawdown_pct']}٪"
        )
    lines.append("")
    lines.append("⚠️ این گزارش فقط شبیه‌سازی با داده لاگ‌شده است و توصیه سرمایه‌گذاری نیست.")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="ارزیابی لاگ shadow — بازده 5/10/20 روزه و تحلیل آستانه")
    parser.add_argument("--file", default=str(DEFAULT_SHADOW_PATH), help="مسیر فایل JSONL")
    parser.add_argument("--thresholds", default="55,60,65,70,75,80", help="لیست آستانه‌ها با کاما")
    parser.add_argument("--horizons", default="5,10,20", help="لیست افق‌ها (روز) با کاما")
    parser.add_argument("--json-out", default="", help="اگر داده شد، نتیجه JSON در این مسیر ذخیره می‌شود")
    args = parser.parse_args()

    thresholds = [int(x.strip()) for x in args.thresholds.split(",") if x.strip()]
    horizons = [int(x.strip()) for x in args.horizons.split(",") if x.strip()]

    result = evaluate_shadow_log(args.file, thresholds=thresholds, horizons=horizons)
    print(format_report(result))

    if args.json_out:
        out_p = Path(args.json_out)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON → {out_p}")


if __name__ == "__main__":
    main()
