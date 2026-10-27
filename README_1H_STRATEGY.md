# NIFTY & SENSEX 1-Hour Breakout Trading Strategy

An institutional-grade algorithmic trading strategy scanner, paper execution engine, and historical backtesting laboratory for Indian benchmark indices: **NIFTY 50** and **SENSEX**.

---

## 1. Executive Summary & Strategy Rules

### 1.1 Underlying Instruments
- **NIFTY 50 (`^NSEI`)**: Standard NSE index contract (Lot size: 25).
- **SENSEX (`^BSESN`)**: Standard BSE index contract (Lot size: 10).

### 1.2 Reference Timeframe & Candlestick Construction
- **1-Hour (1H) Reference Candlestick**:
  - The breakout levels are strictly derived from the **PREVIOUS COMPLETED 1H CANDLE's High and Low**.
  - **Moving Target Prevention**: The currently developing 1H candle is *never* used as the reference level.
  - Indian Session Hours (Asia/Kolkata - IST):
    - Candle 1: `09:15 - 10:15`
    - Candle 2: `10:15 - 11:15`
    - Candle 3: `11:15 - 12:15`
    - Candle 4: `12:15 - 13:15`
    - Candle 5: `13:15 - 14:15`
    - Candle 6: `14:15 - 15:15`
    - Candle 7: `15:15 - 15:30` (Closing partial session)
  - **Overnight Gap Policy**: By default (`carry_overnight_reference = False`), at market open 09:15 AM, the engine awaits the completion of Candle 1 (`09:15 - 10:15 AM`) before establishing reference breakout levels. This eliminates distorted trades caused by pre-market gap opens. An optional configuration toggle allows carrying forward previous day's closing 1H bar if desired.

### 1.3 BUY Entry Logic
1. Record `prev_1h_high` from the previous completed 1H candle.
2. When the live price crosses strictly above `prev_1h_high`:
   - Generate immediate **BUY BREAKOUT** signal.
   - Entry Price = Observed breakout price (subject to slippage).
   - **Target (Take Profit)** = `Entry Price + 50.0 index points`.
   - **Stop Loss** = `Entry Price - 20.0 index points`.
   - **Risk-to-Reward Ratio**: `1:2.5` (20 pts risk for 50 pts gain).

### 1.4 SELL Entry Logic
1. Record `prev_1h_low` from the previous completed 1H candle.
2. When the live price crosses strictly below `prev_1h_low`:
   - Generate immediate **SELL BREAKDOWN** signal.
   - Entry Price = Observed breakdown price (subject to slippage).
   - **Target (Take Profit)** = `Entry Price - 50.0 index points`.
   - **Stop Loss** = `Entry Price + 20.0 index points`.
   - **Risk-to-Reward Ratio**: `1:2.5` (20 pts risk for 50 pts gain).

### 1.5 Critical Quantitative Rules
- **One Entry Per Reference Candle Quota**: Only 1 trade is allowed per instrument per reference 1H candle.
- **No Re-Entry After Exit in Same Candle**: After a position exits at TP or SL, the engine enters a cooldown lock until the next completed 1H candle arrives.
- **Duplicate Prevention**: If a position is already open for an instrument, no new position can be opened.
- **Safety First**: Starts in **Paper Trading Mode** by default. Real order routing is disabled unless explicitly verified and confirmed.

---

## 2. Index Points vs. Option Premium Points

> [!IMPORTANT]
> **UNDERLYING INDEX POINTS VS. OPTIONS DELTA**:
> The strategy's 50-point target and 20-point stop loss are calculated directly on the **underlying index (Spot/Futures)**, not on options premiums.
>
> - **NIFTY 50**:
>   - 1 Lot = 25 Quantity (Default: 2 Lots = 50 Quantity).
>   - +50 Index Points Target = `50 × 50 = ₹2,500 Gross Gain`.
>   - -20 Index Points Stop Loss = `20 × 50 = ₹1,000 Gross Risk`.
> - **SENSEX**:
>   - 1 Lot = 10 Quantity (Default: 2 Lots = 20 Quantity).
>   - +50 Index Points Target = `50 × 20 = ₹1,000 Gross Gain`.
>   - -20 Index Points Stop Loss = `20 × 20 = ₹400 Gross Risk`.
>
> If an operator chooses to execute this strategy using ATM Call or Put options, an ATM option typically has a Delta ($\Delta \approx 0.50$). Therefore, a 50-point index move translates to approximately **25 option premium points**, and a 20-point index stop translates to approximately **10 option premium points**.

---

## 3. System Architecture & Module Structure

```
trading bot/
├── strategy_1h/
│   ├── __init__.py           # Package exports
│   ├── config.py             # Strategy parameters, session times, env variables
│   ├── models.py             # Dataclasses & Enums (Candle, Trade, Signal, Metrics)
│   ├── market_data.py        # Real-time quotes, 1H candle aggregator, IST timezone
│   ├── risk_manager.py       # TP/SL levels, position sizing, Indian statutory costs
│   ├── paper_trader.py       # Paper trading simulator, live MTM tracking
│   ├── engine.py             # Core state machine, candle lock, breakout evaluator
│   ├── backtester.py         # Historical backtest engine with ambiguity handling
│   ├── alerts.py             # Telegram and Webhook dispatcher with deduplication
│   ├── database.py           # SQLite persistent store (trades, signals, audit logs)
│   └── api.py                # REST API Blueprint (/api/strategy/1h/...)
├── tests/
│   ├── __init__.py
│   └── test_strategy_1h.py   # Automated unit tests
├── data/
│   └── strategy_1h.db        # SQLite database file
├── app.py                    # Unified Flask application server
└── templates/
    └── index.html            # Web Dashboard (Live Terminal + Option Chain + 1H Strategy)
```

---

## 4. Backtesting Methodology & Conservative Ambiguity Handling

### 4.1 Intra-Candle Ambiguity Resolution
When backtesting on 1-hour historical candles without sub-second tick feeds, an inherent market ambiguity occurs if a candle's High touches or exceeds the Target (`Entry + 50`), and its Low also touches or breaches the Stop Loss (`Entry - 20`).

**Naive backtesters** artificially inflate win rates by assuming the target was hit first.
**Our Quantitative Backtesting Engine adheres to strict institutional conservatism:**
- If both TP and SL are hit within the same historical candle, the engine assumes **STOP LOSS HIT FIRST** (-20 pts loss).
- The occurrence is logged as an `AMBIGUOUS_CONSERVATIVE` resolution in the scorecard.
- Look-ahead bias is strictly eliminated.

### 4.2 60-Day Benchmark Results (Empirical Reality)

| Metric | NIFTY 50 (60 Days) | SENSEX (60 Days) | Combined Portfolio |
| :--- | :--- | :--- | :--- |
| **Analyzed Period** | Last 60 Days (~360 1H Bars) | Last 60 Days (~360 1H Bars) | Last 60 Days |
| **Total Trades** | 289 | 345 | **634** |
| **Winning Trades** | 54 | 28 | **82** |
| **Losing Trades** | 235 | 317 | **552** |
| **Win Rate** | **18.69%** | **8.12%** | **12.93%** |
| **Fixed Target / SL** | +50 pts / -20 pts | +50 pts / -20 pts | +50 pts / -20 pts |
| **Gross P&L** | -₹93,800.00 | -₹105,000.00 | -₹198,800.00 |
| **Brokerage & Taxes** | ₹110,602.35 | ₹149,123.39 | ₹259,725.74 |
| **Net P&L (INR)** | **-₹204,402.35** | **-₹254,123.39** | **-₹458,525.74** |
| **Profit Factor** | 0.52 | 0.38 | **0.45** |
| **Max Drawdown (INR)** | ₹206,120.00 | ₹256,080.00 | **₹460,652.49** |
| **Ambiguous Bars** | 83 | 267 | **350** |

> [!NOTE]
> **Quantitative Takeaway for Traders**:
> On a 1-hour timeframe, a 20-point stop loss on NIFTY (at index ~22,700) represents just **0.088%**, and on SENSEX (at index ~73,600) represents just **0.027%**. In normal intraday volatility, 1H candle wicks routinely fluctuate 30–70 points. A tight 20-point stop loss on an hourly candle breakout is vulnerable to intraday noise. Users can test wider dynamic ATR stops (e.g. 50–70 pts) using the interactive Backtest Lab.

---

## 5. REST API Reference

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/strategy/1h/status` | `GET` | Scanner health, running state, NIFTY & SENSEX states |
| `/api/strategy/1h/scan` | `POST` | Triggers immediate real-time breakout scan |
| `/api/strategy/1h/control` | `POST` | Control scanner: `start`, `pause`, `resume`, `stop` |
| `/api/strategy/1h/trades` | `GET` | Returns list of open and closed paper trades |
| `/api/strategy/1h/stats` | `GET` | Realized paper win rate, P&L, profit factor, drawdown |
| `/api/strategy/1h/candles` | `GET` | Returns 1H candles for charting (`?instrument=NIFTY&period=5d`) |
| `/api/strategy/1h/backtest` | `POST` | Runs historical backtest (`instrument`, `period`, `target_points`, `stop_loss_points`) |
| `/api/strategy/1h/config` | `GET/POST` | Read or update strategy settings at runtime |

---

## 6. How to Run Locally

### 6.1 Prerequisites
- Python 3.10+
- Dependencies: `pip install flask requests curl_cffi pandas numpy yfinance`

### 6.2 Running Automated Unit Tests
```bash
python -m unittest tests/test_strategy_1h.py
```
*All 8 unit tests will verify breakout triggers, TP/SL levels, candle lock, duplicate prevention, and ambiguity handling.*

### 6.3 Starting the Terminal Dashboard
```bash
python app.py
```
Open your browser at:
**`http://127.0.0.1:5000/`**
Click on **`⚡ 1H BREAKOUT (NIFTY & SENSEX)`** in the topbar or sidebar.
