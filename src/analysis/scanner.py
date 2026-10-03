from __future__ import annotations

from src.analysis.signal_engine import score_signal
from src.analysis.screener import market_rows
from src.data.tsetmc_client import TsetmcError


def _price_volume(hist, client, provider_name):
    closes, volumes = [], []
    for row in hist:
        p = row.get("pClosing") or row.get("pc") or row.get("closingPrice") or row.get("pcp") or row.get("close")
        v = row.get("qTotTran5J") or row.get("tvol") or row.get("volume") or row.get("zTotTran")
        if p is None:
            continue
        closes.append(float(p) if provider_name == "Tindex" else client.rial_to_toman(p))
        if v is not None:
            try:
                if float(v) > 0:
                    volumes.append(float(v))
            except (TypeError, ValueError):
                pass
    return closes, volumes


def analyze_symbol(symbol_name, client, brs, tindex, cfg):
    provider_name = "TSETMC"
    fundamentals = {}
    codal_filings = []
    symbol = symbol_name

    try:
        try:
            found = client.resolve_symbol(symbol_name)
            ins = found.get("insCode") or found.get("InsCode")
            symbol = found.get("lVal18AFC") or found.get("LVal18AFC") or symbol_name
            hist = client.history(str(ins), 120)
            try:
                info = client.instrument_info(str(ins))
                eps_info = info.get("eps") if isinstance(info.get("eps"), dict) else {}
                fundamentals = {
                    "eps": eps_info.get("epsValue"),
                    "estimated_eps": eps_info.get("estimatedEPS"),
                    "pe": eps_info.get("pe") or eps_info.get("PE"),
                    "sector_pe": eps_info.get("sectorPE"),
                    "psr": eps_info.get("psr"),
                    "pb": eps_info.get("pb") or eps_info.get("pB"),
                    "roe": eps_info.get("roe") or eps_info.get("ROE"),
                    "roa": eps_info.get("roa") or eps_info.get("ROA"),
                    "debt_to_equity": eps_info.get("debtToEquity") or eps_info.get("debt_to_equity"),
                    "revenue_growth_pct": eps_info.get("revenueGrowthPct") or eps_info.get("revenue_growth_pct"),
                    "profit_growth_pct": eps_info.get("profitGrowthPct") or eps_info.get("profit_growth_pct"),
                }
                try:
                    codal_filings = client.codal_prepared(str(ins), 10)
                    if not isinstance(codal_filings, list):
                        codal_filings = []
                except Exception as exc:
                    print(f"CODAL METADATA UNAVAILABLE | {symbol} | {exc}")
            except Exception as exc:
                print(f"FUNDAMENTAL DATA UNAVAILABLE | {symbol} | {exc}")
            flow = client.client_type(str(ins))
        except TsetmcError as primary_exc:
            try:
                found = client.legacy_search(symbol_name)
                if not found:
                    raise TsetmcError(f"Legacy TSETMC symbol not found: {symbol_name}")
                ins = found[0].get("insCode")
                symbol = found[0].get("lVal18AFC") or symbol_name
                hist = client.legacy_history(str(ins), 120)
                flow = client.legacy_client_type(str(ins))
                provider_name = "TSETMC-LEGACY"
                print(f"DATA PROVIDER FALLBACK | {symbol} | {provider_name} | reason={primary_exc}")
            except TsetmcError as legacy_exc:
                try:
                    if not tindex.available:
                        raise TsetmcError("TINDEX_API_KEY is not configured")
                    tdata = tindex.market_data(symbol_name, "3m")
                    symbol = tdata["symbol"]
                    hist = tdata["history"]
                    flow = tdata.get("flow", [])
                    provider_name = "Tindex"
                    print(f"DATA PROVIDER FALLBACK | {symbol} | {provider_name} | reason={legacy_exc}")
                except Exception as tindex_exc:
                    if not brs.available:
                        raise TsetmcError(
                            f"{symbol_name}: TSETMC/Tindex unavailable and BRS API is not configured"
                        ) from tindex_exc
                    provider_name = "BrsApi"
                    hist = brs.history(symbol_name, 120)
                    flow = brs.client_type(symbol_name)
                    print(f"DATA PROVIDER FALLBACK | {symbol_name} | {provider_name} | reason={tindex_exc}")

        closes, volumes = _price_volume(hist, client, provider_name)
        if len(closes) < 30:
            raise TsetmcError(f"{symbol_name}: only {len(closes)} usable prices returned")

        f = flow[0] if flow else {}
        bi = float(f.get("buy_I_Volume") or f.get("Buy_I_Volume") or 0)
        bn = float(f.get("buy_N_Volume") or f.get("Buy_N_Volume") or 0)
        ratio = bi / (bi + bn) if bi + bn else None

        price = closes[-1]
        signal = score_signal(closes, volumes, ratio, cfg.min_score, fundamentals)

        return {
            "symbol": symbol,
            "requested_symbol": symbol_name,
            "provider": provider_name,
            "price": price,
            "signal": signal,
            "flow": {
                "real_buy_volume": bi,
                "legal_buy_volume": bn,
                "real_sell_volume": float(f.get("sell_I_Volume") or f.get("Sell_I_Volume") or 0),
                "legal_sell_volume": float(f.get("sell_N_Volume") or f.get("Sell_N_Volume") or 0),
                "real_buy_ratio": ratio,
            },
            "codal_filings": len(codal_filings),
            "history_points": len(closes),
        }
    except Exception as exc:
        return {
            "symbol": symbol_name,
            "requested_symbol": symbol_name,
            "provider": "UNAVAILABLE",
            "price": 0,
            "signal": {
                "score": 0,
                "action": "UNAVAILABLE",
                "reasons": [str(exc)],
                "breakdown": {},
            },
            "flow": {"real_buy_ratio": None},
            "codal_filings": 0,
            "history_points": 0,
            "error": str(exc),
        }


def scan_symbols(symbols, client, brs, tindex, cfg):
    results = []
    for symbol in tuple(symbols)[: cfg.max_symbols]:
        result = analyze_symbol(symbol, client, brs, tindex, cfg)
        results.append(result)
        signal = result["signal"]
        print(
            f"SCAN | {result['symbol']} | provider={result['provider']} | "
            f"price={result['price']:,.0f} | score={signal.get('score', 0)} | "
            f"signal={signal.get('action', 'UNAVAILABLE')}"
        )
    return results
