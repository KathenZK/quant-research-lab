Installation Guide for Institutional Crypto Funding Rate Analyzer
This guide outlines the steps to install and configure the Institutional Crypto Funding Rate Analyzer, a professional-grade tool for analyzing funding rates, backtesting strategies, and managing risks for crypto hedge funds.
Prerequisites

Operating System: Windows, macOS, or Linux
Python: Version 3.8 or higher
Git: For cloning the repository
Exchange API Keys: Read-only API keys for Binance, Bybit, and Kraken (optional for live data)
TimescaleDB (optional): For storing historical data
Text Editor: VS Code, PyCharm, or any editor for configuration

Step-by-Step Installation
1. Clone the Repository
Clone the repository from GitHub to your local machine:
git clone https://github.com/your-username/institutional-crypto-funding-analyzer.git
cd institutional-crypto-funding-analyzer

Replace your-username with your GitHub username or organization.
2. Install Dependencies
Install the required Python packages listed in requirements.txt:
pip install -r requirements.txt

The key dependencies include:

pandas>=2.0.0
numpy>=1.24.0
matplotlib>=3.6.0
ccxt>=4.0.0 and ccxt.pro>=4.0.0 (for exchange APIs)
sqlalchemy>=2.0.0 and timescale>=1.0.0 (for database support)
pyotp>=2.8.0 and cryptography>=40.0.0 (for security)
pyyaml>=6.0.0 (for configuration)

3. Configure API Keys

Copy the sample configuration file:cp config/config.yaml config/config.yaml


Edit config/config.yaml to add your exchange API keys and other settings:exchanges:
  binance:
    api_key: "your_binance_api_key"
    secret: "your_binance_secret"
  bybit:
    api_key: "your_bybit_api_key"
    secret: "your_bybit_secret"
  kraken:
    api_key: "your_kraken_api_key"
    secret: "your_kraken_secret"
trading:
  leverage: 5.0
  fee: 0.0004
  slippage: 0.0002
notifications:
  slack: "https://hooks.slack.com/your/webhook"
  whatsapp: "your_whatsapp_api"


Ensure read-only API keys are used for security. Do not commit config/config.yaml with sensitive data to a public repository.

4. Set Up TimescaleDB (Optional)
For storing historical funding rate data:

Install TimescaleDB (an extension of PostgreSQL) following the official guide.
Create a database and table:CREATE DATABASE funding_rates;
\c funding_rates
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE TABLE funding_rates (
    timestamp TIMESTAMPTZ NOT NULL,
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    funding_rate DECIMAL(12,8)
);
SELECT create_hypertable('funding_rates', 'timestamp');


Update config/config.yaml with the database connection details if needed.

5. Verify Installation
Test the setup by running the main analyzer script:
python -m src.funding_analyzer.core.analyzer

If API keys are not configured, the script will use the sample data in data/sample_funding_rates.csv.
6. Troubleshooting

Dependency Errors: Ensure Python 3.8+ is installed and use a virtual environment (python -m venv venv; source venv/bin/activate).
API Errors: Verify API keys and exchange connectivity. Check logs/funding_analyzer.log for details.
Database Issues: Confirm TimescaleDB is running and credentials are correct.

Next Steps
Proceed to the Usage Guide for instructions on running analyses, backtesting strategies, and generating reports.
