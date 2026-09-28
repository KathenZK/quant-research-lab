# institutional-crypto-funding-analyzer

> **Funding-Rate Research Toolkit**: Pull historical funding rates across exchanges, run competing carry strategies through the same fee-and-slippage-aware backtest loop, and get back the same risk metrics regardless of which strategy produced them.

## The Thesis: Funding Carry Looks Free Until You Cost It

Perpetual funding rates get pitched as close to free yield: long or short the perp, collect (or pay) funding every interval, and if you're on the right side of a persistent rate, it compounds. The trap is that a Sharpe ratio computed on raw funding rates, without leverage decay, exchange fees, slippage, and cross-exchange basis risk priced in, is not a strategy result — it's a fantasy. Two different signal designs (mean-reversion in the funding rate vs. momentum in it) can look equally good on paper if neither one is forced through the same cost model, which makes strategy comparison meaningless.

This toolkit exists to remove that ambiguity. It pulls funding-rate history from configured exchanges via `ccxt`/`ccxt.pro`, runs it through one of three strategy implementations — statistical arbitrage (z-score mean reversion), momentum, or cross-exchange arbitrage — and reduces every run to the same backtest loop: position sizing, leverage, fees, and slippage applied identically regardless of which strategy generated the signal. The output is a Sharpe ratio, a max drawdown, a plot, and a CSV — comparable across strategies because the cost model never changes.

## Core Metrics Defined

- **Z-Score Signal** (statistical arbitrage): `(funding_rate - rolling_mean) / rolling_std` over a configurable `lookback_period`. A short signal (`-1`) fires above `entry_threshold`; a long signal (`+1`) fires below `-entry_threshold`; signals inside `|z| < 0.5` are flattened to `0`.
- **Momentum Signal**: rolling mean of the funding rate over `lookback` periods, compared against a fixed `threshold` to produce `+1` / `-1` / `0`.
- **Position Size**: `kelly_fraction * |signal_strength|`, capped at `max_position` (default 10% of capital) — a simplified, illustrative sizing rule rather than a fitted Kelly criterion.
- **Trade Return**: `signal * funding_rate * leverage - fee - slippage`, applied per observation — the same formula regardless of which strategy produced the signal.
- **Sharpe Ratio**: `mean(returns) / std(returns) * sqrt(365 * 3)`, annualized assuming three 8-hour funding intervals per day.
- **Max Drawdown**: `max(cummax(cumulative_returns) - cumulative_returns)` over the backtest run.
- **VaR / CVaR**: 5th-percentile historical VaR (computed only with ≥30 observations) and the mean of returns at or below that VaR threshold, respectively — in `risk/manager.py` and `risk/metrics.py`.

## Quickstart

```bash
pip install -r requirements.txt
cp .env.template .env   # fill in exchange API keys, or leave blank to fall back to sample data
```

Edit `config/config.yaml` for exchanges, symbols, leverage, fees, slippage, and (optional) Slack webhook.

Run the default analysis — fetches funding rates, runs the statistical-arbitrage backtest, plots results, and sends a completion alert:

```bash
python -m src.funding_analyzer.core.analyzer
```

No API keys? `ExchangeManager` falls back to `data/sample_funding_rates.csv` whenever a live fetch fails, so the pipeline runs end-to-end offline.

Swap in a different strategy programmatically:

```python
import asyncio
from src.funding_analyzer.core.analyzer import FundingAnalyzer
from src.funding_analyzer.strategies.momentum import MomentumStrategy

analyzer = FundingAnalyzer(
    exchanges=["binance", "bybit"],
    symbols=["BTCUSDT", "ETHUSDT"],
    credentials={"BINANCE_API_KEY": "key", "BYBIT_API_KEY": "key"},
)
analyzer.strategy = MomentumStrategy(lookback=20, threshold=0.015)
asyncio.run(analyzer.run())
```

Results land in `data/backtest_plot.png` and `data/backtest_results.csv`; execution detail goes to `logs/funding_analyzer.log`.

## Architecture

```text
config.yaml / .env
  -> ExchangeManager (ccxt.pro, per exchange/symbol)      -- falls back to data/sample_funding_rates.csv
  -> Strategy: StatisticalArbitrage | MomentumStrategy | CrossExchangeArbitrage
  -> simulate_trading loop (RiskManager position sizing, leverage/fee/slippage)
  -> PerformanceAnalyzer (Sharpe ratio, max drawdown)
  -> plot_results (matplotlib PNG)  +  send_alert (Slack webhook)
```

- `core/exchange_manager.py` — wraps `ccxt.pro` exchange instances, fetches `fetch_funding_rate_history` per symbol, and normalizes results into a flat DataFrame.
- `core/analyzer.py` — `FundingAnalyzer` orchestrates fetch → signal generation → backtest simulation → performance report → plot → alert.
- `strategies/` — `statistical_arb.py` (z-score mean reversion, implemented), `momentum.py` (rolling-mean momentum, implemented), `cross_exchange.py` (pivots funding rates across exchanges/symbols; the arbitrage signal logic itself is an unfilled placeholder), all subclassing `strategies/base.py`.
- `risk/manager.py` and `risk/metrics.py` — position sizing, historical VaR, and CVaR.
- `reporting/performance.py` and `reporting/visualizations.py` — Sharpe/drawdown computation and the matplotlib output.
- `data/storage.py` — a generic SQLAlchemy `DataStorage` class that can persist fetched rates to any SQL backend (Postgres, TimescaleDB); it exists as a utility but is not wired into the default `analyzer.py` flow.
- `utils/notifications.py` — posts a completion summary to a Slack webhook URL read from config.

## Scope / What This Is Not

- Not a live trading system: it reads funding-rate history and backtests against it, it does not place orders or manage live exchange connectivity
- `CrossExchangeArbitrage` is a scaffold — the data pivot is implemented, the actual arbitrage signal logic is not
- The Slack webhook in `config/config.yaml` is a placeholder URL; notifications require wiring in your own endpoint
- Position sizing is a simplified fixed-constant formula, not a fitted or adaptive Kelly criterion
- No order-book depth, market-impact, or borrow-cost modeling — the entire edge model is the funding rate itself
- `data/storage.py` supports persistent storage but nothing in the default flow calls it — results are written to CSV/PNG per run

## Development

```bash
pip install -r requirements.txt
pip install -e .
pytest tests/
```

See [docs/installation.md](docs/installation.md) and [docs/usage.md](docs/usage.md) for the full setup and usage walkthrough.
