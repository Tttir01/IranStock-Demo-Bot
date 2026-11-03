"""Tests for shadow logger + evaluator (counterfactual threshold)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.shadow.evaluate import evaluate_shadow_log, hypothetical_drawdown
from src.shadow.logger import build_shadow_record, log_shadow_signals, read_shadow_log


class _Cfg:
    min_score = 80
    max_symbols = 10
    symbols = ("فولاد", "فملی")
    trading_mode = "DRY_RUN"


def _fake_result(symbol, score, price, provider="TSETMC"):
    return {
        "symbol": symbol,
        "requested_symbol": symbol,
        "provider": provider,
        "price": price,
        "signal": {
            "score": score,
            "action": "BUY" if score >= 80 else ("WATCH" if score >= 60 else "NO_TRADE"),
            "min_score": 80,
            "trend": "صعودی",
            "rsi": 55,
            "volume_ratio": 1.2,
            "breakdown": {"base": 35, "trend": 10},
            "reasons": ["دلیل ۱", "دلیل ۲", "دلیل ۳"],
        },
        "flow": {"real_buy_ratio": 0.6, "retail_share": 0.8},
        "history_points": 40,
    }


def test_build_shadow_record_keeps_essential_fields():
    rec = build_shadow_record(_fake_result("فولاد", 72, 2900), cfg=_Cfg(), now="2026-11-03T00:00:00+00:00")
    assert rec["symbol"] == "فولاد"
    assert rec["score"] == 72
    assert rec["price"] == 2900
    assert rec["provider"] == "TSETMC"
    assert rec["breakdown"]["trend"] == 10
    assert len(rec["top_reasons"]) <= 5


def test_log_and_read_shadow_is_append_only(tmp_path: Path):
    p = tmp_path / "shadow.jsonl"
    cfg = _Cfg()
    results = [_fake_result("فولاد", 70, 2900), _fake_result("فملی", 55, 1500)]
    n1 = log_shadow_signals(results, cfg=cfg, path=p)
    assert n1 == 2
    assert p.exists()
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    # second append
    n2 = log_shadow_signals([_fake_result("فولاد", 80, 3000)], cfg=cfg, path=p)
    assert n2 == 1
    lines2 = p.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines2) == 3
    # read helper skips corrupt lines
    p.write_text(p.read_text(encoding="utf-8") + "not-json\n", encoding="utf-8")
    out = read_shadow_log(p)
    assert len(out) == 3


def test_evaluate_counterfactual_thresholds(tmp_path: Path):
    """Shaping a deterministic log: price rises 1% per day for 30 days for فولاد.
    Scores cycle 50,60,70,80 so we can verify threshold counts.
    """
    p = tmp_path / "shadow.jsonl"
    base = datetime(2026, 10, 1, tzinfo=timezone.utc)
    scores_cycle = [50, 60, 70, 80]
    # 30 daily records for فولاد
    for i in range(30):
        rec = {
            "time": (base + timedelta(days=i)).isoformat(),
            "symbol": "فولاد",
            "requested_symbol": "فولاد",
            "provider": "TSETMC",
            "price": 1000 * (1.01 ** i),  # 1% daily compounding
            "score": scores_cycle[i % len(scores_cycle)],
            "action": "NO_TRADE",
            "min_score": 80,
            "trend": "خنثی",
            "breakdown": {},
            "top_reasons": [],
        }
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    result = evaluate_shadow_log(p, thresholds=[55, 60, 65, 70, 75, 80], horizons=[5, 10, 20])
    assert result["total_records"] == 30
    assert result["symbols"] == ["فولاد"]
    pt = result["per_threshold"]
    # For threshold 80, only scores ==80 count → 30/4 ≈ 7 or 8
    # cycle 50,60,70,80 → 7 of 30? Let's compute: indices 3,7,11,15,19,23,27 → 7
    assert pt["80"]["signals"] == 7
    # threshold 55: scores >=55 → 60,70,80 → 3/4 of records → 22 or 23?
    # indices where score !=50: 22 records (since 30 - 8 where score=50)
    assert pt["55"]["signals"] == 22
    assert pt["60"]["signals"] == 22
    assert pt["70"]["signals"] == 14  # 70 and 80 → 7+7
    # horizon stats should have n>0 for early records
    assert pt["55"]["horizons"]["5"]["n"] > 0
    assert pt["55"]["horizons"]["10"]["n"] > 0
    # forward returns positive (price always rises)
    assert pt["55"]["horizons"]["5"]["avg"] > 0
    assert pt["55"]["horizons"]["5"]["win_rate"] == 100.0


def test_hypothetical_drawdown_positive_trend(tmp_path: Path):
    p = tmp_path / "shadow.jsonl"
    base = datetime(2026, 10, 1, tzinfo=timezone.utc)
    # monotonic rise → drawdown 0
    for i in range(20):
        rec = {
            "time": (base + timedelta(days=i)).isoformat(),
            "symbol": "فولاد",
            "price": 1000 + i * 10,
            "score": 75,
            "action": "WATCH",
            "provider": "TSETMC",
        }
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    dd = hypothetical_drawdown(p, threshold=70, horizon=5)
    assert dd["trades"] > 0
    assert dd["max_drawdown_pct"] == 0.0
    assert dd["return_pct"] > 0


def test_evaluate_empty_log(tmp_path: Path):
    p = tmp_path / "empty.jsonl"
    result = evaluate_shadow_log(p)
    assert result["total_records"] == 0
    assert result["per_threshold"] == {}
