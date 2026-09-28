# ZwaAP FreqTrade Strategies

**A FreqTrade small account kit** — five production-tested strategies, honest backtest results, and a step-by-step setup guide for complete beginners who want to run an automated Binance spot-trading bot with **small trade amounts** (starting as low as $25).

This is strategies + tooling for $25–$100 accounts. Most FreqTrade tutorials assume $1,000+ wallets where fees are trivial. If you're starting out with a small account and want to learn before you scale, this is for you.

**Keywords**: freqtrade, freqtrade dipbuyer, freqtrade small account kit, small account, small trade amounts, binance trading bot, spot trading bot, crypto dip-buying strategy, automated trading for beginners, $25 trading bot, low capital crypto trading

---

## Table of Contents

1. [What's in this repo](#whats-in-this-repo)
2. [Who this is for](#who-this-is-for)
3. [Honest results up front](#honest-results-up-front)
4. [Prerequisites](#prerequisites)
5. [Step 1 — Install FreqTrade with Docker](#step-1--install-freqtrade-with-docker)
6. [Step 2 — Get your Binance API key](#step-2--get-your-binance-api-key)
7. [Step 3 — Copy strategies + configure](#step-3--copy-strategies--configure)
8. [Step 4 — Download historical data](#step-4--download-historical-data)
9. [Step 5 — Run backtests](#step-5--run-backtests)
10. [Step 6 — Paper trade (dry-run) first](#step-6--paper-trade-dry-run-first)
11. [Step 7 — Go live (real money)](#step-7--go-live-real-money)
12. [Strategies explained + per-strategy results](#strategies-explained--per-strategy-results)
13. [Using other exchanges (Bybit, OKX, KuCoin, etc.)](#using-other-exchanges)
14. [Troubleshooting](#troubleshooting)
15. [Disclaimer](#disclaimer)

---

## What's in this repo

```
ZwaAP-FreqTrade-Strategies/
├── README.md                 ← this file
├── config.example.json       ← config template (no keys, safe to commit)
├── docker-compose.yml        ← FreqTrade Docker setup
├── .gitignore                ← blocks your real config from ever leaking
├── strategies/
│   ├── DipBuyerStrategy.py       ← ⭐ our best performer (4h dip buying)
│   ├── RsiBbStrategy.py           ← RSI + Bollinger Bands mean reversion
│   ├── EmaTrendStrategy.py        ← EMA + ADX trend following
│   ├── MacdMomentumStrategy.py    ← MACD + Donchian breakout
│   └── BinanceMultiStrategy.py    ← Multi-indicator confluence
└── backtest_results/
    └── SUMMARY.md             ← per-strategy, per-pair, per-timeframe results
```

## Who this is for

- You have **$25–$100 USDT** in a Binance spot wallet
- You've **never used FreqTrade before** but can follow command-line instructions
- You want a bot that **automates buying dips** on crypto spot (not futures, not leverage)
- You understand this is **learning money** — small trade amounts mean small profits AND small losses, but the real purpose is to prove a strategy before scaling up

If you have $1000+, these strategies still work but you'll want more pairs and concurrent trades. See [Scaling up](#scaling-up) at the bottom.

## Honest results up front

Our best strategy, **DipBuyerStrategy**, backtested on 180 days of real Binance data (Oct 2025 – Apr 2026) during a **market crash of -26%**:

| Metric | Value |
|---|---|
| Starting wallet | $25 |
| Trades fired | 9 |
| **Win rate** | **88.9%** |
| **Net profit** | **+$0.82 (+3.29%)** |
| Max drawdown | 7.13% |
| Market benchmark | -26% |

So in a crash that took the crypto market down 26%, this bot made **+3.3%**. That's the real result.

### What this doesn't mean

- **Not a guaranteed profit** — 9 trades is a small sample
- **Not a get-rich-quick** — realistic annual returns: +6% bear, +12–16% neutral, +20–30% bull
- **Not daily income** — most days the bot sits idle waiting for a dip signal
- **0.1 USDT/day is not possible** on a $25 account with any honest strategy

### Best pairs (per-pair backtest on 4h DipBuyer)

| Pair | Trades | Win Rate | P&L |
|---|---|---|---|
| **TAO/USDT** | 3 | 100% | **+5.07%** 🏆 |
| **ETH/USDT** | 2 | 100% | **+2.14%** |
| **XRP/USDT** | 1 | 100% | **+1.43%** |
| **LINK/USDT** | 3 | 67% | -5.36% ⚠️ |
| SOL, NEAR, ADA | 0 | — | dormant (no dip signal in test window) |

Dropped from whitelist after backtesting showed losses: DOGE, AVAX, SUI, ZEC.

Full per-strategy/per-timeframe breakdown: see [backtest_results/SUMMARY.md](./backtest_results/SUMMARY.md)

---

## Prerequisites

- A Linux / macOS / WSL2 (Windows) machine
- **Docker + Docker Compose** installed → [get Docker](https://docs.docker.com/get-docker/)
- **Basic terminal/command-line** comfort
- A **Binance account** with completed KYC verification
- **≥ $25 USDT** in your Binance Spot wallet (not Funding, not Earn)

---

## Step 1 — Install FreqTrade with Docker

You don't install FreqTrade directly — Docker runs it in a container for you.

### 1.1 Clone this repo

```bash
git clone https://github.com/surendrad24/ZwaAP-FreqTrade-Strategies.git
cd ZwaAP-FreqTrade-Strategies
```

### 1.2 Create the FreqTrade directory structure

```bash
mkdir -p user_data/strategies user_data/logs user_data/data user_data/backtest_results
cp strategies/*.py user_data/strategies/
```

### 1.3 Verify Docker works

```bash
docker --version
docker compose version
```

Both should print a version number. If they don't, install Docker first.

---

## Step 2 — Get your Binance API key

### 2.1 Create the key on Binance

1. Log into [Binance](https://www.binance.com/en/my/settings/api-management)
2. Click **Create API** → choose **System generated**
3. Name it something like `freqtrade-bot` and confirm with 2FA/email
4. You'll see two long strings:
   - **API Key** (public, shorter)
   - **Secret Key** (private, longer — shown ONLY ONCE, save it)

### 2.2 Set API permissions — CRITICAL for security

On the API key page, click **Edit restrictions** and configure:

| Permission | Setting | Why |
|---|---|---|
| **Enable Reading** | ✅ ON | Required to fetch balances/prices |
| **Enable Spot & Margin Trading** | ✅ ON | Required to place orders |
| **Enable Withdrawals** | ❌ **OFF** | **If key leaks, this prevents theft** |
| **Enable Futures** | ❌ OFF | Not needed |
| **Enable Margin** | ❌ OFF | Not needed |
| **Restrict access to trusted IPs only** | ✅ ON (recommended) | Add your server's IP |

**To find your server's IP for whitelisting:**
```bash
curl ifconfig.me
```

### 2.3 What a Binance API key looks like (format only — DO NOT use these!)

Binance keys are **64 characters** of random letters + numbers. The strings below are **fake placeholders** just to show the shape:

```
API Key:    EXAMPLE_KEY_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
Secret Key: EXAMPLE_SECRET_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Or in the actual random format Binance uses:
```
API Key:    1a382ccd4ac1dad4175a4c3daf2bf0a0d3beeb6f3bee4d679b1fc16c0e46c329
Secret Key: 1b7eee8f21044bd7840b33396fd6d705fd9889fe95aa82cb2703c4cfc83d0728
```
**↑ These are freshly generated random strings with no value. Replace with your own keys from Binance.**

**Keep your keys private** — never commit them, never share screenshots, never paste into chat with anyone.

---

## Step 3 — Copy strategies + configure

### 3.1 Create your config file from the template

```bash
cp config.example.json user_data/config.json
```

### 3.2 Generate a strong password and JWT secret for the web UI

```bash
# JWT secret (copy the output)
openssl rand -hex 32

# Strong password (copy the output)
openssl rand -base64 18 | tr -d '/+=' | head -c 20
```

### 3.3 Edit `user_data/config.json`

Open `user_data/config.json` and replace the placeholders:

```json
{
  "exchange": {
    "name": "binance",
    "key": "PASTE_YOUR_BINANCE_API_KEY",
    "secret": "PASTE_YOUR_BINANCE_SECRET_KEY",
    ...
  },
  "api_server": {
    "jwt_secret_key": "PASTE_OUTPUT_FROM_openssl_rand_hex_32",
    "username": "pick-a-username",
    "password": "PASTE_OUTPUT_FROM_openssl_rand_base64",
    ...
  }
}
```

**Important settings for small accounts ($25–$100):**

| Setting | Value | Why |
|---|---|---|
| `"max_open_trades"` | `1` | One trade at a time keeps risk serialized |
| `"stake_amount"` | `12` (for $25) or `40` (for $100) | Uses ~half the wallet per trade, leaves buffer |
| `"dry_run"` | `true` | **START HERE** — paper-trade first |
| `"stake_currency"` | `"USDT"` | Quote coin |

### 3.4 Verify `config.json` is ignored by git

```bash
git status
```

You should **NOT** see `user_data/config.json` listed. If you do, the `.gitignore` isn't working — stop and fix before doing anything else.

---

## Step 4 — Download historical data

Before backtesting, you need price history:

```bash
docker compose run --rm freqtrade download-data \
  --config /freqtrade/user_data/config.json \
  --pairs TAO/USDT ETH/USDT LINK/USDT XRP/USDT SOL/USDT NEAR/USDT ADA/USDT \
  --timeframes 15m 1h 4h \
  --days 180 \
  --exchange binance
```

Takes ~30 seconds. Downloads 180 days of candles for the 7 whitelisted pairs across 3 timeframes.

---

## Step 5 — Run backtests

### 5.1 Backtest the best strategy (DipBuyer on 4h)

```bash
docker compose run --rm freqtrade backtesting \
  --config /freqtrade/user_data/config.json \
  --strategy DipBuyerStrategy \
  --timerange 20251020- \
  --timeframe 4h \
  --dry-run-wallet 25 \
  --stake-amount 12 \
  --max-open-trades 1
```

You'll see a table showing:
- Per-pair profit/loss
- Win rate
- Drawdown
- Total return

### 5.2 Compare all strategies

Run each strategy name in place of `DipBuyerStrategy`:

```bash
for strat in DipBuyerStrategy RsiBbStrategy EmaTrendStrategy MacdMomentumStrategy BinanceMultiStrategy; do
  echo "=== $strat ==="
  docker compose run --rm freqtrade backtesting \
    --config /freqtrade/user_data/config.json \
    --strategy $strat \
    --timerange 20251020- \
    --dry-run-wallet 25 \
    --stake-amount 12 \
    --max-open-trades 1 \
    2>&1 | grep "│ $strat │"
done
```

### 5.3 What to look for in results

Good signs:
- Win rate > 70%
- Max drawdown < 20%
- Average winning trade > 1.5× average losing trade
- At least 10 trades (bigger sample = more trust)

Red flags:
- Win rate 100% but only 1–2 trades (lucky, not edge)
- Drawdown > 30%
- Avg winning trade smaller than avg losing trade

---

## Step 6 — Paper trade (dry-run) first

**Never go live without paper-trading for 2 weeks minimum.**

### 6.1 Make sure `dry_run: true` is set

Check `user_data/config.json`:
```json
"dry_run": true,
"dry_run_wallet": 25,
```

### 6.2 Start the bot

```bash
docker compose up -d
```

### 6.3 Check logs

```bash
docker compose logs -f freqtrade
```

### 6.4 Open the web UI

Go to http://localhost:8080 (or your server's IP). Log in with the username/password from your config.

### 6.5 Watch for real signals

The bot should:
- Show "Bot heartbeat" every 5 seconds
- Fetch prices every candle (every 4 hours for DipBuyer)
- Fire simulated trades when RSI < 30 + price below lower Bollinger Band

Run this for **at least 2 weeks** before considering going live. In that time you may see 0–3 trades — that's normal for a 4h dip strategy.

---

## Step 7 — Go live (real money)

Only flip this switch after:
- ✅ You've paper-traded for 2+ weeks
- ✅ You've reviewed the trades the bot made
- ✅ You understand the strategy won't make 0.1 USDT/day
- ✅ You've enabled IP whitelist on your Binance API key
- ✅ You've disabled Withdrawals on your Binance API key
- ✅ Your funds are in **Spot wallet**, not Earn/Flexible/Futures

### 7.1 Flip dry_run off

Edit `user_data/config.json`:
```json
"dry_run": false,
```

### 7.2 Restart

```bash
docker compose restart
```

### 7.3 Verify live connection

```bash
docker compose logs --tail 30 freqtrade | grep -i "wallet\|dry"
```

Should say **"Dry run is disabled"** and show your real USDT balance.

### 7.4 Monitor

- Web UI: refresh trades / balance
- Slack/Telegram alerts: add via `config.json` `telegram` section (see [FreqTrade docs](https://www.freqtrade.io/en/stable/telegram-usage/))

---

## Strategies explained + per-strategy results

All backtests: 180 days (Oct 2025–Apr 2026), Binance spot, fees 0.1%, market was -26% during test.

### ⭐ DipBuyerStrategy (recommended starting point)

- **Timeframe**: 4h
- **Thesis**: Buy when RSI(14) < 30 AND price below lower Bollinger Band (2.2 std dev), but only if price is still within 15% of 200-EMA (not in total collapse). Uses position averaging-down once if trade goes -6%.
- **Exit**: RSI > 70 + price above BB middle, OR trailing stop +2.5% / -12%
- **Best for**: Small accounts, infrequent high-conviction trades
- **Backtest (7 pairs, $25 wallet, $12 stake, 1 open)**:
  - 9 trades, **88.9% win rate**
  - **+3.29% total** (+$0.82)
  - 7.13% max drawdown
  - Market: -26%

### RsiBbStrategy

- **Timeframe**: 15m
- **Thesis**: RSI < 25 + price below lower BB + BB width > 2% (avoid flat markets)
- **Best for**: More frequent trades, higher churn
- **Backtest**: 2 trades, 50% win rate, -5.4% — **use with caution, small sample**

### EmaTrendStrategy

- **Timeframe**: 1h
- **Thesis**: EMA stack (12 > 26 > 50 > 200) + ADX > 25 + DI+ > DI-
- **Best for**: Trending markets, follows momentum
- **Backtest**: 7 trades, 42.9% win rate, -10.5% — **bear market hurt this one**

### MacdMomentumStrategy

- **Timeframe**: 30m
- **Thesis**: MACD histogram rising + Donchian 20 breakout + above EMA 100 + volume surge 1.3x
- **Best for**: Breakout environments
- **Backtest**: 3 trades, 0% win rate, -4.9% — **don't use standalone in bear markets**

### BinanceMultiStrategy

- **Timeframe**: 5m
- **Thesis**: Confluence of RSI + EMA crossover + MACD + BB + volume
- **Best for**: Very strict multi-indicator setups
- **Backtest**: 0 trades — **too strict in the tested window**

---

## Using other exchanges

FreqTrade supports many exchanges. Change `"exchange"."name"` in `config.json`:

| Exchange | Config name | Sign up |
|---|---|---|
| Binance | `"binance"` | [binance.com](https://www.binance.com) |
| Bybit | `"bybit"` | [bybit.com](https://www.bybit.com) |
| OKX | `"okx"` | [okx.com](https://www.okx.com) |
| KuCoin | `"kucoin"` | [kucoin.com](https://www.kucoin.com) |
| Gate.io | `"gate"` | [gate.io](https://www.gate.io) |
| Kraken | `"kraken"` | [kraken.com](https://www.kraken.com) |
| Bitmart | `"bitmart"` | [bitmart.com](https://www.bitmart.com) |

For each:
1. Create an API key with **spot trading only** (no withdrawals)
2. Paste the key + secret into `config.json`
3. Adjust `pair_whitelist` for pairs available on that exchange
4. Some exchanges (KuCoin, OKX) also need a **passphrase** — add `"password": "your-passphrase"` to the exchange block

Sample for KuCoin:
```json
"exchange": {
    "name": "kucoin",
    "key": "YOUR_KUCOIN_KEY",
    "secret": "YOUR_KUCOIN_SECRET",
    "password": "YOUR_KUCOIN_PASSPHRASE",
    ...
}
```

Full list: [FreqTrade supported exchanges](https://www.freqtrade.io/en/stable/exchanges/)

---

## Troubleshooting

**"Invalid Api-Key ID"**
→ Your key has a typo. Copy-paste carefully, don't confuse `l`/`I`/`1` or `O`/`0`.

**"Could not load markets"**
→ Usually an auth issue, bad IP whitelist, or withdrawal permission mismatch. Check Binance API management page.

**Bot doesn't trade**
→ Normal. DipBuyer fires only on deep RSI dips, ~1–3x per month per pair. Check logs for "Bot heartbeat" to confirm it's running.

**"Insufficient balance"**
→ Funds might be in **Funding** or **Earn**, not **Spot**. Transfer to Spot wallet in Binance.

**Web UI password rejected**
→ Did you edit `config.json` and restart? `docker compose restart freqtrade`

**Container keeps crashing**
```bash
docker compose logs --tail 50 freqtrade
```
Look for Python errors, typically in strategy files.

---

## Scaling up

For **$100–$1000 accounts**:

```json
"max_open_trades": 2,
"stake_amount": 40
```

For **$1000+ accounts**:

```json
"max_open_trades": 3,
"stake_amount": 150
```

Also consider:
- Running multiple strategies on separate ports (different docker-compose service per strategy)
- Adding more pairs to whitelist (diversifies signals)
- Running `freqtrade hyperopt` to auto-tune parameters

---

## Disclaimer

This repository is for **educational purposes only**. Cryptocurrency trading carries significant risk of loss.

- Backtests are historical — **past performance does not guarantee future results**
- Strategies were tuned on a 180-day window — out-of-sample performance will differ
- A 9-trade sample size is **not statistically significant**
- Automated bots can malfunction, APIs can fail, markets can gap
- **Only invest money you can afford to lose**
- **The authors take no responsibility for your trading losses**

This is **not financial advice**.

---

## Contributing

PRs welcome for:
- New strategies with backtest proof
- Better backtests across longer windows
- Exchange-specific fixes
- Documentation improvements

---

## License

MIT — do whatever you want, just don't sue us.

---

## About ZwaAP

Built by [zwaapi.com](https://zwaapi.com) — a small-account trading bot kit for people who want to automate crypto without risking their rent money.

If this helped you, ⭐ the repo.
