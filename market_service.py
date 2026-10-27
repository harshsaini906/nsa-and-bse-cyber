"""
Market Service module for TradingAI.
Contains high-performance data fetchers for:
- NSE Live Gainers and Losers
- NSE Volume Spurts & Gainers
- All Listed Stocks (NSE & BSE) Directory and Search
- Yahoo Finance Candlestick (OHLCV) Chart Feeds
- 9:45 AM ORB & Previous Day High/Low Dual Breakout Scanner
- Safe Streamlit secrets & environment variable resolver
- Cloud IP blocking fallbacks with user-friendly diagnostics
"""

import os
import json
import time
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List, Optional, Tuple

try:
    from curl_cffi import requests
    USE_CURL_CFFI = True
except ImportError:
    import requests
    USE_CURL_CFFI = False

IST = timezone(timedelta(hours=5, minutes=30))

# ── SECRET / CONFIG RESOLVER ──
def get_secret(key: str, default: Any = None) -> Any:
    """
    Safely retrieves a configuration key or API secret.
    Priority order:
    1. Streamlit secrets (st.secrets) if running in Streamlit
    2. Environment variables (os.environ)
    3. Default value
    """
    try:
        import streamlit as st
        if hasattr(st, "secrets") and key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    val = os.environ.get(key)
    if val is not None:
        return val
    return default


# ── NSE URLS & HEADERS ──
NSE_BASE_URL = "https://www.nseindia.com"
GAINERS_URL = "https://www.nseindia.com/api/live-analysis-variations?index=gainers"
LOSERS_URL = "https://www.nseindia.com/api/live-analysis-variations?index=loosers"
VOLUME_GAINERS_URL = "https://www.nseindia.com/api/live-analysis-volume-gainers"

COMMON_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Sec-Ch-Ua': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"Windows"',
}

API_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.nseindia.com/',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
}

YF_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/json',
}

_session = None

def get_session():
    """Returns an active HTTP session with browser headers and warm-up cookies."""
    global _session
    if _session is None:
        if USE_CURL_CFFI:
            _session = requests.Session(impersonate="chrome124")
        else:
            _session = requests.Session()
        try:
            _session.get(NSE_BASE_URL, headers=COMMON_HEADERS, timeout=8)
        except Exception:
            pass
    return _session

def reset_session():
    """Resets session if cookies expire."""
    global _session
    _session = None
    return get_session()

# In-memory service caches
_market_cache: Dict[str, Any] = {"data": None, "last_fetched": 0, "ttl": 20}
_volume_cache: Dict[str, Any] = {"data": None, "last_fetched": 0, "ttl": 20}
_screener_cache: Dict[str, Any] = {"cache": {}, "ttl": 30}


def clean_stock_data(raw_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalizes raw stock entries from NSE."""
    formatted = []
    for item in raw_items:
        try:
            symbol = item.get('symbol', 'N/A')
            ltp = float(item.get('ltp', 0.0) or 0.0)
            prev_price = float(item.get('prev_price', 0.0) or 0.0)
            if ltp and prev_price:
                change = round(ltp - prev_price, 2)
            else:
                change = float(item.get('net_price', 0.0) or 0.0)
            p_change = float(item.get('perChange', 0.0) or 0.0)
            high = float(item.get('high_price', 0.0) or 0.0)
            low = float(item.get('low_price', 0.0) or 0.0)
            open_price = float(item.get('open_price', 0.0) or 0.0)
            volume = int(item.get('trade_quantity', 0) or 0)
            turnover = float(item.get('turnover', 0.0) or 0.0)

            formatted.append({
                "symbol": symbol,
                "ltp": ltp,
                "prev_price": prev_price,
                "change": change,
                "pChange": p_change,
                "high": high,
                "low": low,
                "open": open_price,
                "volume": volume,
                "turnover": turnover
            })
        except Exception:
            continue
    return formatted


def _generate_fallback_gainers_losers(index: str = "NIFTY") -> Dict[str, Any]:
    """Generates realistic market fallback data if NSE blocks Cloud datacenter IP."""
    sample_stocks = [
        ("RELIANCE", 2985.40, 48.20, 1.64, 3010.0, 2942.0, 2950.0, 8540000, 2548.5),
        ("TCS", 4120.50, 52.80, 1.30, 4150.0, 4075.0, 4080.0, 2140000, 881.7),
        ("BHARTIARTL", 1345.20, 24.10, 1.82, 1358.0, 1320.0, 1325.0, 6420000, 863.6),
        ("ICICIBANK", 1125.80, 12.40, 1.11, 1134.0, 1112.0, 1115.0, 12840000, 1445.5),
        ("INFY", 1585.30, 15.20, 0.97, 1598.0, 1565.0, 1572.0, 7120000, 1128.7),
        ("SBIN", 824.60, -4.20, -0.51, 835.0, 818.0, 830.0, 14500000, 1195.6),
        ("HDFCBANK", 1520.10, -11.50, -0.75, 1540.0, 1515.0, 1535.0, 16200000, 2462.5),
        ("TATAMOTORS", 975.40, -12.80, -1.30, 995.0, 968.0, 990.0, 9840000, 959.8),
        ("BAJFINANCE", 6850.00, -95.00, -1.37, 6980.0, 6810.0, 6960.0, 1450000, 993.2),
        ("MARUTI", 12450.00, -185.00, -1.46, 12680.0, 12390.0, 12650.0, 680000, 846.6),
    ]

    gainers = []
    losers = []
    for s, ltp, chg, pchg, h, l, o, v, to in sample_stocks:
        rec = {
            "symbol": s,
            "ltp": ltp,
            "prev_price": round(ltp - chg, 2),
            "change": chg,
            "pChange": pchg,
            "high": h,
            "low": l,
            "open": o,
            "volume": v,
            "turnover": to
        }
        if pchg >= 0:
            gainers.append(rec)
        else:
            losers.append(rec)

    gainers.sort(key=lambda x: x["pChange"], reverse=True)
    losers.sort(key=lambda x: x["pChange"])

    return {
        "gainers": gainers,
        "losers": losers,
        "last_updated": datetime.now(IST).strftime("%d-%b-%Y %I:%M:%S %p"),
        "status": "Fallback (Cloud IP Restriction)",
        "is_fallback": True,
        "index": index
    }


def fetch_nse_market_data(index: str = "NIFTY") -> Dict[str, Any]:
    """
    Fetches real-time Top Gainers & Losers from NSE India.
    Includes caching and robust fallback if cloud IP is rate-limited.
    """
    global _market_cache
    now = time.time()
    if _market_cache["data"] and (now - _market_cache["last_fetched"] < _market_cache["ttl"]):
        return _market_cache["data"]

    session = get_session()
    gainers_list = []
    losers_list = []
    timestamp_str = datetime.now(IST).strftime("%d-%b-%Y %I:%M:%S %p")

    try:
        r_g = session.get(GAINERS_URL, headers=API_HEADERS, timeout=7)
        if r_g.status_code in (401, 403):
            session = reset_session()
            r_g = session.get(GAINERS_URL, headers=API_HEADERS, timeout=7)

        r_l = session.get(LOSERS_URL, headers=API_HEADERS, timeout=7)
        if r_l.status_code in (401, 403):
            session = reset_session()
            r_l = session.get(LOSERS_URL, headers=API_HEADERS, timeout=7)

        if r_g.status_code == 200:
            raw_g = r_g.json().get(index, {}).get('data', [])
            gainers_list = clean_stock_data(raw_g)
            gainers_list.sort(key=lambda x: x['pChange'], reverse=True)

        if r_l.status_code == 200:
            raw_l = r_l.json().get(index, {}).get('data', [])
            losers_list = clean_stock_data(raw_l)
            losers_list.sort(key=lambda x: x['pChange'])

        if gainers_list or losers_list:
            res = {
                "gainers": gainers_list,
                "losers": losers_list,
                "last_updated": timestamp_str,
                "status": "Live",
                "is_fallback": False,
                "index": index
            }
            _market_cache["data"] = res
            _market_cache["last_fetched"] = now
            return res
    except Exception as e:
        print(f"[MarketService] NSE Live fetch note: {e}")

    # Fallback to previous cache if available
    if _market_cache["data"]:
        cached = dict(_market_cache["data"])
        cached["status"] = "Cached Feed"
        return cached

    # Safe synthetic fallback for cloud deployment
    fallback = _generate_fallback_gainers_losers(index=index)
    _market_cache["data"] = fallback
    _market_cache["last_fetched"] = now
    return fallback


def fetch_volume_gainers() -> Dict[str, Any]:
    """Fetches Top Volume Spurts from NSE with graceful fallback."""
    global _volume_cache
    now = time.time()
    if _volume_cache["data"] and (now - _volume_cache["last_fetched"] < _volume_cache["ttl"]):
        return _volume_cache["data"]

    session = get_session()
    timestamp_str = datetime.now(IST).strftime("%d-%b-%Y %I:%M:%S %p")
    vol_headers = dict(API_HEADERS)
    vol_headers['Referer'] = 'https://www.nseindia.com/market-data/volume-gainers-spurts'

    try:
        r = session.get(VOLUME_GAINERS_URL, headers=vol_headers, timeout=7)
        if r.status_code in (401, 403):
            session = reset_session()
            r = session.get(VOLUME_GAINERS_URL, headers=vol_headers, timeout=7)

        if r.status_code == 200:
            raw = r.json()
            items = raw.get('data', [])
            cleaned = []
            for item in items:
                try:
                    ltp = float(item.get('ltp', 0.0) or 0.0)
                    p_change = float(item.get('pChange', 0.0) or 0.0)
                    if p_change != -100.0 and ltp > 0:
                        prev_close = ltp / (1.0 + (p_change / 100.0))
                        change = round(ltp - prev_close, 2)
                    else:
                        change = 0.0

                    cleaned.append({
                        "symbol": item.get('symbol', 'N/A'),
                        "companyName": item.get('companyName', ''),
                        "ltp": ltp,
                        "change": change,
                        "pChange": p_change,
                        "volume": int(item.get('volume', 0) or 0),
                        "week1AvgVol": int(item.get('week1AvgVolume', 0) or 0),
                        "week2AvgVol": int(item.get('week2AvgVolume', 0) or 0),
                        "week1VolChg": round(float(item.get('week1volChange', 0.0) or 0.0), 2),
                        "week2VolChg": round(float(item.get('week2volChange', 0.0) or 0.0), 2),
                        "turnover": float(item.get('turnover', 0.0) or 0.0),
                    })
                except Exception:
                    continue

            if cleaned:
                res = {
                    "volumeGainers": cleaned,
                    "last_updated": raw.get('timestamp', timestamp_str),
                    "status": "Live",
                    "is_fallback": False,
                    "count": len(cleaned)
                }
                _volume_cache["data"] = res
                _volume_cache["last_fetched"] = now
                return res
    except Exception as e:
        print(f"[MarketService] Volume gainers fetch note: {e}")

    # Fallback to high-volume stocks from market data
    mkt = fetch_nse_market_data()
    all_stocks = mkt.get("gainers", []) + mkt.get("losers", [])
    all_stocks_sorted = sorted(all_stocks, key=lambda x: x.get("volume", 0), reverse=True)
    fallback_cleaned = []
    for s in all_stocks_sorted[:20]:
        vol = s.get("volume", 0)
        avg_est = max(1, int(vol * 0.45))
        spurt = round(vol / avg_est, 1)
        fallback_cleaned.append({
            "symbol": s.get("symbol"),
            "companyName": s.get("symbol"),
            "ltp": s.get("ltp", 0.0),
            "change": s.get("change", 0.0),
            "pChange": s.get("pChange", 0.0),
            "volume": vol,
            "week1AvgVol": avg_est,
            "week2AvgVol": avg_est,
            "week1VolChg": spurt,
            "week2VolChg": spurt,
            "turnover": s.get("turnover", 0.0)
        })

    res = {
        "volumeGainers": fallback_cleaned,
        "last_updated": timestamp_str,
        "status": "Market Volume Derived",
        "is_fallback": True,
        "count": len(fallback_cleaned)
    }
    _volume_cache["data"] = res
    _volume_cache["last_fetched"] = now
    return res


# ── ALL STOCKS (NSE & BSE) DATABASE ──
_STOCKS_DB_FILE = os.path.join(os.path.dirname(__file__), "data", "all_stocks.json")
_stocks_db_cache: Dict[str, Any] = {"total": 0, "totalNse": 0, "totalBse": 0, "dualListed": 0, "stocks": []}

def get_stocks_db() -> Dict[str, Any]:
    """Loads and caches all_stocks.json."""
    global _stocks_db_cache
    if not _stocks_db_cache["stocks"] and os.path.exists(_STOCKS_DB_FILE):
        try:
            with open(_STOCKS_DB_FILE, "r", encoding="utf-8") as f:
                _stocks_db_cache = json.load(f)
        except Exception as e:
            print(f"[MarketService] Error loading {_STOCKS_DB_FILE}: {e}")
    return _stocks_db_cache

def search_stocks(query: str = "", exchange: str = "all", page: int = 1, limit: int = 50) -> Dict[str, Any]:
    """Searches, filters, and paginates through the 2,600+ stock database."""
    db = get_stocks_db()
    stocks = db.get("stocks", [])
    q = (query or "").strip().upper()
    ex = (exchange or "all").lower()

    filtered = stocks
    if ex == 'nse':
        filtered = [s for s in filtered if s.get('nse')]
    elif ex == 'bse':
        filtered = [s for s in filtered if s.get('bse')]
    elif ex == 'both':
        filtered = [s for s in filtered if s.get('nse') and s.get('bse')]

    if q:
        filtered = [
            s for s in filtered
            if q in s.get('symbol', '').upper()
            or q in s.get('name', '').upper()
            or q in str(s.get('bseCode', ''))
            or q in s.get('isin', '').upper()
        ]

    total_count = len(filtered)
    start = (page - 1) * limit
    end = start + limit
    paginated = filtered[start:end]

    return {
        'total': total_count,
        'page': page,
        'limit': limit,
        'totalPages': max(1, (total_count + limit - 1) // limit),
        'stats': {
            'totalNse': db.get('totalNse', 0),
            'totalBse': db.get('totalBse', 0),
            'dualListed': db.get('dualListed', 0),
            'totalCombined': db.get('total', 0)
        },
        'stocks': paginated
    }


def fetch_chart_data(symbol: str, interval: str = "1d", range_val: str = "3mo", exchange_req: str = "") -> Dict[str, Any]:
    """
    Fetches OHLCV candlestick data for an NSE or BSE stock using Yahoo Finance.
    Implements cross-exchange fallback (.NS vs .BO) and synthetic generation if blocked.
    """
    sym = symbol.upper().strip()
    valid_intervals = {'1m','2m','5m','15m','30m','60m','90m','1h','1d','5d','1wk','1mo','3mo'}
    valid_ranges    = {'1d','5d','1mo','3mo','6mo','1y','2y','5y','10y','ytd','max'}
    if interval not in valid_intervals:
        interval = '1d'
    if range_val not in valid_ranges:
        range_val = '3mo'

    clean_sym = sym.replace('.BO', '').replace('.NS', '')
    if exchange_req.upper() == 'BSE' or sym.endswith('.BO'):
        primary_sym = f"{clean_sym}.BO"
        fallback_sym = f"{clean_sym}.NS"
        default_exch = 'BSE'
    else:
        primary_sym = f"{clean_sym}.NS"
        fallback_sym = f"{clean_sym}.BO"
        default_exch = 'NSE'

    session = get_session()

    def fetch_yf(s):
        try:
            r = session.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{s}",
                headers=YF_HEADERS,
                params={'interval': interval, 'range': range_val},
                timeout=8
            )
            if r.status_code == 200:
                data = r.json()
                res = data.get('chart', {}).get('result')
                if res:
                    return res[0], None
            return None, f"Status {r.status_code}"
        except Exception as e:
            return None, str(e)

    result, err = fetch_yf(primary_sym)
    resolved_sym = primary_sym
    exch_name = default_exch

    if not result or len(result.get('timestamp', [])) <= 2:
        fallback_res, _ = fetch_yf(fallback_sym)
        if fallback_res and len(fallback_res.get('timestamp', [])) > (len(result.get('timestamp', [])) if result else 0):
            result = fallback_res
            resolved_sym = fallback_sym
            exch_name = 'NSE' if fallback_sym.endswith('.NS') else 'BSE'

    if not result:
        # Generate graceful synthetic candles if Cloud IP is blocked
        now_ts = int(time.time())
        candles = []
        base_price = 1000.0
        # Check if known symbol in default dict
        known_prices = {'RELIANCE': 2980.0, 'TCS': 4120.0, 'INFY': 1580.0, 'HDFCBANK': 1520.0, 'SBIN': 825.0, 'NIFTY': 22750.0, 'SENSEX': 73600.0}
        base_price = known_prices.get(clean_sym, 500.0)
        step_seconds = 86400 if interval == '1d' else 3600
        for i in range(30, 0, -1):
            t_bar = now_ts - (i * step_seconds)
            delta = (i % 7 - 3) * (base_price * 0.005)
            c_open = base_price + delta
            c_high = c_open + (base_price * 0.008)
            c_low = c_open - (base_price * 0.008)
            c_close = c_open + (base_price * 0.003)
            candles.append({
                'time': t_bar,
                'open': round(c_open, 2),
                'high': round(c_high, 2),
                'low': round(c_low, 2),
                'close': round(c_close, 2),
                'volume': int(100000 + (i * 5000)),
            })

        return {
            'symbol': clean_sym,
            'yfSymbol': resolved_sym,
            'exchange': exch_name,
            'currency': 'INR',
            'interval': interval,
            'range': range_val,
            'ltp': candles[-1]['close'],
            'prevClose': candles[-2]['close'] if len(candles) > 1 else candles[-1]['close'],
            'candles': candles,
            'count': len(candles),
            'is_fallback': True,
            'notice': 'Synthetic chart generated (Yahoo Finance cloud IP block)'
        }

    try:
        ts = result.get('timestamp', [])
        meta = result.get('meta', {})
        quote = result.get('indicators', {}).get('quote', [{}])[0]
        opens = quote.get('open', [])
        highs = quote.get('high', [])
        lows = quote.get('low', [])
        closes = quote.get('close', [])
        volumes = quote.get('volume', [])

        candles = []
        for i, t in enumerate(ts):
            try:
                o, h, l, c, v = opens[i], highs[i], lows[i], closes[i], volumes[i]
                if None in (o, h, l, c):
                    continue
                candles.append({
                    'time': t,
                    'open': round(float(o), 2),
                    'high': round(float(h), 2),
                    'low': round(float(l), 2),
                    'close': round(float(c), 2),
                    'volume': int(v) if v else 0,
                })
            except Exception:
                continue

        return {
            'symbol': clean_sym,
            'yfSymbol': resolved_sym,
            'exchange': exch_name,
            'currency': meta.get('currency', 'INR'),
            'interval': interval,
            'range': range_val,
            'ltp': round(float(meta.get('regularMarketPrice', candles[-1]['close'] if candles else 0)), 2),
            'prevClose': round(float(meta.get('previousClose', 0) or 0), 2),
            'candles': candles,
            'count': len(candles),
            'is_fallback': False
        }
    except Exception as e:
        return {'error': str(e), 'candles': [], 'is_fallback': True}


# ── 9:45 AM ORB & PREV DAY HIGH DUAL BREAKOUT SCREENER ──
def scan_orb_945(index: str = "NIFTY") -> Dict[str, Any]:
    """
    Evaluates dual-side 5-minute breakout criteria (09:15 - 09:45 AM IST window).
    """
    global _screener_cache
    idx = index.upper().strip()
    cache_key = f"dual_{idx}"
    now = time.time()
    cached = _screener_cache["cache"].get(cache_key)
    if cached and (now - cached["timestamp"] < _screener_cache["ttl"]):
        return cached["data"]

    if idx == 'BANKNIFTY':
        symbols = ['HDFCBANK', 'ICICIBANK', 'SBIN', 'AXISBANK', 'KOTAKBANK', 'INDUSINDBK', 'BANKBARODA', 'PNB', 'AUBANK', 'FEDERALBNK', 'IDFCFIRSTB', 'BANDHANBNK']
    elif idx == 'NIFTYNEXT50':
        symbols = ['BEL', 'HAL', 'ZOMATO', 'JIOFIN', 'TRENT', 'VEDL', 'IRFC', 'PFC', 'RECLTD', 'CHOLAFIN', 'BANKBARODA', 'SIEMENS', 'DLF', 'IOC', 'GAIL', 'ABB', 'HINDALCO', 'AMBUJACEM']
    else:
        # Default top liquid universe
        symbols = [
            'RELIANCE', 'TCS', 'HDFCBANK', 'ICICIBANK', 'INFY', 'BHARTIARTL', 'ITC', 'SBIN', 'LICI', 'HINDUNILVR',
            'LT', 'BAJFINANCE', 'HCLTECH', 'MARUTI', 'SUNPHARMA', 'ADANIENT', 'TATAMOTORS', 'KOTAKBANK', 'NTPC',
            'TITAN', 'ONGC', 'AXISBANK', 'ADANIPORTS', 'POWERGRID', 'COALINDIA', 'TATASTEEL', 'BAJAJFINSV', 'M&M',
            'ASIANPAINT', 'JSWSTEEL', 'ULTRACEMCO', 'NESTLEIND', 'GRASIM', 'TECHM', 'WIPRO', 'HDFCLIFE', 'DIVISLAB',
            'CIPLA', 'SBILIFE', 'DRREDDY', 'EICHERMOT', 'BRITANNIA', 'TATACONSUM', 'APOLLOHOSP', 'HEROMOTOCO',
            'HINDALCO', 'SHRIRAMFIN', 'BPCL', 'INDUSINDBK', 'TRENT'
        ]

    session = get_session()

    def scan_one(sym):
        try:
            r = session.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}.NS", headers=YF_HEADERS, params={'interval': '5m', 'range': '5d'}, timeout=7)
            if r.status_code != 200:
                r = session.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}.BO", headers=YF_HEADERS, params={'interval': '5m', 'range': '5d'}, timeout=7)
                if r.status_code != 200:
                    return None

            data = r.json()
            res = data.get('chart', {}).get('result', [{}])[0]
            ts = res.get('timestamp', [])
            meta = res.get('meta', {})
            quote = res.get('indicators', {}).get('quote', [{}])[0]
            opens = quote.get('open', [])
            highs = quote.get('high', [])
            lows = quote.get('low', [])
            closes = quote.get('close', [])
            vols = quote.get('volume', [])

            by_date = {}
            for i, t in enumerate(ts):
                try:
                    o, h, l, c, v = opens[i], highs[i], lows[i], closes[i], vols[i]
                    if None in (o, h, l, c): continue
                    dt = datetime.fromtimestamp(t, tz=timezone.utc).astimezone(IST)
                    d_key = dt.strftime('%Y-%m-%d')
                    if d_key not in by_date: by_date[d_key] = []
                    by_date[d_key].append({'time': t, 'dt': dt, 'open': float(o), 'high': float(h), 'low': float(l), 'close': float(c), 'volume': int(v or 0)})
                except Exception:
                    continue

            dates = sorted(by_date.keys())
            if len(dates) < 2: return None

            today_date = dates[-1]
            prev_date = dates[-2]
            prev_candles = by_date[prev_date]
            today_candles = by_date[today_date]

            prev_day_high = round(max(c['high'] for c in prev_candles), 2)
            prev_day_low = round(min(c['low'] for c in prev_candles), 2)
            prev_day_close = prev_candles[-1]['close']

            window = [c for c in today_candles if c['dt'].hour == 9 and c['dt'].minute <= 45]
            if not window: return None

            c1 = window[0]
            c1_high = round(c1['high'], 2)
            c1_low  = round(c1['low'], 2)

            ltp = round(float(meta.get('regularMarketPrice', today_candles[-1]['close'])), 2)
            prevClose = round(float(meta.get('previousClose', prev_day_close)), 2)
            chg = round(ltp - prevClose, 2)
            pChg = round((chg / prevClose) * 100, 2) if prevClose else 0.0

            today_vol = sum(c['volume'] for c in today_candles) or int(meta.get('regularMarketVolume', 0))
            past_vols = [sum(c['volume'] for c in by_date[d]) for d in dates[:-1] if sum(c['volume'] for c in by_date[d]) > 0]
            avg_vol = (sum(past_vols) / len(past_vols)) if past_vols else today_vol
            vol_vs_avg = round(today_vol / avg_vol, 2) if avg_vol > 0 else 1.0

            # 1. Bullish Check
            bull_c1_low_held = all(c['low'] >= c1_low for c in window)
            bull_c1_high_bo  = any(c['high'] > c1_high for c in window[1:]) if len(window) > 1 else False
            bull_pdh_bo      = any(c['high'] > prev_day_high for c in window)
            bull_pdl_held    = all(c['low'] >= prev_day_low for c in window)
            bull_score       = (1 if bull_c1_low_held else 0) + (1 if bull_c1_high_bo else 0) + (1 if bull_pdh_bo else 0) + (1 if bull_pdl_held else 0)

            # 2. Bearish Check
            bear_c1_high_held = all(c['high'] <= c1_high for c in window)
            bear_c1_low_bd    = any(c['low'] < c1_low for c in window[1:]) if len(window) > 1 else False
            bear_pdl_bd       = any(c['low'] < prev_day_low for c in window)
            bear_pdh_held     = all(c['high'] <= prev_day_high for c in window)
            bear_score       = (1 if bear_c1_high_held else 0) + (1 if bear_c1_low_bd else 0) + (1 if bear_pdl_bd else 0) + (1 if bear_pdh_held else 0)

            base = {
                'symbol': sym,
                'ltp': ltp,
                'prevClose': prevClose,
                'change': chg,
                'pChange': pChg,
                'volume': today_vol,
                'vol_vs_avg': vol_vs_avg,
                'c1_high': c1_high,
                'c1_low': c1_low,
                'pdh': prev_day_high,
                'pdl': prev_day_low,
            }

            bull = {
                **base,
                'c1_low_held': bull_c1_low_held,
                'c1_high_bo': bull_c1_high_bo,
                'pdh_bo': bull_pdh_bo,
                'pdl_held': bull_pdl_held,
                'score': bull_score,
                'is_full_match': (bull_score == 4),
                'status': 'SELECTED' if bull_score == 4 else 'REJECTED'
            }

            bear = {
                **base,
                'c1_high_held': bear_c1_high_held,
                'c1_low_bd': bear_c1_low_bd,
                'pdl_bd': bear_pdl_bd,
                'pdh_held': bear_pdh_held,
                'score': bear_score,
                'is_full_match': (bear_score == 4),
                'status': 'SELECTED' if bear_score == 4 else 'REJECTED'
            }

            return bull, bear
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=10) as executor:
        pairs = [p for p in executor.map(scan_one, symbols) if p]

    bull_list = [p[0] for p in pairs]
    bear_list = [p[1] for p in pairs]

    bull_list.sort(key=lambda x: (x['is_full_match'], x['score'], x['pChange']), reverse=True)
    bear_list.sort(key=lambda x: (x['is_full_match'], x['score'], -x['pChange']), reverse=True)

    summary = {
        'total_scanned': len(pairs),
        'bullish_selected_count': sum(1 for b in bull_list if b['is_full_match']),
        'bearish_selected_count': sum(1 for b in bear_list if b['is_full_match']),
        'bullish_score_3_count': sum(1 for b in bull_list if b['score'] == 3),
        'bearish_score_3_count': sum(1 for b in bear_list if b['score'] == 3),
        'index': idx,
        'last_scanned': datetime.now(IST).strftime('%H:%M:%S IST'),
        'bullish_results': bull_list,
        'bearish_results': bear_list
    }

    _screener_cache["cache"][cache_key] = {
        "timestamp": now,
        "data": summary
    }
    return summary
