from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_SHADOW_PATH = Path("data/shadow-signals.jsonl")
# آستانه‌های پیش‌فرض برای تحلیل counterfactual (بدون تغییر رفتار زنده)
DEFAULT_THRESHOLDS = [55, 60, 65, 70, 75, 80]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _top_reasons(reasons: list[str], n: int = 5) -> list[str]:
    if not reasons:
        return []
    # فقط دلایل کلیدی؛ خطای provider را جدا نگه می‌داریم
    return [str(r) for r in reasons[:n]]


def build_shadow_record(item: dict, cfg=None, now: str | None = None) -> dict:
    """یک رکورد shadow از یک خروجی analyze_symbol بساز.

    عمداً سبک نگه داشته شده تا JSONL حجیم نشود ولی برای
    ارزیابی 5/10/20 روزه کافی باشد.
    """
    sig = item.get("signal") or {}
    flow = item.get("flow") or {}
    breakdown = sig.get("breakdown") or {}
    return {
        "time": now or _now_iso(),
        "symbol": item.get("symbol"),
        "requested_symbol": item.get("requested_symbol", item.get("symbol")),
        "provider": item.get("provider"),
        "price": float(item.get("price") or 0),
        "score": int(sig.get("score") or 0),
        "action": sig.get("action"),
        "min_score": int(sig.get("min_score") or (cfg.min_score if cfg and hasattr(cfg, "min_score") else 80)),
        "trend": sig.get("trend"),
        "trend_strength": sig.get("trend_strength"),
        "rsi": sig.get("rsi"),
        "volume_ratio": sig.get("volume_ratio"),
        "real_buy_ratio": flow.get("real_buy_ratio"),
        "retail_share": flow.get("retail_share"),
        "history_points": item.get("history_points", 0),
        "breakdown": breakdown,
        "top_reasons": _top_reasons(sig.get("reasons") or []),
        "error": item.get("error"),
    }


def log_shadow_signals(results: list[dict], cfg=None, path: str | Path = DEFAULT_SHADOW_PATH) -> int:
    """نتایج اسکن را به صورت append-only در JSONL ثبت کن.

    - هر نماد یک خط.
    - حتی UNAVAILABLE هم ثبت می‌شود تا نرخ دسترسی قابل‌سنجش بماند.
    - هیچ‌گاه فایل را truncate نمی‌کند.
    - مقدار برگشتی: تعداد خطوط نوشته‌شده.
    """
    if not results:
        return 0
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    now = _now_iso()
    count = 0
    with p.open("a", encoding="utf-8") as f:
        for item in results:
            rec = build_shadow_record(item, cfg=cfg, now=now)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            count += 1
    print(f"SHADOW | logged {count} records -> {p}")
    return count


def read_shadow_log(path: str | Path = DEFAULT_SHADOW_PATH) -> list[dict]:
    """کل لاگ shadow را بخوان؛ خطوط خراب نادیده گرفته می‌شوند."""
    p = Path(path)
    if not p.exists():
        return []
    out: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except (ValueError, TypeError):
            continue
    return out
