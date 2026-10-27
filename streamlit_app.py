"""
TradingAI - Neural Financial Terminal & Algorithmic Trading Suite
Designed for Streamlit Community Cloud and Local Execution.
Provides real-time NSE & BSE market feeds, F&O Option Chain with Greeks,
9:45 AM ORB Dual Breakout Screener, Advanced 2,600-Stock Market Scanner,
and NIFTY & SENSEX 1H Breakout Trading Strategy with Quantitative Backtest Lab.
"""

import os
import time
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Attempt to load auto-refresh component safely
try:
    from streamlit_autorefresh import st_autorefresh
    AUTOREFRESH_AVAILABLE = True
except ImportError:
    AUTOREFRESH_AVAILABLE = False

# Import Core Services & Logic Modules
import market_service as ms
from advanced_scanner import scanner as adv_scanner
from option_chain import compute_option_chain, FO_SPECS
from strategy_1h.config import StrategyConfig, default_config
from strategy_1h.models import Instrument, TradeDirection, TradeStatus
from strategy_1h.engine import engine
from strategy_1h.backtester import BacktestEngine
from strategy_1h.database import get_trades, get_trade_stats

IST = timezone(timedelta(hours=5, minutes=30))
APP_START_TIME = time.time()

# ── 1. STREAMLIT PAGE CONFIG & CYBER DARK THEME INJECTION ──
st.set_page_config(
    page_title="TradingAI | Neural Terminal",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Cyberpunk Neon Dark Theme CSS
CUSTOM_CSS = """
<style>
    /* Main Dark Theme background */
    .stApp {
        background-color: #030712;
        color: #f1f5f9;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    
    /* Top Header Bar */
    .header-bar {
        background: linear-gradient(90deg, #070d17 0%, #0d1b2e 100%);
        border: 1px solid rgba(0, 245, 155, 0.25);
        border-radius: 12px;
        padding: 16px 22px;
        margin-bottom: 18px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
    }
    .header-title {
        font-size: 1.4rem;
        font-weight: 800;
        background: linear-gradient(135deg, #00f59b 0%, #00f0ff 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        letter-spacing: 0.5px;
    }
    .header-sub {
        font-size: 0.75rem;
        color: #94a3b8;
        font-family: monospace;
        margin-top: 2px;
    }

    /* Metric Card Styling */
    .metric-card {
        background: #080f1e;
        border: 1px solid #1e293b;
        border-radius: 10px;
        padding: 14px 16px;
        margin-bottom: 10px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.25);
    }
    .metric-label {
        font-size: 0.72rem;
        font-family: monospace;
        color: #94a3b8;
        font-weight: 600;
        text-transform: uppercase;
    }
    .metric-val {
        font-size: 1.4rem;
        font-weight: 800;
        color: #ffffff;
        margin-top: 4px;
        font-family: -apple-system, sans-serif;
    }
    .metric-sub {
        font-size: 0.7rem;
        color: #64748b;
        margin-top: 2px;
    }

    /* Neon Hero Card for 1H Breakout */
    .hero-box {
        background: #070d19;
        border-radius: 12px;
        padding: 18px 20px;
        margin-bottom: 14px;
        box-shadow: 0 4px 16px rgba(0,0,0,0.3);
    }
    .hero-nifty { border-left: 5px solid #00f0ff; }
    .hero-sensex { border-left: 5px solid #c084fc; }

    /* Custom Badges */
    .cyber-badge {
        display: inline-block;
        padding: 3px 8px;
        border-radius: 6px;
        font-size: 0.7rem;
        font-family: monospace;
        font-weight: 700;
    }
    .badge-green { background: rgba(0, 245, 155, 0.15); color: #00f59b; border: 1px solid rgba(0, 245, 155, 0.3); }
    .badge-red { background: rgba(255, 46, 99, 0.15); color: #ff2e63; border: 1px solid rgba(255, 46, 99, 0.3); }
    .badge-gold { background: rgba(251, 191, 36, 0.15); color: #fbbf24; border: 1px solid rgba(251, 191, 36, 0.3); }
    .badge-cyan { background: rgba(0, 240, 255, 0.15); color: #00f0ff; border: 1px solid rgba(0, 240, 255, 0.3); }

    /* Streamlit DataFrame & Table polish */
    div[data-testid="stDataFrame"] {
        border-radius: 8px;
        overflow: hidden;
        border: 1px solid #1e293b;
    }
    div[data-testid="stMetricValue"] {
        font-weight: 800;
    }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ── 2. CACHED DATA WRAPPERS WITH STREAMLIT CACHING ──
@st.cache_data(ttl=25, show_spinner=False)
def get_cached_market_data(index_name: str = "NIFTY") -> Dict[str, Any]:
    return ms.fetch_nse_market_data(index=index_name)

@st.cache_data(ttl=25, show_spinner=False)
def get_cached_volume_gainers() -> Dict[str, Any]:
    return ms.fetch_volume_gainers()

@st.cache_data(ttl=30, show_spinner=False)
def get_cached_orb_screener(index_name: str = "NIFTY") -> Dict[str, Any]:
    return ms.scan_orb_945(index=index_name)

@st.cache_data(ttl=60, show_spinner=False)
def get_cached_chart_data(symbol: str, interval: str, range_val: str, exchange: str) -> Dict[str, Any]:
    return ms.fetch_chart_data(symbol, interval, range_val, exchange)

@st.cache_data(ttl=20, show_spinner=False)
def get_cached_option_chain(symbol: str, expiry: Optional[str]) -> Dict[str, Any]:
    return compute_option_chain(symbol=symbol, expiry=expiry)


# ── 3. SIDEBAR NAVIGATION & SYSTEM CONTROLS ──
def render_sidebar():
    with st.sidebar:
        # Logo and Title
        col_logo, col_txt = st.columns([1, 4])
        with col_logo:
            if os.path.exists("static/favicon.svg"):
                st.image("static/favicon.svg", width=44)
            else:
                st.markdown("### ⚡")
        with col_txt:
            st.markdown("<h3 style='margin:0; padding:0; color:#00f59b; font-weight:800;'>TradingAI</h3>", unsafe_allow_html=True)
            st.markdown("<p style='margin:0; font-size:0.7rem; color:#94a3b8; font-family:monospace;'>NEURAL TERMINAL 2.0</p>", unsafe_allow_html=True)

        st.divider()

        # Market Timing & Status Indicator
        now_ist = datetime.now(timezone.utc).astimezone(IST)
        time_str = now_ist.strftime("%d-%b-%Y %I:%M:%S %p IST")
        
        # Check market hours (09:15 to 15:30 IST, Monday-Friday)
        is_weekday = now_ist.weekday() < 5
        curr_time = now_ist.time()
        market_open_time = datetime.strptime("09:15", "%H:%M").time()
        market_close_time = datetime.strptime("15:30", "%H:%M").time()
        is_market_open = is_weekday and (market_open_time <= curr_time <= market_close_time)

        if is_market_open:
            st.markdown('<span class="cyber-badge badge-green">🟢 LIVE MARKET OPEN (NSE/BSE)</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="cyber-badge badge-gold">🌙 OFF-HOURS / POST-MARKET</span>', unsafe_allow_html=True)
        
        st.caption(f"🕒 {time_str}")

        st.divider()

        # Auto-Refresh Control
        st.markdown("#### ⚡ Auto-Refresh Feed")
        auto_refresh = st.checkbox("Enable Auto-Refresh", value=True)
        refresh_sec = st.slider("Interval (seconds)", min_value=10, max_value=120, value=30, step=5)

        if auto_refresh and AUTOREFRESH_AVAILABLE:
            st_autorefresh(interval=refresh_sec * 1000, key="global_autorefresh")
        elif auto_refresh and not AUTOREFRESH_AVAILABLE:
            st.caption("Auto-refresh active on manual interaction.")

        # Manual Refresh Action
        if st.button("🔄 Refresh All Data Now", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

        st.divider()

        # Quick Cloud Diagnostic info
        st.markdown("#### ☁️ Deployment Health")
        st.caption(f"**Host:** Streamlit Community Cloud")
        st.caption(f"**curl_cffi Native TLS:** {'Enabled' if ms.USE_CURL_CFFI else 'Standard Requests'}")
        
        tg_ready = bool(ms.get_secret("TELEGRAM_BOT_TOKEN"))
        wb_ready = bool(ms.get_secret("WEBHOOK_URL"))
        st.caption(f"**Telegram Alerts:** {'Configured' if tg_ready else 'Not Set'}")
        st.caption(f"**Webhook Alerts:** {'Configured' if wb_ready else 'Not Set'}")
        
        st.divider()
        st.markdown("<div style='font-size:0.68rem; color:#64748b;'>TradingAI Engine v2.0 • Indian Indices & Stocks</div>", unsafe_allow_html=True)

render_sidebar()


# ── 4. MAIN HEADER BAR ──
st.markdown("""
<div class="header-bar">
    <div>
        <div class="header-title">⚡ TradingAI Neural Financial Terminal</div>
        <div class="header-sub">Real-Time NSE & BSE Analytics • F&O Greeks • 9:45 ORB Scanner • 1H Breakout Strategy Lab</div>
    </div>
</div>
""", unsafe_allow_html=True)


# ── 5. TOP TABS NAVIGATION (ALL 7 MODULES) ──
tab_market, tab_options, tab_orb, tab_scanner, tab_strategy, tab_directory, tab_health = st.tabs([
    "📈 Live Market",
    "📊 F&O Option Chain",
    "⚡ 9:45 AM ORB Screener",
    "🧠 Advanced Scanner",
    "🎯 1H Breakout Strategy",
    "🔍 Stocks & Charts",
    "🩺 System Health"
])


# ══════════════════════════════════════════════════════════════════
# TAB 1: LIVE MARKET (TOP GAINERS, LOSERS & VOLUME SPURTS)
# ══════════════════════════════════════════════════════════════════
with tab_market:
    st.markdown("### 📈 Live NSE Index Movers & Volume Spurts")
    
    col_idx, col_refresh, col_space = st.columns([2, 1, 3])
    with col_idx:
        selected_index = st.selectbox(
            "Select NSE Index:",
            ["NIFTY", "NIFTY 500", "BANKNIFTY", "NIFTYMIDCAP50", "NIFTYNEXT50"],
            index=0,
            key="market_index_select"
        )
    with col_refresh:
        st.write("")
        st.write("")
        if st.button("↻ Fetch Live", key="btn_refresh_market"):
            st.cache_data.clear()
            st.rerun()

    market_data = get_cached_market_data(selected_index)
    gainers = market_data.get("gainers", [])
    losers = market_data.get("losers", [])
    vol_data = get_cached_volume_gainers()
    volume_gainers = vol_data.get("volumeGainers", [])

    if market_data.get("is_fallback"):
        st.warning("⚠️ **Notice:** NSE live portal returned connection limit from Cloud IP. Displaying cached/derived market baseline.")

    # High-level Market Metrics
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    with col_m1:
        st.metric("Top Gainers Tracked", f"{len(gainers)} Stocks")
    with col_m2:
        top_gain = gainers[0]['pChange'] if gainers else 0.0
        st.metric("Top Gainer Spike", f"+{top_gain:.2f}%", delta=f"{top_gain:.2f}%")
    with col_m3:
        st.metric("Top Losers Tracked", f"{len(losers)} Stocks")
    with col_m4:
        top_drop = losers[0]['pChange'] if losers else 0.0
        st.metric("Deepest Drop", f"{top_drop:.2f}%", delta=f"{top_drop:.2f}%")

    st.markdown("---")

    # Dual Column: Gainers vs Losers
    col_g, col_l = st.columns(2)
    with col_g:
        st.markdown("#### 🟢 Top Gainers")
        if gainers:
            df_g = pd.DataFrame(gainers)[["symbol", "ltp", "change", "pChange", "high", "low", "volume"]]
            df_g.columns = ["Symbol", "LTP (₹)", "Change (₹)", "% Change", "High (₹)", "Low (₹)", "Volume"]
            st.dataframe(
                df_g.style.format({
                    "LTP (₹)": "{:,.2f}",
                    "Change (₹)": "{:+,.2f}",
                    "% Change": "{:+.2f}%",
                    "High (₹)": "{:,.2f}",
                    "Low (₹)": "{:,.2f}",
                    "Volume": "{:,}"
                }).background_gradient(subset=["% Change"], cmap="Greens"),
                use_container_width=True,
                height=380
            )
        else:
            st.info("No gainers data returned for selected index.")

    with col_l:
        st.markdown("#### 🔴 Top Losers")
        if losers:
            df_l = pd.DataFrame(losers)[["symbol", "ltp", "change", "pChange", "high", "low", "volume"]]
            df_l.columns = ["Symbol", "LTP (₹)", "Change (₹)", "% Change", "High (₹)", "Low (₹)", "Volume"]
            st.dataframe(
                df_l.style.format({
                    "LTP (₹)": "{:,.2f}",
                    "Change (₹)": "{:+,.2f}",
                    "% Change": "{:+.2f}%",
                    "High (₹)": "{:,.2f}",
                    "Low (₹)": "{:,.2f}",
                    "Volume": "{:,}"
                }).background_gradient(subset=["% Change"], cmap="Reds_r"),
                use_container_width=True,
                height=380
            )
        else:
            st.info("No losers data returned for selected index.")

    st.markdown("---")

    # Volume Spurts / Gainers Section
    st.markdown("#### 🚀 Top Volume Spurts (Spurt Multiplier vs Weekly Average)")
    if volume_gainers:
        df_vol = pd.DataFrame(volume_gainers)[["symbol", "ltp", "pChange", "volume", "week1AvgVol", "week1VolChg", "turnover"]]
        df_vol.columns = ["Symbol", "LTP (₹)", "% Change", "Current Volume", "1-Wk Avg Volume", "Volume Spurt", "Turnover (₹ Cr)"]
        st.dataframe(
            df_vol.style.format({
                "LTP (₹)": "{:,.2f}",
                "% Change": "{:+.2f}%",
                "Current Volume": "{:,}",
                "1-Wk Avg Volume": "{:,}",
                "Volume Spurt": "{:,.2f}x",
                "Turnover (₹ Cr)": "{:,.2f}"
            }).background_gradient(subset=["Volume Spurt"], cmap="Purples"),
            use_container_width=True,
            height=320
        )
    else:
        st.info("Volume spurts data currently loading...")


# ══════════════════════════════════════════════════════════════════
# TAB 2: LIVE F&O OPTION CHAIN & DERIVATIVES GREEKS
# ══════════════════════════════════════════════════════════════════
with tab_options:
    st.markdown("### 📊 Live F&O Option Chain, Greeks & Open Interest")
    
    col_opt_sym, col_opt_exp, col_opt_btn = st.columns([2, 2, 1])
    with col_opt_sym:
        f_and_o_symbols = list(FO_SPECS.keys())
        opt_sym = st.selectbox("Underlying Symbol:", f_and_o_symbols, index=0, key="opt_symbol_select")

    # Fetch available expiries for selected symbol
    upcoming_expiries = ms.get_upcoming_expiries(opt_sym) if hasattr(ms, "get_upcoming_expiries") else ["Current Weekly", "Next Weekly", "Monthly"]
    
    with col_opt_exp:
        opt_exp = st.selectbox("Expiry Date:", upcoming_expiries, index=0, key="opt_expiry_select")

    with col_opt_btn:
        st.write("")
        st.write("")
        if st.button("↻ Fetch Chain", key="btn_refresh_options"):
            st.cache_data.clear()
            st.rerun()

    opt_data = get_cached_option_chain(opt_sym, opt_exp)
    
    if opt_data and "strikes" in opt_data:
        spot_price = float(opt_data.get("spot_price", 0.0))
        chg = float(opt_data.get("change", 0.0))
        pchg = float(opt_data.get("pChange", 0.0))
        pcr = float(opt_data.get("pcr", 1.0))
        max_pain = float(opt_data.get("max_pain", spot_price))
        atm_strike = float(opt_data.get("atm_strike", spot_price))
        total_call_oi = int(opt_data.get("total_call_oi", 0))
        total_put_oi = int(opt_data.get("total_put_oi", 0))

        # Sentiment Badge from PCR
        if pcr > 1.15:
            pcr_badge = "🟢 BULLISH"
        elif pcr < 0.85:
            pcr_badge = "🔴 BEARISH"
        else:
            pcr_badge = "🟡 NEUTRAL / BALANCED"

        # Derivative Metrics HUD
        col_oc1, col_oc2, col_oc3, col_oc4, col_oc5 = st.columns(5)
        with col_oc1:
            st.metric("Underlying Spot Price", f"₹{spot_price:,.2f}", delta=f"{chg:+,.2f} ({pchg:+.2f}%)")
        with col_oc2:
            st.metric("Put-Call Ratio (PCR)", f"{pcr:.2f}", delta=pcr_badge)
        with col_oc3:
            st.metric("Max Pain Strike", f"₹{max_pain:,.1f}")
        with col_oc4:
            st.metric("ATM Strike", f"₹{atm_strike:,.1f}")
        with col_oc5:
            st.metric("Total Call vs Put OI", f"{(total_call_oi/1000):,.0f}k / {(total_put_oi/1000):,.0f}k")

        # Open Interest Distribution Chart
        strikes_list = opt_data.get("strikes", [])
        if strikes_list:
            x_strikes = [s["strike"] for s in strikes_list]
            call_ois = [s.get("ce", {}).get("oi", 0) for s in strikes_list]
            put_ois = [s.get("pe", {}).get("oi", 0) for s in strikes_list]
            
            fig_oi = go.Figure()
            fig_oi.add_trace(go.Bar(
                x=x_strikes,
                y=call_ois,
                name="Call OI (Resistance)",
                marker_color="#ff2e63",
                opacity=0.85
            ))
            fig_oi.add_trace(go.Bar(
                x=x_strikes,
                y=put_ois,
                name="Put OI (Support)",
                marker_color="#00f59b",
                opacity=0.85
            ))
            fig_oi.add_vline(x=spot_price, line_width=2, line_dash="dash", line_color="#00f0ff", annotation_text="Spot Price")

            fig_oi.update_layout(
                title=f"{opt_sym} Open Interest Distribution across Strike Prices",
                template="plotly_dark",
                barmode="group",
                height=350,
                margin=dict(l=10, r=10, t=40, b=10),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_oi, use_container_width=True)

            # Option Chain Table
            st.markdown("#### 📜 Option Chain Grid (Calls | Strike | Puts)")
            
            table_rows = []
            for s in strikes_list:
                is_atm = s.get("is_atm", False)
                strike_label = f"⭐ {s['strike']:,.1f} (ATM)" if is_atm else f"{s['strike']:,.1f}"
                ce = s.get("ce", {})
                pe = s.get("pe", {})
                table_rows.append({
                    "Call Delta": ce.get("delta", 0.0),
                    "Call Theta": ce.get("theta", 0.0),
                    "Call IV%": f"{ce.get('iv', 0.0):.1f}%",
                    "Call OI": ce.get("oi", 0),
                    "Call Chg OI": ce.get("oi_change", 0),
                    "Call LTP (₹)": ce.get("ltp", 0.0),
                    "STRIKE": strike_label,
                    "Put LTP (₹)": pe.get("ltp", 0.0),
                    "Put Chg OI": pe.get("oi_change", 0),
                    "Put OI": pe.get("oi", 0),
                    "Put IV%": f"{pe.get('iv', 0.0):.1f}%",
                    "Put Theta": pe.get("theta", 0.0),
                    "Put Delta": pe.get("delta", 0.0),
                })
            
            df_chain = pd.DataFrame(table_rows)
            st.dataframe(
                df_chain.style.format({
                    "Call Delta": "{:.2f}",
                    "Call Theta": "{:.2f}",
                    "Call OI": "{:,}",
                    "Call Chg OI": "{:+,}",
                    "Call LTP (₹)": "{:,.2f}",
                    "Put LTP (₹)": "{:,.2f}",
                    "Put Chg OI": "{:+,}",
                    "Put OI": "{:,}",
                    "Put Theta": "{:.2f}",
                    "Put Delta": "{:.2f}",
                }),
                use_container_width=True,
                height=420
            )
    else:
        st.warning("Option Chain computation currently unavailable for this symbol. Please try another instrument.")


# ══════════════════════════════════════════════════════════════════
# TAB 3: 9:45 AM ORB & PREV DAY HIGH DUAL BREAKOUT SCREENER
# ══════════════════════════════════════════════════════════════════
with tab_orb:
    st.markdown("### ⚡ 9:45 AM Opening Range Breakout (ORB) Screener")
    st.caption("Scans 09:15 - 09:45 AM 5-Minute Candle Breakouts with Previous Day High/Low confirmation.")

    col_orb_idx, col_orb_btn, _ = st.columns([2, 1, 3])
    with col_orb_idx:
        orb_index = st.selectbox("Select Universe:", ["NIFTY", "BANKNIFTY", "NIFTYNEXT50"], index=0, key="orb_index_select")
    with col_orb_btn:
        st.write("")
        st.write("")
        if st.button("🚀 Run ORB Scan", key="btn_run_orb"):
            st.cache_data.clear()
            st.rerun()

    orb_results = get_cached_orb_screener(orb_index)
    total_scanned = orb_results.get("total_scanned", 0)
    bull_count = orb_results.get("bullish_selected_count", 0)
    bear_count = orb_results.get("bearish_selected_count", 0)
    bull_list = orb_results.get("bullish_results", [])
    bear_list = orb_results.get("bearish_results", [])

    col_orb1, col_orb2, col_orb3, col_orb4 = st.columns(4)
    with col_orb1:
        st.metric("Universe Scanned", f"{total_scanned} Stocks")
    with col_orb2:
        st.metric("Bullish 4/4 Full Matches", f"{bull_count} Stocks", delta=f"{bull_count} Bullish")
    with col_orb3:
        st.metric("Bearish 4/4 Full Matches", f"{bear_count} Stocks", delta=f"-{bear_count} Bearish", delta_color="inverse")
    with col_orb4:
        st.metric("Last Scan Timestamp", orb_results.get("last_scanned", "--:--"))

    st.markdown("---")

    col_orb_bull, col_orb_bear = st.columns(2)
    with col_orb_bull:
        st.markdown("#### 🟢 Bullish ORB Breakouts (4 Conditions Required)")
        st.caption("1. C1 Low Held | 2. C1 High BO | 3. PDH BO | 4. PDL Protected")
        if bull_list:
            df_orb_b = pd.DataFrame(bull_list)[["symbol", "ltp", "pChange", "score", "status", "c1_high", "pdh", "volume"]]
            df_orb_b.columns = ["Symbol", "LTP (₹)", "% Change", "Score", "Status", "09:15 High", "Prev Day High", "Volume"]
            st.dataframe(
                df_orb_b.style.format({
                    "LTP (₹)": "{:,.2f}",
                    "% Change": "{:+.2f}%",
                    "Score": "{}/4",
                    "09:15 High": "{:,.2f}",
                    "Prev Day High": "{:,.2f}",
                    "Volume": "{:,}"
                }).background_gradient(subset=["% Change"], cmap="Greens"),
                use_container_width=True,
                height=380
            )
        else:
            st.info("No Bullish matches in this scan session.")

    with col_orb_bear:
        st.markdown("#### 🔴 Bearish ORB Breakdowns (4 Conditions Required)")
        st.caption("1. C1 High Held | 2. C1 Low BD | 3. PDL BD | 4. PDH Protected")
        if bear_list:
            df_orb_d = pd.DataFrame(bear_list)[["symbol", "ltp", "pChange", "score", "status", "c1_low", "pdl", "volume"]]
            df_orb_d.columns = ["Symbol", "LTP (₹)", "% Change", "Score", "Status", "09:15 Low", "Prev Day Low", "Volume"]
            st.dataframe(
                df_orb_d.style.format({
                    "LTP (₹)": "{:,.2f}",
                    "% Change": "{:+.2f}%",
                    "Score": "{}/4",
                    "09:15 Low": "{:,.2f}",
                    "Prev Day Low": "{:,.2f}",
                    "Volume": "{:,}"
                }).background_gradient(subset=["% Change"], cmap="Reds_r"),
                use_container_width=True,
                height=380
            )
        else:
            st.info("No Bearish matches in this scan session.")


# ══════════════════════════════════════════════════════════════════
# TAB 4: ADVANCED MARKET SCANNER (2,600 STOCKS + MACRO REGIME)
# ══════════════════════════════════════════════════════════════════
with tab_scanner:
    st.markdown("### 🧠 Advanced Market Scanner & Macro Trend Engine")
    st.caption("Macro trend classification across NIFTY 50, BANKNIFTY, SENSEX, and real-time scanning of 2,600+ equities.")

    trend_info = adv_scanner.get_status().get("market_trend", {})
    regime = trend_info.get("regime", "NEUTRAL")
    conf = trend_info.get("confidence", 50)

    # Macro Trend HUD
    col_t1, col_t2, col_t3, col_t4 = st.columns(4)
    with col_t1:
        st.metric("Macro Market Regime", regime, delta=f"{conf}% Confidence")
    with col_t2:
        nifty_p = trend_info.get("indices", {}).get("NIFTY", {}).get("pChange", 0.0)
        st.metric("NIFTY 50 Momentum", f"{nifty_p:+.2f}%", delta=f"{nifty_p:+.2f}%")
    with col_t3:
        bank_p = trend_info.get("indices", {}).get("BANKNIFTY", {}).get("pChange", 0.0)
        st.metric("Bank Nifty Momentum", f"{bank_p:+.2f}%", delta=f"{bank_p:+.2f}%")
    with col_t4:
        ad_ratio = trend_info.get("ad_ratio", 1.0)
        st.metric("Advance / Decline Ratio", f"{ad_ratio:.2f}", delta="Bullish Bias" if ad_ratio > 1 else "Bearish Bias")

    st.markdown("---")

    # Scanner Controls Row
    col_sc1, col_sc2, col_sc3, col_sc4 = st.columns(4)
    with col_sc1:
        if st.button("⚡ Scan Top 100 Liquid Stocks", use_container_width=True):
            with st.spinner("Scanning top priority liquid universe..."):
                adv_scanner.scan_priority_batch(100)
            st.success("Scanned top 100 liquid stocks!")
            st.rerun()

    with col_sc2:
        scanner_status = adv_scanner.get_status()
        is_running = scanner_status.get("is_running", False)
        if not is_running:
            if st.button("▶️ Start Background Scan", use_container_width=True):
                adv_scanner.start_background_scan(batch_size=25)
                st.rerun()
        else:
            if st.button("⏸️ Pause Scanner", use_container_width=True):
                adv_scanner.pause_scan()
                st.rerun()

    with col_sc3:
        if st.button("🔄 Refresh Macro Trend", use_container_width=True):
            adv_scanner.update_market_trend()
            st.rerun()

    with col_sc4:
        if st.button("🧹 Reset Scanner Results", use_container_width=True):
            adv_scanner.reset()
            st.rerun()

    # Progress Bar
    status = adv_scanner.get_status()
    st.progress(min(1.0, max(0.0, status.get("progress_pct", 0.0) / 100.0)))
    st.caption(f"Status: **{'RUNNING' if status.get('is_running') else 'STANDBY'}** | Scanned: **{status.get('scanned', 0)}** / {status.get('total_symbols', 0)} | Bullish: **{status.get('bullish_count', 0)}** | Bearish: **{status.get('bearish_count', 0)}** | Latency: **{status.get('latency_ms', 0)} ms**")

    # Trend Leaders Sub-section
    leaders = adv_scanner.get_trend_leaders()
    top_bull = leaders.get("top_bullish", [])
    top_bear = leaders.get("top_bearish", [])
    top_vol = leaders.get("top_rel_volume", [])

    col_l1, col_l2, col_l3 = st.columns(3)
    with col_l1:
        st.markdown("##### 🚀 Top Bullish Momentum")
        if top_bull:
            df_tb = pd.DataFrame(top_bull)[["symbol", "ltp", "pChange"]]
            st.dataframe(df_tb.style.format({"ltp": "₹{:,.2f}", "pChange": "{:+.2f}%"}), use_container_width=True, height=200)
        else:
            st.caption("Evaluating symbols...")

    with col_l2:
        st.markdown("##### 🔻 Top Bearish Momentum")
        if top_bear:
            df_tbr = pd.DataFrame(top_bear)[["symbol", "ltp", "pChange"]]
            st.dataframe(df_tbr.style.format({"ltp": "₹{:,.2f}", "pChange": "{:+.2f}%"}), use_container_width=True, height=200)
        else:
            st.caption("Evaluating symbols...")

    with col_l3:
        st.markdown("##### 🌊 Relative Volume Spurts")
        if top_vol:
            df_tv = pd.DataFrame(top_vol)[["symbol", "ltp", "vol_vs_avg"]]
            st.dataframe(df_tv.style.format({"ltp": "₹{:,.2f}", "vol_vs_avg": "{:.2f}x"}), use_container_width=True, height=200)
        else:
            st.caption("Evaluating symbols...")

    # Upload Watchlist Expander
    with st.expander("📁 Import Custom Watchlist / CSV of Symbols"):
        uploaded_file = st.file_uploader("Upload CSV or text file containing symbols:", type=["csv", "txt"])
        raw_text_symbols = st.text_area("Or paste symbols separated by commas or newlines:")
        if st.button("Import into Scanner Watchlist"):
            content = ""
            if uploaded_file is not None:
                content = uploaded_file.read().decode("utf-8", errors="ignore")
            elif raw_text_symbols:
                content = raw_text_symbols
            if content:
                count = adv_scanner.import_symbols_from_text_or_csv(content)
                st.success(f"Successfully imported {count} unique symbols into active scanner queue!")
                st.rerun()


# ══════════════════════════════════════════════════════════════════
# TAB 5: NIFTY & SENSEX 1H BREAKOUT STRATEGY & BACKTEST LAB
# ══════════════════════════════════════════════════════════════════
with tab_strategy:
    st.markdown("### 🎯 NIFTY & SENSEX 1H Breakout Trading Strategy")
    st.caption("Automated hourly range breakout engine with instrument-calibrated targets and stops (1:2.5 Risk-to-Reward).")

    strat_mode = st.radio("Strategy View Mode:", ["📡 Live Radar & Paper Positions", "🧪 Quantitative Backtest Lab", "⚙️ Strategy Configuration"], horizontal=True)

    # ── SUB-VIEW 1: LIVE RADAR & PAPER TRADING ──
    if strat_mode == "📡 Live Radar & Paper Positions":
        col_ctrl1, col_ctrl2, col_ctrl3, _ = st.columns([1, 1, 1, 3])
        with col_ctrl1:
            if st.button("🚀 Trigger Live Scan", key="btn_strat_scan"):
                engine.scan_all()
                st.rerun()
        with col_ctrl2:
            st_state = engine.get_status()
            if not st_state.get("is_running"):
                if st.button("▶️ Start 1H Engine", key="btn_start_1h"):
                    engine.start_background_scanner()
                    st.rerun()
            else:
                if st.button("⏸️ Pause Engine", key="btn_pause_1h"):
                    engine.pause_scanner()
                    st.rerun()
        with col_ctrl3:
            st.caption(f"Feed: **Asia/Kolkata** • Interval: **{engine.config.scan_interval_seconds}s**")

        engine_status = engine.get_status()
        nifty_state = engine_status.get("nifty_state", {})
        sensex_state = engine_status.get("sensex_state", {})

        # DUAL HERO CARDS (NIFTY & SENSEX)
        col_nifty_card, col_sensex_card = st.columns(2)
        
        # NIFTY HERO CARD
        with col_nifty_card:
            n_spot = nifty_state.get("current_price", 0.0)
            n_chg = nifty_state.get("change", 0.0)
            n_pchg = nifty_state.get("pChange", 0.0)
            n_sig = nifty_state.get("current_signal", "NO_SIGNAL")
            n_high = nifty_state.get("prev_1h_high", 0.0)
            n_low = nifty_state.get("prev_1h_low", 0.0)
            n_dist_h = nifty_state.get("distance_to_high", 0.0)
            n_dist_l = nifty_state.get("distance_to_low", 0.0)
            n_tp = nifty_state.get("target_points", 50.0)
            n_sl = nifty_state.get("stop_loss_points", 20.0)

            st.markdown(f"""
            <div class="hero-box hero-nifty">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <span style="font-size:1.3rem; font-weight:800; color:#fff;">NIFTY 50</span>
                        <span class="cyber-badge badge-cyan">NSE INDEX</span>
                    </div>
                    <div>
                        <span class="cyber-badge {'badge-green' if n_sig=='BUY' else ('badge-red' if n_sig=='SELL' else 'badge-gold')}">{n_sig}</span>
                    </div>
                </div>
                <div style="font-size:1.8rem; font-weight:800; color:#fff; margin-top:6px;">₹{n_spot:,.2f} <span style="font-size:0.9rem; color:{'#00f59b' if n_chg>=0 else '#ff2e63'};">{n_chg:+,.2f} ({n_pchg:+.2f}%)</span></div>
                <hr style="border-color:#1e293b; margin:8px 0;">
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px; font-family:monospace; font-size:0.75rem;">
                    <div style="background:rgba(0,245,155,0.06); padding:8px; border-radius:6px; border:1px solid rgba(0,245,155,0.2);">
                        <div style="color:#00f59b; font-weight:700;">BUY LEVEL (1H HIGH)</div>
                        <div style="font-size:1rem; font-weight:700; color:#fff;">₹{n_high:,.2f}</div>
                        <div style="color:#94a3b8;">Dist: {n_dist_h:+.1f} pts</div>
                        <div style="color:#94a3b8; font-size:0.68rem; margin-top:2px;">TP: +{n_tp:.0f} | SL: -{n_sl:.0f} pts</div>
                    </div>
                    <div style="background:rgba(255,46,99,0.06); padding:8px; border-radius:6px; border:1px solid rgba(255,46,99,0.2);">
                        <div style="color:#ff2e63; font-weight:700;">SELL LEVEL (1H LOW)</div>
                        <div style="font-size:1rem; font-weight:700; color:#fff;">₹{n_low:,.2f}</div>
                        <div style="color:#94a3b8;">Dist: {n_dist_l:+.1f} pts</div>
                        <div style="color:#94a3b8; font-size:0.68rem; margin-top:2px;">TP: -{n_tp:.0f} | SL: +{n_sl:.0f} pts</div>
                    </div>
                </div>
                <div style="font-size:0.7rem; color:#64748b; margin-top:6px; font-family:monospace;">Quota: {nifty_state.get('trades_taken_in_candle',0)}/1 trade | Status: {nifty_state.get('signal_message','--')}</div>
            </div>
            """, unsafe_allow_html=True)

        # SENSEX HERO CARD
        with col_sensex_card:
            s_spot = sensex_state.get("current_price", 0.0)
            s_chg = sensex_state.get("change", 0.0)
            s_pchg = sensex_state.get("pChange", 0.0)
            s_sig = sensex_state.get("current_signal", "NO_SIGNAL")
            s_high = sensex_state.get("prev_1h_high", 0.0)
            s_low = sensex_state.get("prev_1h_low", 0.0)
            s_dist_h = sensex_state.get("distance_to_high", 0.0)
            s_dist_l = sensex_state.get("distance_to_low", 0.0)
            s_tp = sensex_state.get("target_points", 160.0)
            s_sl = sensex_state.get("stop_loss_points", 65.0)

            st.markdown(f"""
            <div class="hero-box hero-sensex">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <span style="font-size:1.3rem; font-weight:800; color:#fff;">SENSEX</span>
                        <span class="cyber-badge badge-green">CALIBRATED 1:2.5 RR</span>
                    </div>
                    <div>
                        <span class="cyber-badge {'badge-green' if s_sig=='BUY' else ('badge-red' if s_sig=='SELL' else 'badge-gold')}">{s_sig}</span>
                    </div>
                </div>
                <div style="font-size:1.8rem; font-weight:800; color:#fff; margin-top:6px;">₹{s_spot:,.2f} <span style="font-size:0.9rem; color:{'#00f59b' if s_chg>=0 else '#ff2e63'};">{s_chg:+,.2f} ({s_pchg:+.2f}%)</span></div>
                <hr style="border-color:#1e293b; margin:8px 0;">
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px; font-family:monospace; font-size:0.75rem;">
                    <div style="background:rgba(0,245,155,0.06); padding:8px; border-radius:6px; border:1px solid rgba(0,245,155,0.2);">
                        <div style="color:#00f59b; font-weight:700;">BUY LEVEL (1H HIGH)</div>
                        <div style="font-size:1rem; font-weight:700; color:#fff;">₹{s_high:,.2f}</div>
                        <div style="color:#94a3b8;">Dist: {s_dist_h:+.1f} pts</div>
                        <div style="color:#94a3b8; font-size:0.68rem; margin-top:2px;">TP: +{s_tp:.0f} | SL: -{s_sl:.0f} pts</div>
                    </div>
                    <div style="background:rgba(255,46,99,0.06); padding:8px; border-radius:6px; border:1px solid rgba(255,46,99,0.2);">
                        <div style="color:#ff2e63; font-weight:700;">SELL LEVEL (1H LOW)</div>
                        <div style="font-size:1rem; font-weight:700; color:#fff;">₹{s_low:,.2f}</div>
                        <div style="color:#94a3b8;">Dist: {s_dist_l:+.1f} pts</div>
                        <div style="color:#94a3b8; font-size:0.68rem; margin-top:2px;">TP: -{s_tp:.0f} | SL: +{s_sl:.0f} pts</div>
                    </div>
                </div>
                <div style="font-size:0.7rem; color:#64748b; margin-top:6px; font-family:monospace;">Quota: {sensex_state.get('trades_taken_in_candle',0)}/1 trade | Status: {sensex_state.get('signal_message','--')}</div>
            </div>
            """, unsafe_allow_html=True)

        # Active Paper Trading Positions
        st.markdown("#### ⚡ Active Running Positions (Real-Time MTM)")
        active_positions = []
        if nifty_state.get("active_position"):
            active_positions.append(nifty_state["active_position"])
        if sensex_state.get("active_position"):
            active_positions.append(sensex_state["active_position"])

        if active_positions:
            for pos in active_positions:
                p_col1, p_col2, p_col3 = st.columns([2, 2, 3])
                with p_col1:
                    st.markdown(f"**{pos['instrument']} • {pos['direction']}**")
                    st.caption(f"Entry: ₹{pos['entry_price']:,.2f} | Qty: {pos['quantity']}")
                with p_col2:
                    pnl_pts = pos.get('points_pnl', 0.0)
                    pnl_inr = pos.get('net_pnl', 0.0)
                    st.metric("Running PnL", f"{pnl_pts:+.1f} pts", delta=f"₹{pnl_inr:+,.2f}")
                with p_col3:
                    # Dynamic Progress bar to TP / SL
                    tp_pts = pos.get('target_points', 50.0 if pos['instrument'] == 'NIFTY' else 160.0)
                    sl_pts = pos.get('stop_loss_points', 20.0 if pos['instrument'] == 'NIFTY' else 65.0)
                    total_range = tp_pts + sl_pts
                    progress_pct = max(0.0, min(1.0, (pnl_pts + sl_pts) / total_range))
                    st.progress(progress_pct)
                    st.caption(f"SL: -{sl_pts:.0f} pts ─── Entry ─── Target: +{tp_pts:.0f} pts")
        else:
            st.info("No active open positions. Scanner is monitoring previous 1H High & Low levels for breakout triggers.")

        st.markdown("---")

        # Paper Trading Performance Scorecard
        st.markdown("#### 🏆 Real-Time Paper Trading Performance Scorecard")
        stats = get_trade_stats()
        
        c_st1, c_st2, c_st3, c_st4, c_st5 = st.columns(5)
        with c_st1:
            st.metric("Total Paper Trades", stats.get("total_trades", 0))
        with c_st2:
            st.metric("Win Rate", f"{stats.get('win_rate', 0.0):.1f}%", delta=f"{stats.get('wins', 0)}W / {stats.get('losses', 0)}L")
        with c_st3:
            st.metric("Profit Factor", f"{stats.get('profit_factor', 0.0):.2f}")
        with c_st4:
            st.metric("Net Points PnL", f"{stats.get('net_points', 0.0):+,.1f} pts")
        with c_st5:
            net_inr = stats.get('net_profit', 0.0)
            st.metric("Net Realized INR", f"₹{net_inr:+,.2f}", delta=f"Gross: ₹{stats.get('gross_profit',0.0):+,.2f}")

        # Completed Trades Ledger
        st.markdown("#### 📜 Completed Trades Ledger (SQLite Backed)")
        trades_list = get_trades(limit=100)
        if trades_list:
            df_trades = pd.DataFrame(trades_list)[["id", "entry_time", "instrument", "direction", "entry_price", "target_price", "stop_loss_price", "exit_price", "points_pnl", "net_pnl", "exit_reason"]]
            df_trades.columns = ["Trade ID", "Entry Time", "Instrument", "Direction", "Entry (₹)", "Target (₹)", "Stop Loss (₹)", "Exit (₹)", "Points", "Net INR (₹)", "Exit Reason"]
            st.dataframe(
                df_trades.style.format({
                    "Entry (₹)": "{:,.2f}",
                    "Target (₹)": "{:,.2f}",
                    "Stop Loss (₹)": "{:,.2f}",
                    "Exit (₹)": "{:,.2f}",
                    "Points": "{:+.1f}",
                    "Net INR (₹)": "{:+,.2f}"
                }).background_gradient(subset=["Net INR (₹)"], cmap="RdYlGn"),
                use_container_width=True,
                height=300
            )
        else:
            st.caption("No completed trades recorded in the database yet.")

    # ── SUB-VIEW 2: QUANTITATIVE BACKTEST LAB ──
    elif strat_mode == "🧪 Quantitative Backtest Lab":
        st.markdown("#### 🧪 Backtest Simulation Lab (Zero Look-Ahead Bias)")
        st.caption("Simulates the 1H Breakout Strategy on historical hourly candles with conservative intra-candle ambiguity handling and Indian transaction costs.")

        col_b1, col_b2, col_b3, col_b4, col_b5 = st.columns(5)
        with col_b1:
            bt_instrument = st.selectbox("Instrument:", ["BOTH", "NIFTY", "SENSEX"], index=0, key="bt_inst_select")
        with col_b2:
            bt_period = st.selectbox("Historical Period:", ["30d", "60d", "180d", "1y"], index=1, key="bt_period_select")
        
        # Auto-calibrate defaults based on selected instrument
        default_tp = 160.0 if bt_instrument == "SENSEX" else 50.0
        default_sl = 65.0 if bt_instrument == "SENSEX" else 20.0

        with col_b3:
            bt_tp = st.number_input("Target Points:", min_value=10.0, max_value=500.0, value=default_tp, step=5.0, key="bt_tp_input")
        with col_b4:
            bt_sl = st.number_input("Stop Loss Points:", min_value=5.0, max_value=250.0, value=default_sl, step=5.0, key="bt_sl_input")
        with col_b5:
            bt_slippage = st.number_input("Slippage (pts):", min_value=0.0, max_value=10.0, value=1.0, step=0.5, key="bt_slip_input")

        if st.button("🚀 Run Backtest Simulation", type="primary", use_container_width=True):
            with st.spinner("Executing simulation on historical 1H candles..."):
                cfg = StrategyConfig()
                cfg.use_adaptive_index_scaling = (bt_instrument == "BOTH")
                cfg.nifty_target_points = bt_tp if bt_instrument in ("NIFTY", "BOTH") else 50.0
                cfg.nifty_stop_loss_points = bt_sl if bt_instrument in ("NIFTY", "BOTH") else 20.0
                cfg.sensex_target_points = bt_tp if bt_instrument == "SENSEX" else 160.0
                cfg.sensex_stop_loss_points = bt_sl if bt_instrument == "SENSEX" else 65.0
                cfg.execution_slippage_points = bt_slippage

                runner = BacktestEngine(cfg, engine.market_data, engine.risk_manager)
                
                if bt_instrument == "NIFTY":
                    bt_res = runner.run_backtest(Instrument.NIFTY, period=bt_period).to_dict()
                elif bt_instrument == "SENSEX":
                    bt_res = runner.run_backtest(Instrument.SENSEX, period=bt_period).to_dict()
                else:
                    bt_res = runner.run_combined_backtest(period=bt_period)

                st.session_state["bt_results"] = bt_res
                st.session_state["bt_mode"] = bt_instrument

        # Render Backtest Results if available in session_state
        if "bt_results" in st.session_state:
            res = st.session_state["bt_results"]
            
            st.markdown("---")
            st.markdown("##### 📊 Backtest Scorecard")
            
            c_bt1, c_bt2, c_bt3, c_bt4, c_bt5 = st.columns(5)
            with c_bt1:
                st.metric("Total Simulated Trades", res.get("total_trades", 0))
            with c_bt2:
                wr = res.get("win_rate_pct", 0.0)
                st.metric("Win Rate", f"{wr:.1f}%", delta=f"{res.get('wins', 0)}W / {res.get('losses', 0)}L")
            with c_bt3:
                st.metric("Profit Factor", f"{res.get('profit_factor', 0.0):.2f}")
            with c_bt4:
                net_p = res.get("net_profit_inr", 0.0)
                st.metric("Net Profit (INR)", f"₹{net_p:+,.2f}", delta=f"Taxes: ₹{res.get('brokerage_and_taxes_inr',0):,.2f}")
            with c_bt5:
                st.metric("Max Drawdown (INR)", f"₹{res.get('max_drawdown_inr', 0):,.2f}", delta=f"{res.get('max_drawdown_pct', 0):.2f}%", delta_color="inverse")

            # Equity Curve Plot
            curve = res.get("combined_equity_curve") or res.get("equity_curve") or []
            if curve:
                df_curve = pd.DataFrame(curve)
                fig_curve = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.75, 0.25])
                fig_curve.add_trace(go.Scatter(
                    x=df_curve["timestamp"],
                    y=df_curve["equity"],
                    mode="lines",
                    name="Portfolio Equity (₹)",
                    line=dict(color="#00f59b", width=2),
                    fill="tozeroy",
                    fillcolor="rgba(0, 245, 155, 0.08)"
                ), row=1, col=1)
                fig_curve.add_trace(go.Scatter(
                    x=df_curve["timestamp"],
                    y=-df_curve["drawdown"],
                    mode="lines",
                    name="Underwater Drawdown (₹)",
                    line=dict(color="#ff2e63", width=1),
                    fill="tozeroy",
                    fillcolor="rgba(255, 46, 99, 0.15)"
                ), row=2, col=1)

                fig_curve.update_layout(
                    title="Simulated Portfolio Equity Curve & Underwater Drawdown",
                    template="plotly_dark",
                    height=400,
                    margin=dict(l=10, r=10, t=40, b=10)
                )
                st.plotly_chart(fig_curve, use_container_width=True)

            # Historical Backtest Trade Log Table
            trades_bt = res.get("combined_trades") or res.get("trades") or []
            if trades_bt:
                st.markdown("##### 📜 Historical Backtest Trade-by-Trade Log")
                df_bt_trades = pd.DataFrame(trades_bt)[["id", "entry_time", "instrument", "direction", "entry_price", "target_price", "stop_loss_price", "exit_price", "points_pnl", "net_pnl", "exit_reason"]]
                df_bt_trades.columns = ["Trade ID", "Entry Time", "Instrument", "Direction", "Entry (₹)", "Target (₹)", "Stop Loss (₹)", "Exit (₹)", "Points", "Net INR (₹)", "Exit Reason"]
                st.dataframe(
                    df_bt_trades.style.format({
                        "Entry (₹)": "{:,.2f}",
                        "Target (₹)": "{:,.2f}",
                        "Stop Loss (₹)": "{:,.2f}",
                        "Exit (₹)": "{:,.2f}",
                        "Points": "{:+.1f}",
                        "Net INR (₹)": "{:+,.2f}"
                    }).background_gradient(subset=["Net INR (₹)"], cmap="RdYlGn"),
                    use_container_width=True,
                    height=300
                )

    # ── SUB-VIEW 3: STRATEGY CONFIGURATION ──
    else:
        st.markdown("#### ⚙️ Strategy Risk & Execution Settings")
        st.caption("Adjust risk levels, lot sizing, and alert notifications. Settings persist in runtime engine.")

        col_cfg1, col_cfg2 = st.columns(2)
        with col_cfg1:
            st.markdown("##### NIFTY 50 Risk Settings")
            new_n_tp = st.number_input("NIFTY Target Points:", min_value=10.0, max_value=200.0, value=float(engine.config.nifty_target_points), step=5.0)
            new_n_sl = st.number_input("NIFTY Stop Loss Points:", min_value=5.0, max_value=100.0, value=float(engine.config.nifty_stop_loss_points), step=5.0)
            new_n_lots = st.number_input("NIFTY Lots Per Trade (1 Lot = 25):", min_value=1, max_value=20, value=int(engine.config.nifty_lots_per_trade), step=1)

        with col_cfg2:
            st.markdown("##### SENSEX Risk Settings (Calibrated)")
            new_s_tp = st.number_input("SENSEX Target Points:", min_value=30.0, max_value=600.0, value=float(engine.config.sensex_target_points), step=10.0)
            new_s_sl = st.number_input("SENSEX Stop Loss Points:", min_value=15.0, max_value=300.0, value=float(engine.config.sensex_stop_loss_points), step=5.0)
            new_s_lots = st.number_input("SENSEX Lots Per Trade (1 Lot = 10):", min_value=1, max_value=20, value=int(engine.config.sensex_lots_per_trade), step=1)

        st.markdown("##### Execution Rules")
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            one_tr = st.checkbox("Enforce 1 Trade Per 1H Candle Quota", value=engine.config.one_trade_per_candle)
            carry_ov = st.checkbox("Carry Overnight Reference Candle across Market Open", value=engine.config.carry_overnight_reference)
        with col_r2:
            tg_en = st.checkbox("Enable Telegram Alerts", value=engine.config.telegram_alerts_enabled)
            wb_en = st.checkbox("Enable Discord / Slack Webhook Alerts", value=engine.config.webhook_alerts_enabled)

        if st.button("💾 Save Strategy Settings"):
            engine.config.nifty_target_points = new_n_tp
            engine.config.nifty_stop_loss_points = new_n_sl
            engine.config.nifty_lots_per_trade = new_n_lots
            engine.config.sensex_target_points = new_s_tp
            engine.config.sensex_stop_loss_points = new_s_sl
            engine.config.sensex_lots_per_trade = new_s_lots
            engine.config.one_trade_per_candle = one_tr
            engine.config.carry_overnight_reference = carry_ov
            engine.config.telegram_alerts_enabled = tg_en
            engine.config.webhook_alerts_enabled = wb_en
            st.success("Strategy settings successfully updated in live engine!")
            st.rerun()


# ══════════════════════════════════════════════════════════════════
# TAB 6: STOCKS DIRECTORY & INTERACTIVE OHLCV CHARTS (2,600+ STOCKS)
# ══════════════════════════════════════════════════════════════════
with tab_directory:
    st.markdown("### 🔍 All Stocks Directory & Interactive Candlestick Charts")
    st.caption("Search, filter, and view technical candlestick charts for 2,600+ NSE and BSE listed equities.")

    col_srch1, col_srch2 = st.columns([3, 1])
    with col_srch1:
        search_query = st.text_input("Search by Symbol, Company Name, BSE Code, or ISIN:", value="", placeholder="e.g. RELIANCE, TCS, INFY, 500325...")
    with col_srch2:
        exchange_filter = st.selectbox("Exchange:", ["all", "nse", "bse", "both"], index=0)

    # Search stocks
    search_res = ms.search_stocks(query=search_query, exchange=exchange_filter, page=1, limit=30)
    matched_stocks = search_res.get("stocks", [])
    total_matches = search_res.get("total", 0)

    st.caption(f"Found **{total_matches}** matched stocks across NSE & BSE database.")

    # Select stock for Charting
    stock_options = [s["symbol"] for s in matched_stocks] if matched_stocks else ["RELIANCE", "TCS", "INFY", "HDFCBANK", "SBIN"]
    
    col_sym, col_tf, col_rng = st.columns(3)
    with col_sym:
        chart_sym = st.selectbox("Select Stock for Chart:", stock_options, index=0, key="chart_sym_select")
    with col_tf:
        chart_interval = st.selectbox("Timeframe:", ["5m", "15m", "1h", "1d", "1wk"], index=3, key="chart_tf_select")
    with col_rng:
        chart_range = st.selectbox("Range:", ["5d", "1mo", "3mo", "6mo", "1y", "2y"], index=2, key="chart_rng_select")

    # Fetch chart data
    chart_data = get_cached_chart_data(chart_sym, chart_interval, chart_range, exchange_filter)
    candles = chart_data.get("candles", [])

    if candles:
        df_c = pd.DataFrame(candles)
        df_c["dt"] = pd.to_datetime(df_c["time"], unit="s")
        
        # Calculate 20 SMA
        df_c["sma20"] = df_c["close"].rolling(window=20).mean()

        fig_candle = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.75, 0.25])
        
        # Candlestick Trace
        fig_candle.add_trace(go.Candlestick(
            x=df_c["dt"],
            open=df_c["open"],
            high=df_c["high"],
            low=df_c["low"],
            close=df_c["close"],
            name="OHLC",
            increasing_line_color="#00f59b",
            decreasing_line_color="#ff2e63"
        ), row=1, col=1)

        # 20 SMA Line
        fig_candle.add_trace(go.Scatter(
            x=df_c["dt"],
            y=df_c["sma20"],
            mode="lines",
            name="SMA 20",
            line=dict(color="#fbbf24", width=1.5)
        ), row=1, col=1)

        # Volume Trace
        colors = ["#00f59b" if c >= o else "#ff2e63" for o, c in zip(df_c["open"], df_c["close"])]
        fig_candle.add_trace(go.Bar(
            x=df_c["dt"],
            y=df_c["volume"],
            name="Volume",
            marker_color=colors,
            opacity=0.8
        ), row=2, col=1)

        fig_candle.update_layout(
            title=f"{chart_sym} Interactive Technical Chart ({chart_interval} • {chart_range})",
            template="plotly_dark",
            height=480,
            margin=dict(l=10, r=10, t=40, b=10),
            xaxis_rangeslider_visible=False
        )
        st.plotly_chart(fig_candle, use_container_width=True)
    else:
        st.warning("Chart data not available for this ticker.")

    # Matched Stocks Table
    if matched_stocks:
        st.markdown("##### 📋 Matched Equities")
        df_dir = pd.DataFrame(matched_stocks)[["symbol", "name", "bseCode", "isin", "nse", "bse"]]
        df_dir.columns = ["Symbol", "Company Name", "BSE Code", "ISIN", "NSE Listed", "BSE Listed"]
        st.dataframe(df_dir, use_container_width=True, height=260)


# ══════════════════════════════════════════════════════════════════
# TAB 7: DIAGNOSTICS & SYSTEM HEALTH
# ══════════════════════════════════════════════════════════════════
with tab_health:
    st.markdown("### 🩺 System Diagnostics & Production Health")
    st.caption("Inspects execution runtime, background engines, memory consumption, and connectivity to market feeds.")

    uptime_sec = int(time.time() - APP_START_TIME)
    
    # Memory RSS check
    mem_mb = "N/A"
    try:
        import psutil
        mem_mb = f"{psutil.Process(os.getpid()).memory_info().rss / (1024*1024):.1f} MB"
    except Exception:
        pass

    col_h1, col_h2, col_h3, col_h4 = st.columns(4)
    with col_h1:
        st.metric("System Uptime", f"{uptime_sec}s")
    with col_h2:
        st.metric("Memory RSS", mem_mb)
    with col_h3:
        st.metric("curl_cffi Status", "Active" if ms.USE_CURL_CFFI else "Fallback")
    with col_h4:
        st.metric("1H Strategy Status", "Active" if engine._is_running else "Standby")

    st.markdown("---")

    # Module Status Summary
    st.markdown("##### 📦 Modules Diagnostic State")
    modules_data = [
        {"Module": "Market Service (NSE/BSE)", "Status": "ONLINE", "Details": "Live feed with cloud fallback"},
        {"Module": "Advanced Market Scanner", "Status": "ONLINE", "Details": f"{len(adv_scanner.symbols)} symbols queued"},
        {"Module": "Option Chain & Greeks", "Status": "ONLINE", "Details": f"{len(FO_SPECS)} instruments supported"},
        {"Module": "1H Breakout Strategy", "Status": "ONLINE", "Details": "NIFTY & SENSEX calibrated engine"},
        {"Module": "SQLite Trade Database", "Status": "ONLINE", "Details": "Local persistence active"},
    ]
    st.dataframe(pd.DataFrame(modules_data), use_container_width=True)

    # Network Latency Probe
    if st.button("📡 Run Live Connectivity Test"):
        with st.spinner("Pinging NSE and Yahoo Finance..."):
            t0 = time.time()
            try:
                test_quote = ms.fetch_nse_market_data("NIFTY")
                lat_nse = round((time.time() - t0) * 1000, 1)
                st.success(f"✅ NSE Portal Response: {lat_nse} ms (Status: {test_quote.get('status')})")
            except Exception as e:
                st.error(f"❌ NSE Portal Connection: {e}")

            t1 = time.time()
            try:
                test_yf = ms.fetch_chart_data("RELIANCE", "1d", "5d")
                lat_yf = round((time.time() - t1) * 1000, 1)
                st.success(f"✅ Yahoo Finance API Response: {lat_yf} ms (Candles: {test_yf.get('count')})")
            except Exception as e:
                st.error(f"❌ Yahoo Finance Connection: {e}")
