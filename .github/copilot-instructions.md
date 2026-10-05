# Iran Stock Demo Bot — Copilot Instructions

## Mission
This repository is a Persian/Iranian stock-market analysis and paper-trading project. Keep it safe, testable, and production-quality.

## Core rules
- Default trading mode is DRY_RUN. Never enable real order submission.
- Never guess, scrape, reverse-engineer, or bypass undocumented broker APIs, MFA, anti-bot controls, or authentication.
- Never request, print, commit, or expose API keys, tokens, passwords, cookies, or account credentials.
- Agah integration is currently a safe adapter only. Treat live orders as blocked unless an officially documented and verified API is explicitly added later.
- Preserve existing Telegram, dashboard, paper-account, and data-provider behavior unless the task specifically changes it.
- Prefer fallback data providers over failing the entire scan.
- Do not silently convert data units. Confirm whether a provider returns rial/toman before changing price calculations.
- Keep paper trading deterministic and auditable.

## Project areas
- src/analysis/: indicators, screener, scanner, signal engine
- src/data/: TSETMC, Tindex, BRS clients
- src/trading/: paper account and risk management
- src/broker/: broker adapters; Agah is DRY_RUN-only
- src/main.py: orchestration, paper trading, Telegram report, dashboard
- tests/: automated tests
- .github/workflows/: scheduled/manual paper-trading workflow

## Analysis expectations
When changing signal logic, preserve or test:
- RSI, MACD, EMA
- volume and money-flow signals
- trend strength
- RSI/MACD divergence where implemented
- oversold-reversal confirmation
- fundamental inputs where available
- clear score/action/reasons output

## Safe development loop
1. Inspect the relevant files and current behavior.
2. Make the smallest coherent change.
3. Add or update tests.
4. Run pytest.
5. Check workflow configuration.
6. Never move TRADING_MODE away from DRY_RUN as part of an automatic fix.
7. Summarize changed files, tests, and remaining risks.

## Paper-trading universe
The scheduled workflow currently scans:
فولاد, فملی, شستا, وبملت, خودرو, شپنا, شبندر, کگل, کچاد, ذوب

## Failure handling
A provider outage should be reported clearly and should use configured fallback providers when possible. Do not manufacture prices, signals, or fundamentals.
