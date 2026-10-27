<p align="center">
  <img src="static/banner.svg" alt="TradingAI Banner" width="100%">
</p>

<p align="center">
  <strong>Neural Financial Terminal &bull; Institutional Stock Scanner &bull; Quantitative Algorithmic Engine</strong>
</p>

<p align="center">
  <a href="https://github.com/harshsaini906/tradingai"><img src="https://img.shields.io/badge/GitHub-harshsaini906%2Ftradingai-38bdf8?style=for-the-badge&logo=github" alt="GitHub Repo"></a>
  <a href="#-production-deployment-guide"><img src="https://img.shields.io/badge/Deploy%20on-Render-00f59b?style=for-the-badge&logo=render" alt="Deploy to Render"></a>
  <a href="#-production-deployment-guide"><img src="https://img.shields.io/badge/Deploy%20on-Railway-c084fc?style=for-the-badge&logo=railway" alt="Deploy to Railway"></a>
  <img src="https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-blue?style=for-the-badge&logo=python" alt="Python Version">
  <img src="https://img.shields.io/badge/Status-Production%20Ready-success?style=for-the-badge" alt="Production Ready">
</p>

---

## 🌐 Live Website & Links

| Resource | Link |
| :--- | :--- |
| **GitHub Repository** | [https://github.com/harshsaini906/tradingai](https://github.com/harshsaini906/tradingai) |
| **Live Production Terminal** | `https://your-tradingai-app.onrender.com` *(Replace with your live deployed URL)* |
| **Production Health Check** | `https://your-tradingai-app.onrender.com/health` |

---

## ⚡ Key Highlights & Core Features

### 1. 2,600+ Stock Advanced Intraday Scanner & Market Regime Engine
- **Full Universe Scanning**: Scans 2,600+ NSE liquid equities in real-time batches.
- **Market Trend Detection**: Analyzes NIFTY 50, BANK NIFTY, and NIFTY 500 using multi-timeframe EMAs (EMA 20 & 50 on 5m and 15m), VWAP, Opening Range (9:15–9:30 AM), and structural High-High/Low-Low dynamics.
- **Market Regimes**: Classifies overall market as `STRONG BULLISH`, `BULLISH`, `SIDEWAYS`, `BEARISH`, `STRONG BEARISH`, or `MIXED`.
- **Dual-Side 9:45 AM Breakout Screener**:
  - Bullish: First 5-minute candle Low protected, High broken, and Previous Day High broken before 9:45 AM.
  - Bearish: First 5-minute candle High protected, Low broken, and Previous Day Low broken before 9:45 AM.

### 2. Live NSE Option Chain & Greeks Matrix (F&O Analytics)
- **Multi-Asset Matrix**: Real-time option chains for Indices (`NIFTY`, `BANKNIFTY`, `FINNIFTY`, `MIDCPNIFTY`) and top F&O equities (`RELIANCE`, `HDFCBANK`, `ICICIBANK`, `SBIN`, `TCS`, `INFY`, etc.).
- **Black-Scholes Greeks Engine**: Real-time computation of Delta ($\Delta$), Gamma ($\Gamma$), Theta ($\Theta$), and Vega ($\mathcal{V}$).
- **Quantitative Analytics HUD**:
  - **Put-Call Ratio (PCR)**: Automated directional bias classification.
  - **Max Pain Strike**: Identifies key expiry settlement gravity strike.
  - **ATM Straddle Expected Move**: Live straddle premium and expected expiry range (`[Lower Bound — Upper Bound]`).
  - **Major Support & Resistance**: Auto-detected via peak Put OI and Call OI strikes.
  - **OI Buildup Classification**: Real-time tagging for *Long Buildup*, *Short Buildup*, *Short Covering*, and *Long Unwinding*.

### 3. NIFTY 50 & SENSEX 1-Hour (1H) Breakout Quantitative Strategy
- **Previous Completed 1H High/Low Trigger**: Moving target prevention by strictly referencing closed hourly bars.
- **Fixed Risk Parameters**: 50 index points Target, 20 index points Stop Loss ($1:2.5$ Risk-to-Reward ratio).
- **Execution Rules**: Single-trade per reference candle quota and anti-re-entry locks.
- **Integrated Paper Trading Engine**: Real-time mark-to-market (MTM) tracking, trade logging to SQLite (`data/strategy_1h.db`), and automated P&L cost accounting.
- **Quantitative Backtest Lab**:
  - Zero look-ahead bias with historical hourly data.
  - **Conservative Ambiguity Handling**: If both TP and SL are hit in the same historical candle, the engine conservatively assumes Stop Loss hit first.
  - Comprehensive scorecards: Win Rate %, Profit Factor, Net INR P&L, Max Drawdown, Sharpe & Sortino ratios, and Chart.js Equity Curves.

### 4. Interactive Charts & Cyberpunk Terminal UI
- Holographic TradingView Lightweight Candlestick Charts (5m / 15m / Daily).
- Low-latency Dark Cyber Terminal with SFX audio feedback and live ticker tape.

---

## 🚀 Streamlit Community Cloud Deployment Guide (Recommended)

`TradingAI` is fully optimized for **Streamlit Community Cloud** with native caching (`@st.cache_data`), reactive UI tabs, interactive Plotly charts, and Cloud IP fallback handling.

### Step 1: Push Code to GitHub
Ensure all code and the `.streamlit/` directory are committed to your GitHub repository:
```bash
git add .
git commit -m "Convert TradingAI to Streamlit Cloud app"
git push origin main
```

### Step 2: Deploy on Streamlit Community Cloud
1. Sign in to [share.streamlit.io](https://share.streamlit.io/) using your GitHub account.
2. Click **"New app"**.
3. Fill in the repository details:
   - **Repository**: `harshsaini906/tradingai`
   - **Branch**: `main`
   - **Main file path**: `streamlit_app.py`
4. Expand **Advanced Settings**:
   - **Python Version**: `3.11` (or `3.10` / `3.12`)
   - Under **Secrets**, copy and paste the values from `.streamlit/secrets.toml.example` (add your Telegram token or Webhook URL if needed):
     ```toml
     TELEGRAM_ALERTS_ENABLED = false
     TELEGRAM_BOT_TOKEN = "your_bot_token"
     TELEGRAM_CHAT_ID = "your_chat_id"
     WEBHOOK_ALERTS_ENABLED = false
     WEBHOOK_URL = "https://discord.com/api/webhooks/your_url"
     STRATEGY_TARGET_POINTS = 50.0
     STRATEGY_STOP_LOSS_POINTS = 20.0
     USE_MOCK_DATA_FALLBACK = true
     ```
5. Click **"Deploy!"**.
6. Streamlit Cloud will automatically install dependencies from `requirements.txt` and launch your live application in under 2 minutes.

---

## 🛠️ Local Installation & Development

### 1. Clone the Repository
```bash
git clone https://github.com/harshsaini906/tradingai.git
cd tradingai
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Launch Streamlit Locally
```bash
streamlit run streamlit_app.py
```
*(Or via python executable: `python -m streamlit run streamlit_app.py`)*

Your browser will automatically open at **`http://localhost:8501`**.

---

## 🏛️ Project Architecture

```
tradingai/
├── streamlit_app.py            # Main Streamlit Application Entrypoint (7 Tabs)
├── market_service.py           # NSE/BSE fetchers, ORB scanner, search & chart services
├── advanced_scanner.py         # 2,600+ Stock scanner & macro trend engine
├── option_chain.py             # F&O Black-Scholes Greeks, PCR, Max Pain & Straddle
├── requirements.txt            # Streamlit Cloud dependencies
├── .streamlit/
│   ├── config.toml             # Custom cyberpunk dark theme configuration
│   └── secrets.toml.example    # Streamlit secrets configuration template
├── strategy_1h/                # 1H Breakout Trading Strategy package
│   ├── engine.py               # State machine & real-time trigger monitor
│   ├── backtester.py           # Quantitative backtesting simulation engine
│   ├── risk_manager.py         # 1:2.5 RR and instrument-calibrated targets/stops
│   ├── market_data.py          # 1H candle construction & historical feeds
│   ├── database.py             # SQLite trade ledger persistence
│   └── models.py               # Dataclasses & Enum definitions
├── data/
│   └── all_stocks.json         # 2,600+ listed NSE & BSE stocks database
├── static/                     # Brand SVG assets (favicon, logo, banner)
├── legacy_flask/               # Original Flask server implementation
│   ├── app.py                  # Preserved Flask application
│   ├── templates/              # Jinja2 HTML templates
│   ├── static/                 # Static JS/CSS
│   └── Dockerfile              # Docker container configuration
└── tests/
    └── test_strategy_1h.py     # Automated strategy unit test suite
```

---

## 🏛️ Alternative Deployments (Docker / Render / Railway)
The legacy Flask implementation is fully preserved inside `legacy_flask/` along with its `Dockerfile`, `Procfile`, `render.yaml`, and `railway.json` for containerized hosting.

---

## 🩺 Production Health Check & Error Handling Verification

TradingAI includes built-in endpoints for continuous monitoring and uptime verification.

### 1. Health Probe (`/health` & `/api/health`)
Perform a health probe using `curl` or any uptime monitor (UptimeRobot, Pingdom, Render Health Probes):

```bash
curl -i https://your-tradingai-app.onrender.com/health
```

**Expected JSON Response (HTTP 200 OK):**
```json
{
  "status": "UP",
  "service": "TradingAI - Neural Financial Terminal",
  "environment": "production",
  "uptime_seconds": 1284,
  "memory_rss_mb": 94.25,
  "curl_cffi_enabled": true,
  "modules": {
    "advanced_scanner": "ACTIVE",
    "option_chain": "READY",
    "strategy_1h": "READY"
  },
  "timestamp": "2026-10-27T14:55:00Z"
}
```

### 2. Error Handling Verification (HTTP 404 & 500)
- **API 404 Check**: Requesting `/api/non-existent-route` returns structured JSON:
  ```json
  { "status": "error", "code": 404, "message": "API endpoint not found: /api/non-existent-route" }
  ```
- **Web 404 Check**: Navigating to an invalid web page automatically falls back to the dashboard SPA.
- **500 Internal Error Check**: Uncaught application exceptions return sanitized JSON without exposing stack traces or server paths.

---

## 🔒 Security & Safe Secrets Management
- **No Hardcoded Secrets**: All API keys, Telegram bot tokens, and webhook URLs are strictly managed through environment variables or `.env`.
- **Pre-Configured `.gitignore`**: Excludes `.env`, SQLite runtime databases (`data/*.db`), temporary scratch files, and Python bytecode.
- **Paper Trading Safeguard**: Real-money order execution is disabled by default (`LIVE_TRADING_ENABLED=false`).

---

## 📄 License
This project is open-source under the [MIT License](LICENSE).

<p align="center">
  Built with ❤️ by <a href="https://github.com/harshsaini906">Harsh Saini</a> &bull; TradingAI Quantitative Engineering
</p>
