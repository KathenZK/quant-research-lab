# CFRM 422/522 Strategy Project: Funding Rate Contrarian

## Overview

This project implements and evaluates a contrarian trading strategy on BTC-USDT perpetual futures (Binance). The strategy exploits mean-reversion following extreme funding rate events.

**Core hypothesis**: When perpetual futures funding rates reach extreme z-score levels, the dominant side of the trade (longs or shorts) is crowded. These crowded positions tend to unwind within 8-24 hours, causing price to mean-revert. We trade against the crowding direction.

**Economic mechanism**: High funding rates mean longs pay 0.01% or more every 8 hours. At annualized rates of 13%+, longs reduce exposure — especially leveraged players who cannot sustain the cost. This creates predictable short-term selling pressure (Brunnermeier & Pedersen 2009).

## Key Results (Optimal Parameters: threshold=2.5, lookback=60d, hold=8h)

| Metric | Value |
|--------|-------|
| Calmar Ratio | 0.111 |
| Sharpe Ratio | 0.771 |
| Max Drawdown | 13.77% |
| Win Rate | 54.40% |
| Total Trades | 125 (2020-2024) |
| Avg Hold Period | 8 hours |

**Walk-Forward OOS Performance**

| Year | Calmar | Trades |
|------|--------|--------|
| 2021 | -0.587 | 23 |
| 2022 | -0.249 | 25 |
| 2023 | +0.567 | 28 |
| 2024 | +0.634 | 23 |

Regime note: Strategy underperformed in 2021-22 (low-funding trending bull/bear), recovered in 2023-24 as funding rate volatility returned.

## File Structure

```
Strategy-project/
|-- strategy_notebook.ipynb   # Main deliverable — all 10 graded sections
|-- generate_notebook.py      # Script that builds the notebook
|-- references.bib            # BibTeX bibliography (9 papers)
|-- README.md                 # This file
|
|-- data/
|   |-- fetch_data.py         # Downloads real Binance data (public API)
|   |-- btc_funding.csv       # BTC-USDT funding rates (2020-2024)
|   |-- btc_ohlcv_1h.csv      # BTC-USDT 1h OHLCV (2020-2024)
|   |-- eth_funding.csv       # ETH-USDT funding rates (for extension)
|   |-- eth_ohlcv_1h.csv      # ETH-USDT 1h OHLCV (for extension)
|   |-- grid_search_cache.pkl # Cached grid search results
|
|-- src/
    |-- indicators.py         # Funding z-score, cumulative, IC computation
    |-- signals.py            # Signal generation with optional OI filter
    |-- backtest.py           # Vectorized backtester, performance metrics
    |-- optimization.py       # Grid search and simulated annealing
    |-- overfitting.py        # DSR, bootstrap Sharpe, top-N removal
```

## How to Run

### 1. Install dependencies

```bash
pip install numpy pandas scipy matplotlib statsmodels jupyter nbformat requests
```

### 2. Fetch data (optional — notebook uses synthetic data if this fails)

```bash
python data/fetch_data.py --start 2020-01-01 --end 2024-12-31 --symbols BTC ETH
```

The script uses Binance's public futures API (no API key required).

### 3. Run the notebook

```bash
jupyter notebook strategy_notebook.ipynb
```

Or execute headlessly:

```bash
jupyter nbconvert --to notebook --execute strategy_notebook.ipynb --output strategy_notebook_executed.ipynb
```

### 4. Regenerate the notebook (if needed)

```bash
python generate_notebook.py
```

## Data Sources

- **Funding rates**: Binance USDT-M Futures public API (`/fapi/v1/fundingRate`)
- **OHLCV**: Binance USDT-M Futures public API (`/fapi/v1/klines`)
- **No API key required** for historical data access
- **Fallback**: If the API is unreachable, the notebook generates realistic synthetic data using GBM with regime switching and historical-style funding rate distributions. This is clearly flagged in the notebook.

## Strategy Details

### Signal Generation

```
z = (funding_rate - rolling_mean(window)) / rolling_std(window)
signal = +1 if z < -threshold  (fade crowded shorts)
signal = -1 if z > +threshold  (fade crowded longs)
signal = 0  otherwise
```

### Execution Rules

- Enter at next open after signal fires
- Hold for `hold_hours` (default: 8h, optimized in Section 7)
- Optional stop-loss at 0.5% adverse move
- Optional OI filter: skip if OI change < 1%
- Fees: 0.04% taker each side
- No leverage (1x exposure)

### Objective Function

**Calmar Ratio** = Annualized Return / Maximum Drawdown

Preferred over Sharpe because BTC return distributions have fat tails and occasional extreme positive events that inflate Sharpe artificially. Calmar focuses on the worst-case loss, which is more relevant for leveraged crypto strategies.

## Notebook Sections

| Section | Title | Points |
|---------|-------|--------|
| 0 | Setup and Imports | -- |
| 1 | Hypothesis and Testing Plan | 10 |
| 2 | Constraints, Benchmark, Objective | 10 |
| 3 | Data Description and EDA | 10 |
| 4 | Indicators (Standalone Testing) | 10 |
| 5 | Signal Processing (Standalone Testing) | 10 |
| 6 | Trading Rules (Incremental Testing) | 10 |
| 7 | Parameter Optimization | 10 |
| 8 | Walk-Forward Analysis | 10 |
| 9 | Overfitting Evaluation | 10 |
| 10 | Extension (ETH, regime, Sortino) | 10 |

## References

See `references.bib` for full citations. Key papers:

- Bailey & Lopez de Prado (2014) — Deflated Sharpe Ratio methodology
- Brunnermeier & Pedersen (2009) — Funding liquidity and market liquidity spirals
- Shleifer & Vishny (1997) — Limits of arbitrage
- Pardo (2008) — Walk-forward analysis methodology
- Liu, Tsyvinski & Wu (2022) — Cryptocurrency factor models
