Usage Guide for Institutional Crypto Funding Rate Analyzer
This guide explains how to use the Institutional Crypto Funding Rate Analyzer to fetch funding rates, execute trading strategies, and analyze performance for crypto hedge funds.
Overview
The analyzer supports:

Real-Time Data: Fetches funding rates from Binance, Bybit, and Kraken via WebSocket.
Strategies: Statistical arbitrage and momentum-based trading strategies.
Backtesting: Simulates trades with leverage, fees, and slippage.
Risk Management: Calculates Value at Risk (VaR) and position sizing.
Reporting: Generates plots and CSV reports for performance analysis.
Notifications: Sends alerts via Slack, WhatsApp, or Signal.

Getting Started
Ensure the project is installed as described in the Installation Guide.
1. Run the Default Analysis
To fetch funding rates, run a statistical arbitrage backtest, and generate reports:
python -m src.funding_analyzer.core.analyzer

This:

Fetches funding rates for BTCUSDT and ETHUSDT from configured exchanges.
Applies a statistical arbitrage strategy (z-score-based).
Generates plots (data/backtest_plot.png) and a CSV report (data/backtest_results.csv).
Sends a completion alert with key metrics (e.g., Sharpe ratio).

2. Configure Custom Settings
Edit config/config.yaml to customize:

Exchanges: Add or remove exchanges (e.g., binance, bybit, kraken).
Symbols: Specify trading pairs (e.g., BTCUSDT, ETHUSDT).
Trading Parameters: Adjust leverage (default: 5x), fees (0.04%), and slippage (0.02%).
Notifications: Set up Slack or WhatsApp webhooks.

Example config/config.yaml:
exchanges:
  binance:
    api_key: "your_key"
    secret: "your_secret"
  bybit:
    api_key: "your_key"
    secret: "your_secret"
trading:
  leverage: 10.0
  fee: 0.0003
  slippage: 0.0001
notifications:
  slack: "https://hooks.slack.com/your/webhook"

3. Run a Custom Backtest
Use the FundingAnalyzer class programmatically for advanced usage:
import asyncio
from src.funding_analyzer.core.analyzer import FundingAnalyzer

# Configuration
credentials = {
    "BINANCE_API_KEY": "your_key",
    "BYBIT_API_KEY": "your_key",
    "KRAKEN_API_KEY": "your_key"
}
analyzer = FundingAnalyzer(
    exchanges=["binance", "bybit"],
    symbols=["BTCUSDT", "ETHUSDT"],
    credentials=credentials
)

# Run analysis
asyncio.run(analyzer.run())

This example runs a backtest with the default statistical arbitrage strategy.
4. Switch Strategies
To use the momentum strategy instead:
from src.funding_analyzer.strategies.momentum import MomentumStrategy

analyzer.strategy = MomentumStrategy(lookback=20, threshold=0.015)
asyncio.run(analyzer.run())


lookback: Number of periods for calculating momentum (default: 10).
threshold: Minimum momentum for a signal (default: 0.01).

5. Interpret Results

Plots: View data/backtest_plot.png for funding rate trends and cumulative returns.
CSV Report: Check data/backtest_results.csv for detailed trade data.
Logs: Review logs/funding_analyzer.log for execution details and errors.
Metrics: The script outputs key metrics like Sharpe ratio and max drawdown.

Example output:
Sharpe Ratio: 2.34, Max Drawdown: 0.0420

6. Advanced Usage

Custom Symbols: Add more trading pairs (e.g., SOLUSDT) in config.yaml.
Database Storage: Configure TimescaleDB to store historical data (see installation.md).
Notifications: Receive alerts for significant events (e.g., high funding rates) via Slack or WhatsApp.

Example: Backtest with Custom Parameters
import asyncio
from src.funding_analyzer.core.analyzer import FundingAnalyzer
from src.funding_analyzer.strategies.statistical_arb import StatisticalArbitrage

credentials = {
    "BINANCE_API_KEY": "your_key",
    "BYBIT_API_KEY": "your_key"
}
analyzer = FundingAnalyzer(
    exchanges=["binance"],
    symbols=["BTCUSDT"],
    credentials=credentials
)
analyzer.strategy = StatisticalArbitrage(lookback_period=50, entry_threshold=2.5)
asyncio.run(analyzer.run())

Troubleshooting

No Data: Ensure API keys are valid or use data/sample_funding_rates.csv.
Plotting Errors: Verify matplotlib is installed and check logs/funding_analyzer.log.
Notification Failures: Confirm webhook URLs in config.yaml.

Next Steps

Explore advanced strategies in src/funding_analyzer/strategies/.
Integrate with TimescaleDB for persistent storage.
Set up CI/CD with GitHub Actions for automated testing.


