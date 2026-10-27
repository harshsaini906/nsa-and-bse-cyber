import os
import re
import csv
import io
import json
import time
import math
import threading
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
try:
    from curl_cffi import requests
except ImportError:
    import requests

IST = timezone(timedelta(hours=5, minutes=30))

YF_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/json',
}

TOP_50_NIFTY = [
    'RELIANCE', 'TCS', 'HDFCBANK', 'ICICIBANK', 'INFY', 'BHARTIARTL', 'ITC', 'SBIN', 'LICI', 'HINDUNILVR',
    'LT', 'BAJFINANCE', 'HCLTECH', 'MARUTI', 'SUNPHARMA', 'ADANIENT', 'TATAMOTORS', 'KOTAKBANK', 'NTPC',
    'TITAN', 'ONGC', 'AXISBANK', 'ADANIPORTS', 'POWERGRID', 'COALINDIA', 'TATASTEEL', 'BAJAJFINSV', 'M&M',
    'ASIANPAINT', 'JSWSTEEL', 'ULTRACEMCO', 'NESTLEIND', 'GRASIM', 'TECHM', 'WIPRO', 'HDFCLIFE', 'DIVISLAB',
    'CIPLA', 'SBILIFE', 'DRREDDY', 'EICHERMOT', 'BRITANNIA', 'TATACONSUM', 'APOLLOHOSP', 'HEROMOTOCO',
    'HINDALCO', 'SHRIRAMFIN', 'BPCL', 'INDUSINDBK', 'TRENT'
]

def compute_ema(values, period):
    if len(values) < period:
        return [None] * len(values)
    ema = [None] * len(values)
    sma = sum(values[:period]) / period
    ema[period - 1] = sma
    mult = 2 / (period + 1)
    for i in range(period, len(values)):
        ema[i] = (values[i] * mult) + (ema[i - 1] * (1 - mult))
    return ema

class AdvancedMarketScanner:
    def __init__(self, stocks_file='data/all_stocks.json'):
        self.stocks_file = stocks_file
        self.symbols = []
        self.load_symbols()

        # State
        self.is_running = False
        self.is_paused = False
        self.current_index = 0
        self.scanned_count = 0
        self.failed_count = 0
        self.latency_ms = 0
        self.last_completed_scan = None
        self.last_update_time = None

        # Data stores
        self.market_trend = {}
        self.bullish_results = []
        self.bearish_results = []
        self.trend_leaders = {
            'top_bullish': [],
            'top_bearish': [],
            'top_rel_volume': [],
            'sideways_mixed': []
        }
        self.all_evaluated = {}  # sym -> (bull_r, bear_r)
        self._lock = threading.Lock()
        self._worker_thread = None

        # 1. Immediate Market Trend Detection
        self.update_market_trend()

        # 2. Pre-warm top liquid universe in background on startup
        threading.Thread(target=self._prewarm_top_liquid, daemon=True).start()

    def load_symbols(self):
        try:
            raw_syms = []
            if os.path.exists(self.stocks_file):
                with open(self.stocks_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    stocks = data.get('stocks', [])
                    raw_syms = [s['symbol'].strip().upper() for s in stocks if s.get('nse')]
            
            # Ensure top liquid stocks are prioritized at the front
            seen = set()
            ordered = []
            for s in TOP_50_NIFTY:
                if s not in seen:
                    seen.add(s)
                    ordered.append(s)
            for s in raw_syms:
                if s not in seen:
                    seen.add(s)
                    ordered.append(s)

            self.symbols = ordered if ordered else TOP_50_NIFTY
        except Exception as e:
            print("Error loading symbols:", e)
            self.symbols = TOP_50_NIFTY

    def import_symbols_from_text_or_csv(self, content_str):
        """
        Parses symbols from raw string (CSV, comma-separated, space or newline-separated).
        Validates symbols and removes duplicates.
        """
        with self._lock:
            extracted = []
            reader = csv.reader(io.StringIO(content_str))
            for row in reader:
                for cell in row:
                    tokens = re.split(r'[\s,\t\r\n]+', cell)
                    for t in tokens:
                        sym = t.strip().upper().replace('.NS', '').replace('.BO', '')
                        # Valid NSE symbol regex (alphanumeric, may contain & or -)
                        if sym and re.match(r'^[A-Z0-9&-]{2,15}$', sym) and sym not in ('SYMBOL', 'SERIES', 'NAME', 'ISIN'):
                            extracted.append(sym)
            
            seen = set()
            deduped = [x for x in extracted if not (x in seen or seen.add(x))]
            if deduped:
                self.symbols = deduped
                self.reset()
                return len(deduped)
            return 0

    def _prewarm_top_liquid(self):
        """Pre-warms initial top liquid universe so user sees instant results."""
        try:
            print("Pre-warming top liquid stocks for advanced scanner...")
            top_sample = self.symbols[:35]
            with ThreadPoolExecutor(max_workers=10) as ex:
                results = list(ex.map(self.analyze_stock, top_sample))

            with self._lock:
                for idx, res in enumerate(results):
                    sym = top_sample[idx]
                    if res:
                        bull_r, bear_r = res
                        self.all_evaluated[sym] = (bull_r, bear_r)
                        self.scanned_count += 1
                        if bull_r['is_full_match']:
                            self.bullish_results.append(bull_r)
                        if bear_r['is_full_match']:
                            self.bearish_results.append(bear_r)
                    else:
                        self.failed_count += 1

                self.current_index = len(top_sample)
                self.last_update_time = datetime.now(IST).strftime('%H:%M:%S IST')
                self._recalculate_leaders_and_sort()
            print(f"Pre-warm complete: {self.scanned_count} stocks loaded. Bullish: {len(self.bullish_results)}, Bearish: {len(self.bearish_results)}")
        except Exception as e:
            print("Pre-warm error:", e)

    def update_market_trend(self):
        """
        Determines overall market regime using NIFTY 50 (^NSEI) and NIFTY BANK (^NSEBANK).
        Calculates 5m/15m EMA 20 & 50, VWAP, Opening Range (9:15-9:30 AM), PDH/PDL,
        Price structure (HH/HL vs LH/LL), and Relative Volume.
        """
        s = requests.Session(impersonate="chrome124")
        indices_data = {}

        for sym, name in [('^NSEI', 'NIFTY 50'), ('^NSEBANK', 'NIFTY BANK')]:
            try:
                t0 = time.time()
                r = s.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=5m&range=5d", headers=YF_HEADERS, timeout=8)
                self.latency_ms = round((time.time() - t0) * 1000)
                if r.status_code != 200: continue
                data = r.json()
                res = data['chart']['result'][0]
                ts = res.get('timestamp', [])
                quote = res.get('indicators', {}).get('quote', [{}])[0]
                opens, highs, lows, closes, vols = quote.get('open', []), quote.get('high', []), quote.get('low', []), quote.get('close', []), quote.get('volume', [])

                candles_5m = []
                for i, t in enumerate(ts):
                    if None in (opens[i], highs[i], lows[i], closes[i]): continue
                    dt = datetime.fromtimestamp(t, tz=timezone.utc).astimezone(IST)
                    candles_5m.append({
                        'time': t, 'dt': dt, 'open': float(opens[i]), 'high': float(highs[i]), 'low': float(lows[i]), 'close': float(closes[i]), 'volume': int(vols[i] or 0)
                    })

                if len(candles_5m) < 20: continue

                by_date = {}
                for c in candles_5m:
                    d = c['dt'].strftime('%Y-%m-%d')
                    if d not in by_date: by_date[d] = []
                    by_date[d].append(c)

                dates = sorted(by_date.keys())
                if len(dates) < 2: continue
                today_candles = by_date[dates[-1]]
                prev_candles = by_date[dates[-2]]

                # Intraday VWAP
                cum_pv = sum(((c['high'] + c['low'] + c['close']) / 3) * (c['volume'] or 1) for c in today_candles)
                cum_v = sum((c['volume'] or 1) for c in today_candles)
                vwap = round(cum_pv / cum_v, 2) if cum_v else today_candles[-1]['close']

                # 5m EMAs
                closes_5m = [c['close'] for c in candles_5m]
                ema20_5m = compute_ema(closes_5m, 20)[-1]
                ema50_5m = compute_ema(closes_5m, 50)[-1]

                # 15m Synthesis & EMAs
                candles_15m = []
                for idx in range(0, len(candles_5m), 3):
                    chk = candles_5m[idx:idx+3]
                    if chk:
                        candles_15m.append({
                            'dt': chk[0]['dt'],
                            'open': chk[0]['open'],
                            'high': max(c['high'] for c in chk),
                            'low': min(c['low'] for c in chk),
                            'close': chk[-1]['close'],
                            'volume': sum(c['volume'] for c in chk)
                        })
                closes_15m = [c['close'] for c in candles_15m]
                ema20_15m = compute_ema(closes_15m, 20)[-1] if len(closes_15m) >= 20 else ema20_5m
                ema50_15m = compute_ema(closes_15m, 50)[-1] if len(closes_15m) >= 50 else ema50_5m

                # Opening range 9:15-9:30 AM (first 3 candles)
                or_candles = [c for c in today_candles if c['dt'].hour == 9 and c['dt'].minute <= 25]
                or_high = round(max(c['high'] for c in or_candles), 2) if or_candles else None
                or_low  = round(min(c['low'] for c in or_candles), 2) if or_candles else None

                pdh = round(max(c['high'] for c in prev_candles), 2)
                pdl = round(min(c['low'] for c in prev_candles), 2)
                prev_close = round(prev_candles[-1]['close'], 2)
                ltp = round(today_candles[-1]['close'], 2)
                chg = round(ltp - prev_close, 2)
                pChg = round((chg / prev_close) * 100, 2)

                # Structure evaluation (HH/HL vs LH/LL)
                recent_highs = [c['high'] for c in today_candles[-6:]]
                recent_lows  = [c['low'] for c in today_candles[-6:]]
                is_hh_hl = (len(recent_highs) >= 4 and recent_highs[-1] > recent_highs[0] and recent_lows[-1] > recent_lows[0])
                is_lh_ll = (len(recent_highs) >= 4 and recent_highs[-1] < recent_highs[0] and recent_lows[-1] < recent_lows[0])
                structure = "HIGHER HIGHS / HIGHER LOWS (HH/HL)" if is_hh_hl else ("LOWER HIGHS / LOWER LOWS (LH/LL)" if is_lh_ll else "RANGEBOUND / CONSOLIDATION")

                # Scoring directional bias
                bias_score = 0
                reasons = []

                if ltp > vwap:
                    bias_score += 2
                    reasons.append("Price > VWAP")
                else:
                    bias_score -= 2
                    reasons.append("Price < VWAP")

                if ema20_5m and ema50_5m:
                    if ema20_5m > ema50_5m and ltp > ema20_5m:
                        bias_score += 2
                        reasons.append("5m EMA20 > EMA50 Bullish Stack")
                    elif ema20_5m < ema50_5m and ltp < ema20_5m:
                        bias_score -= 2
                        reasons.append("5m EMA20 < EMA50 Bearish Stack")

                if ema20_15m and ema50_15m:
                    if ema20_15m > ema50_15m:
                        bias_score += 1.5
                        reasons.append("15m EMA20 > EMA50 Supportive")
                    else:
                        bias_score -= 1.5
                        reasons.append("15m EMA20 < EMA50 Resistance")

                if or_high and ltp > or_high:
                    bias_score += 1.5
                    reasons.append("Above 9:15-9:30 Opening Range High")
                elif or_low and ltp < or_low:
                    bias_score -= 1.5
                    reasons.append("Below 9:15-9:30 Opening Range Low")

                if ltp > pdh:
                    bias_score += 2
                    reasons.append("Trading Above Prev Day High")
                elif ltp < pdl:
                    bias_score -= 2
                    reasons.append("Trading Below Prev Day Low")

                if is_hh_hl: bias_score += 1
                elif is_lh_ll: bias_score -= 1

                # Trend designation
                if bias_score >= 6: trend = "STRONG BULLISH"
                elif bias_score >= 2: trend = "BULLISH"
                elif bias_score <= -6: trend = "STRONG BEARISH"
                elif bias_score <= -2: trend = "BEARISH"
                else: trend = "SIDEWAYS"

                indices_data[name] = {
                    'symbol': sym,
                    'name': name,
                    'ltp': ltp,
                    'change': chg,
                    'pChange': pChg,
                    'vwap': vwap,
                    'pdh': pdh,
                    'pdl': pdl,
                    'or_high': or_high,
                    'or_low': or_low,
                    'ema20_5m': round(ema20_5m, 2) if ema20_5m else None,
                    'ema50_5m': round(ema50_5m, 2) if ema50_5m else None,
                    'ema20_15m': round(ema20_15m, 2) if ema20_15m else None,
                    'ema50_15m': round(ema50_15m, 2) if ema50_15m else None,
                    'structure': structure,
                    'trend': trend,
                    'bias_score': bias_score,
                    'reasons': reasons
                }
            except Exception as e:
                print(f"Error updating market trend for {sym}:", e)

        # Composite market regime
        nifty = indices_data.get('NIFTY 50')
        bank = indices_data.get('NIFTY BANK')

        if nifty and bank:
            total_bias = nifty['bias_score'] + bank['bias_score']
            if total_bias >= 10: regime = "STRONG BULLISH"
            elif total_bias >= 4: regime = "BULLISH"
            elif total_bias <= -10: regime = "STRONG BEARISH"
            elif total_bias <= -4: regime = "BEARISH"
            else: regime = "SIDEWAYS"
        elif nifty:
            regime = nifty['trend']
        else:
            regime = "MIXED / INSUFFICIENT DATA"

        self.market_trend = {
            'regime': regime,
            'last_update': datetime.now(IST).strftime('%H:%M:%S IST'),
            'indices': indices_data
        }
        return self.market_trend

    def analyze_stock(self, sym):
        """
        Calculates 5m/15m trend, VWAP, swing structure, relative volume,
        evaluates mandatory bullish & bearish breakout conditions,
        and scores candidates out of 100.
        """
        try:
            s = requests.Session(impersonate="chrome124")
            r = s.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}.NS",
                headers=YF_HEADERS,
                params={'interval': '5m', 'range': '5d'},
                timeout=7
            )
            if r.status_code != 200:
                r = s.get(
                    f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}.BO",
                    headers=YF_HEADERS,
                    params={'interval': '5m', 'range': '5d'},
                    timeout=7
                )
                if r.status_code != 200:
                    return None

            data = r.json()
            res = data.get('chart', {}).get('result', [{}])[0]
            ts = res.get('timestamp', [])
            meta = res.get('meta', {})
            quote = res.get('indicators', {}).get('quote', [{}])[0]
            opens, highs, lows, closes, vols = quote.get('open', []), quote.get('high', []), quote.get('low', []), quote.get('close', []), quote.get('volume', [])

            candles_5m = []
            for i, t in enumerate(ts):
                if None in (opens[i], highs[i], lows[i], closes[i]): continue
                dt = datetime.fromtimestamp(t, tz=timezone.utc).astimezone(IST)
                candles_5m.append({
                    'time': t, 'dt': dt, 'open': float(opens[i]), 'high': float(highs[i]), 'low': float(lows[i]), 'close': float(closes[i]), 'volume': int(vols[i] or 0)
                })

            if len(candles_5m) < 15: return None

            by_date = {}
            for c in candles_5m:
                d = c['dt'].strftime('%Y-%m-%d')
                if d not in by_date: by_date[d] = []
                by_date[d].append(c)

            dates = sorted(by_date.keys())
            if len(dates) < 2: return None

            today_date = dates[-1]
            prev_date  = dates[-2]
            today_candles = by_date[today_date]
            prev_candles  = by_date[prev_date]

            # 9:15 to 9:45 window
            window = [c for c in today_candles if c['dt'].hour == 9 and c['dt'].minute <= 45]
            if not window: return None

            c1 = window[0]
            c1_high = round(c1['high'], 2)
            c1_low  = round(c1['low'], 2)
            pdh = round(max(c['high'] for c in prev_candles), 2)
            pdl = round(min(c['low'] for c in prev_candles), 2)
            prev_close = round(float(meta.get('previousClose', prev_candles[-1]['close'])), 2)

            ltp = round(float(meta.get('regularMarketPrice', today_candles[-1]['close'])), 2)
            chg = round(ltp - prev_close, 2)
            pChg = round((chg / prev_close) * 100, 2) if prev_close else 0.0

            # Intraday VWAP
            cum_pv = sum(((c['high'] + c['low'] + c['close']) / 3) * (c['volume'] or 1) for c in today_candles)
            cum_v  = sum((c['volume'] or 1) for c in today_candles)
            vwap   = round(cum_pv / cum_v, 2) if cum_v else ltp

            # Relative Volume
            today_vol = sum(c['volume'] for c in today_candles) or int(meta.get('regularMarketVolume', 0))
            past_vols = [sum(c['volume'] for c in by_date[d]) for d in dates[:-1] if sum(c['volume'] for c in by_date[d]) > 0]
            avg_vol = (sum(past_vols) / len(past_vols)) if past_vols else today_vol
            rel_vol = round(today_vol / avg_vol, 2) if avg_vol > 0 else 1.0

            # 5m & 15m EMAs
            closes_5m = [c['close'] for c in candles_5m]
            ema20_5m = compute_ema(closes_5m, 20)[-1]
            ema50_5m = compute_ema(closes_5m, 50)[-1]

            # 15m Synthesis
            candles_15m = []
            for idx in range(0, len(candles_5m), 3):
                chk = candles_5m[idx:idx+3]
                if chk:
                    candles_15m.append({
                        'dt': chk[0]['dt'],
                        'open': chk[0]['open'],
                        'high': max(c['high'] for c in chk),
                        'low': min(c['low'] for c in chk),
                        'close': chk[-1]['close'],
                        'volume': sum(c['volume'] for c in chk)
                    })
            closes_15m = [c['close'] for c in candles_15m]
            ema20_15m = compute_ema(closes_15m, 20)[-1] if len(closes_15m) >= 20 else ema20_5m
            ema50_15m = compute_ema(closes_15m, 50)[-1] if len(closes_15m) >= 50 else ema50_5m

            # 5m Trend Classification
            trend_5m_bull = (ema20_5m and ema50_5m and ema20_5m > ema50_5m and ltp > ema20_5m)
            trend_5m_bear = (ema20_5m and ema50_5m and ema20_5m < ema50_5m and ltp < ema20_5m)
            trend_5m = "UPTREND" if trend_5m_bull else ("DOWNTREND" if trend_5m_bear else "SIDEWAYS")

            # 15m Trend Classification
            trend_15m_bull = (ema20_15m and ema50_15m and ema20_15m > ema50_15m and ltp > ema20_15m)
            trend_15m_bear = (ema20_15m and ema50_15m and ema20_15m < ema50_15m and ltp < ema20_15m)
            trend_15m = "UPTREND" if trend_15m_bull else ("DOWNTREND" if trend_15m_bear else "SIDEWAYS")

            # Price Structure (HH/HL vs LH/LL)
            recent_highs = [c['high'] for c in today_candles[-5:]]
            recent_lows  = [c['low'] for c in today_candles[-5:]]
            is_hh_hl = (len(recent_highs) >= 3 and recent_highs[-1] > recent_highs[0] and recent_lows[-1] > recent_lows[0])
            is_lh_ll = (len(recent_highs) >= 3 and recent_highs[-1] < recent_highs[0] and recent_lows[-1] < recent_lows[0])

            # Comprehensive Individual Stock Trend
            trend_score = 0
            trend_reasons = []

            if ltp > vwap:
                trend_score += 2
                trend_reasons.append("Price > VWAP")
            else:
                trend_score -= 2
                trend_reasons.append("Price < VWAP")

            if trend_5m_bull:
                trend_score += 2.5
                trend_reasons.append("5m EMA20 > EMA50 Stack")
            elif trend_5m_bear:
                trend_score -= 2.5
                trend_reasons.append("5m EMA20 < EMA50 Stack")

            if trend_15m_bull:
                trend_score += 2
                trend_reasons.append("15m EMA20 > EMA50 Stack")
            elif trend_15m_bear:
                trend_score -= 2
                trend_reasons.append("15m EMA20 < EMA50 Stack")

            if is_hh_hl:
                trend_score += 1.5
                trend_reasons.append("Higher High / Higher Low Structure")
            elif is_lh_ll:
                trend_score -= 1.5
                trend_reasons.append("Lower High / Lower Low Structure")

            if rel_vol >= 1.5:
                trend_reasons.append(f"Volume Surge {rel_vol}x vs Avg")

            if trend_score >= 6: stock_trend = "STRONG UPTREND"
            elif trend_score >= 2: stock_trend = "UPTREND"
            elif trend_score <= -6: stock_trend = "STRONG DOWNTREND"
            elif trend_score <= -2: stock_trend = "DOWNTREND"
            else: stock_trend = "SIDEWAYS"

            # ── MANDATORY BULLISH BREAKOUT EVALUATION ──
            bull_c1_low_held = all(c['low'] >= c1_low for c in window)
            bull_c1_high_bo  = any(c['high'] > c1_high for c in window[1:]) if len(window) > 1 else False
            bull_c1_bo_candle = next((c for c in window[1:] if c['high'] > c1_high), None) if len(window) > 1 else None
            bull_c1_bo_time   = bull_c1_bo_candle['dt'].strftime('%H:%M') if bull_c1_bo_candle else None

            bull_pdh_bo      = any(c['high'] > pdh for c in window)
            bull_pdh_bo_candle = next((c for c in window if c['high'] > pdh), None)
            bull_pdh_bo_time   = bull_pdh_bo_candle['dt'].strftime('%H:%M') if bull_pdh_bo_candle else None

            bull_pdl_held    = all(c['low'] >= pdl for c in window)
            is_bull_match    = (bull_c1_low_held and bull_c1_high_bo and bull_pdh_bo and bull_pdl_held)

            bull_bo_time = None
            if bull_c1_bo_time and bull_pdh_bo_time:
                bull_bo_time = max(bull_c1_bo_time, bull_pdh_bo_time) + ' IST'
            elif bull_c1_bo_time:
                bull_bo_time = bull_c1_bo_time + ' IST'
            elif bull_pdh_bo_time:
                bull_bo_time = bull_pdh_bo_time + ' IST'

            # ── MANDATORY BEARISH BREAKDOWN EVALUATION ──
            bear_c1_high_held = all(c['high'] <= c1_high for c in window)
            bear_c1_low_bd    = any(c['low'] < c1_low for c in window[1:]) if len(window) > 1 else False
            bear_c1_bd_candle = next((c for c in window[1:] if c['low'] < c1_low), None) if len(window) > 1 else None
            bear_c1_bd_time   = bear_c1_bd_candle['dt'].strftime('%H:%M') if bear_c1_bd_candle else None

            bear_pdl_bd       = any(c['low'] < pdl for c in window)
            bear_pdl_bd_candle = next((c for c in window if c['low'] < pdl), None)
            bear_pdl_bd_time   = bear_pdl_bd_candle['dt'].strftime('%H:%M') if bear_pdl_bd_candle else None

            bear_pdh_held     = all(c['high'] <= pdh for c in window)
            is_bear_match    = (bear_c1_high_held and bear_c1_low_bd and bear_pdl_bd and bear_pdh_held)

            bear_bd_time = None
            if bear_c1_bd_time and bear_pdl_bd_time:
                bear_bd_time = max(bear_c1_bd_time, bear_pdl_bd_time) + ' IST'
            elif bear_c1_bd_time:
                bear_bd_time = bear_c1_bd_time + ' IST'
            elif bear_pdl_bd_time:
                bear_bd_time = bear_pdl_bd_time + ' IST'

            # ── TRANSPARENT 100-POINT SCORING FRAMEWORK ──
            market_regime = self.market_trend.get('regime', 'SIDEWAYS')

            # 1. Bullish Score (out of 100)
            b_s5 = 25 if trend_5m_bull else (15 if (ema20_5m and ltp > ema20_5m) else 0)
            b_s15 = 20 if trend_15m_bull else (10 if (ema20_15m and ltp > ema20_15m) else 0)
            b_svwap = 15 if ltp > vwap else (10 if abs(ltp - vwap) / vwap < 0.003 else 0)
            b_srvol = 15 if rel_vol >= 2.0 else (10 if rel_vol >= 1.2 else (5 if rel_vol >= 1.0 else 0))

            last_c = today_candles[-1]
            c_range = last_c['high'] - last_c['low']
            b_sstr = 15 if (c_range > 0 and (last_c['close'] - last_c['low']) / c_range >= 0.70) else 8

            b_smkt = 10 if market_regime == 'STRONG BULLISH' else (7 if market_regime == 'BULLISH' else (4 if market_regime == 'SIDEWAYS' else 0))
            bull_score = b_s5 + b_s15 + b_svwap + b_srvol + b_sstr + b_smkt

            bull_score_breakdown = {
                'trend_5m': b_s5,
                'trend_15m': b_s15,
                'vwap': b_svwap,
                'rel_vol': b_srvol,
                'breakout_strength': b_sstr,
                'market_alignment': b_smkt,
                'total': bull_score
            }

            # 2. Bearish Score (out of 100)
            d_s5 = 25 if trend_5m_bear else (15 if (ema20_5m and ltp < ema20_5m) else 0)
            d_s15 = 20 if trend_15m_bear else (10 if (ema20_15m and ltp < ema20_15m) else 0)
            d_svwap = 15 if ltp < vwap else (10 if abs(ltp - vwap) / vwap < 0.003 else 0)
            d_srvol = 15 if rel_vol >= 2.0 else (10 if rel_vol >= 1.2 else (5 if rel_vol >= 1.0 else 0))

            d_sstr = 15 if (c_range > 0 and (last_c['high'] - last_c['close']) / c_range >= 0.70) else 8
            d_smkt = 10 if market_regime == 'STRONG BEARISH' else (7 if market_regime == 'BEARISH' else (4 if market_regime == 'SIDEWAYS' else 0))
            bear_score = d_s5 + d_s15 + d_svwap + d_srvol + d_sstr + d_smkt

            bear_score_breakdown = {
                'trend_5m': d_s5,
                'trend_15m': d_s15,
                'vwap': d_svwap,
                'rel_vol': d_srvol,
                'breakout_strength': d_sstr,
                'market_alignment': d_smkt,
                'total': bear_score
            }

            base_record = {
                'symbol': sym,
                'ltp': ltp,
                'change': chg,
                'pChange': pChg,
                'volume': today_vol,
                'rel_vol': rel_vol,
                'vwap': vwap,
                'vwap_status': 'ABOVE' if ltp > vwap else 'BELOW',
                'c1_high': c1_high,
                'c1_low': c1_low,
                'pdh': pdh,
                'pdl': pdl,
                'trend_5m': trend_5m,
                'trend_15m': trend_15m,
                'stock_trend': stock_trend,
                'trend_reasons': trend_reasons,
                'day_high': round(max(c['high'] for c in today_candles), 2),
                'day_low': round(min(c['low'] for c in today_candles), 2)
            }

            bull_record = {
                **base_record,
                'breakout_time': bull_bo_time or '--',
                'c1_low_held': bull_c1_low_held,
                'c1_high_bo': bull_c1_high_bo,
                'pdh_bo': bull_pdh_bo,
                'pdl_held': bull_pdl_held,
                'cond1_status': 'PASS' if bull_c1_low_held else 'FAIL',
                'cond2_status': 'PASS' if bull_c1_high_bo else 'FAIL',
                'cond3_status': 'PASS' if bull_pdh_bo else 'FAIL',
                'cond4_status': 'PASS' if bull_pdl_held else 'FAIL',
                'is_full_match': is_bull_match,
                'final_status': 'SELECTED' if is_bull_match else 'REJECTED',
                'score': bull_score,
                'score_breakdown': bull_score_breakdown
            }

            bear_record = {
                **base_record,
                'breakdown_time': bear_bd_time or '--',
                'c1_high_held': bear_c1_high_held,
                'c1_low_bd': bear_c1_low_bd,
                'pdl_bd': bear_pdl_bd,
                'pdh_held': bear_pdh_held,
                'cond1_status': 'PASS' if bear_c1_high_held else 'FAIL',
                'cond2_status': 'PASS' if bear_c1_low_bd else 'FAIL',
                'cond3_status': 'PASS' if bear_pdl_bd else 'FAIL',
                'cond4_status': 'PASS' if bear_pdh_held else 'FAIL',
                'is_full_match': is_bear_match,
                'final_status': 'SELECTED' if is_bear_match else 'REJECTED',
                'score': bear_score,
                'score_breakdown': bear_score_breakdown
            }

            return bull_record, bear_record
        except Exception as e:
            return None

    def start_background_scan(self, batch_size=25):
        if self.is_running: return
        self.is_running = True
        self.is_paused = False
        self._worker_thread = threading.Thread(target=self._run_scan_loop, args=(batch_size,), daemon=True)
        self._worker_thread.start()

    def pause_scan(self):
        self.is_paused = True

    def resume_scan(self):
        self.is_paused = False

    def reset(self):
        with self._lock:
            self.is_running = False
            self.is_paused = False
            self.current_index = 0
            self.scanned_count = 0
            self.failed_count = 0
            self.bullish_results = []
            self.bearish_results = []
            self.trend_leaders = {
                'top_bullish': [],
                'top_bearish': [],
                'top_rel_volume': [],
                'sideways_mixed': []
            }
            self.all_evaluated = {}

    def scan_priority_batch(self, count=100):
        """Scans the top priority NIFTY liquid universe synchronously."""
        sample = self.symbols[:count]
        with ThreadPoolExecutor(max_workers=14) as ex:
            results = list(ex.map(self.analyze_stock, sample))

        with self._lock:
            for idx, res in enumerate(results):
                sym = sample[idx]
                if res:
                    bull_r, bear_r = res
                    self.all_evaluated[sym] = (bull_r, bear_r)
                    if bull_r['is_full_match'] and not any(x['symbol'] == sym for x in self.bullish_results):
                        self.bullish_results.append(bull_r)
                    if bear_r['is_full_match'] and not any(x['symbol'] == sym for x in self.bearish_results):
                        self.bearish_results.append(bear_r)
                    self.scanned_count += 1
                else:
                    self.failed_count += 1

            self.current_index = max(self.current_index, len(sample))
            self.last_update_time = datetime.now(IST).strftime('%H:%M:%S IST')
            self._recalculate_leaders_and_sort()
        return len(sample)

    def _recalculate_leaders_and_sort(self):
        all_records = [v[0] for v in self.all_evaluated.values()]
        self.trend_leaders['top_bullish'] = sorted(
            [r for r in all_records if r['stock_trend'] in ('STRONG UPTREND', 'UPTREND')],
            key=lambda x: (x['pChange'], x['rel_vol']), reverse=True
        )[:20]

        self.trend_leaders['top_bearish'] = sorted(
            [r for r in all_records if r['stock_trend'] in ('STRONG DOWNTREND', 'DOWNTREND')],
            key=lambda x: (-x['pChange'], x['rel_vol']), reverse=True
        )[:20]

        self.trend_leaders['top_rel_volume'] = sorted(
            all_records,
            key=lambda x: x['rel_vol'], reverse=True
        )[:20]

        self.trend_leaders['sideways_mixed'] = [
            r for r in all_records if r['stock_trend'] in ('SIDEWAYS', 'MIXED / INSUFFICIENT DATA')
        ][:20]

        # Deduplicate & Sort breakout tables by transparent score (highest score first)
        seen_b = set()
        dedup_b = []
        for b in self.bullish_results:
            if b['symbol'] not in seen_b:
                seen_b.add(b['symbol'])
                dedup_b.append(b)
        self.bullish_results = sorted(dedup_b, key=lambda x: (x['score'], x['pChange']), reverse=True)

        seen_d = set()
        dedup_d = []
        for d in self.bearish_results:
            if d['symbol'] not in seen_d:
                seen_d.add(d['symbol'])
                dedup_d.append(d)
        self.bearish_results = sorted(dedup_d, key=lambda x: (x['score'], -x['pChange']), reverse=True)

    def _run_scan_loop(self, batch_size=25):
        print(f"Starting Background Scan on {len(self.symbols)} symbols...")
        self.update_market_trend()

        while self.is_running and self.current_index < len(self.symbols):
            if self.is_paused:
                time.sleep(1)
                continue

            batch = self.symbols[self.current_index:self.current_index + batch_size]
            if not batch: break

            with ThreadPoolExecutor(max_workers=min(14, len(batch))) as executor:
                results = list(executor.map(self.analyze_stock, batch))

            with self._lock:
                for idx, res in enumerate(results):
                    sym = batch[idx]
                    if res:
                        bull_r, bear_r = res
                        self.all_evaluated[sym] = (bull_r, bear_r)
                        self.scanned_count += 1

                        if bull_r['is_full_match']:
                            self.bullish_results.append(bull_r)
                        if bear_r['is_full_match']:
                            self.bearish_results.append(bear_r)
                    else:
                        self.failed_count += 1

                self.current_index += len(batch)
                self.last_update_time = datetime.now(IST).strftime('%H:%M:%S IST')
                self._recalculate_leaders_and_sort()

            # Small delay between batches to respect rate limits
            time.sleep(0.35)

        with self._lock:
            self.is_running = False
            self.last_completed_scan = datetime.now(IST).strftime('%H:%M:%S IST')
        print(f"Scan Loop Terminated. Total Scanned: {self.scanned_count}, Failed: {self.failed_count}")

    def get_status(self):
        with self._lock:
            total = len(self.symbols)
            pending = max(0, total - self.current_index)
            pct = round((self.current_index / total) * 100, 1) if total else 0.0
            return {
                'total_symbols': total,
                'scanned': self.scanned_count,
                'pending': pending,
                'failed': self.failed_count,
                'progress_pct': pct,
                'is_running': self.is_running,
                'is_paused': self.is_paused,
                'latency_ms': self.latency_ms,
                'market_trend': self.market_trend,
                'last_update': self.last_update_time or '--:--:-- IST',
                'last_completed_scan': self.last_completed_scan or '--:--:-- IST',
                'bullish_count': len(self.bullish_results),
                'bearish_count': len(self.bearish_results),
            }

    def get_bullish_breakouts(self, selected_only=True):
        with self._lock:
            if selected_only:
                return sorted(self.bullish_results, key=lambda x: (x['score'], x['pChange']), reverse=True)
            all_b = [v[0] for v in self.all_evaluated.values()]
            return sorted(all_b, key=lambda x: (x['is_full_match'], x['score'], x['pChange']), reverse=True)

    def get_bearish_breakdowns(self, selected_only=True):
        with self._lock:
            if selected_only:
                return sorted(self.bearish_results, key=lambda x: (x['score'], -x['pChange']), reverse=True)
            all_d = [v[1] for v in self.all_evaluated.values()]
            return sorted(all_d, key=lambda x: (x['is_full_match'], x['score'], -x['pChange']), reverse=True)

    def get_trend_leaders(self):
        with self._lock:
            return self.trend_leaders

# Global singleton instance
scanner = AdvancedMarketScanner()
