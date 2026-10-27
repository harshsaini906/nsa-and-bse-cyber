import math
import time
import json
from datetime import datetime, timezone, timedelta
from curl_cffi import requests

IST = timezone(timedelta(hours=5, minutes=30))

YF_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/json',
}

# Standard Indian F&O Instrument specs
FO_SPECS = {
    'NIFTY': {'name': 'NIFTY 50 INDEX', 'step': 50, 'lot_size': 25, 'yf_sym': '^NSEI', 'base_iv': 0.138},
    'BANKNIFTY': {'name': 'NIFTY BANK INDEX', 'step': 100, 'lot_size': 15, 'yf_sym': '^NSEBANK', 'base_iv': 0.165},
    'FINNIFTY': {'name': 'NIFTY FINANCIAL SERVICES', 'step': 50, 'lot_size': 25, 'yf_sym': 'NIFTY_FIN_SERVICE.NS', 'base_iv': 0.145},
    'MIDCPNIFTY': {'name': 'NIFTY MIDCAP SELECT', 'step': 25, 'lot_size': 50, 'yf_sym': '^CRSLDX', 'base_iv': 0.170},
    'RELIANCE': {'name': 'RELIANCE INDUSTRIES', 'step': 20, 'lot_size': 250, 'yf_sym': 'RELIANCE.NS', 'base_iv': 0.190},
    'HDFCBANK': {'name': 'HDFC BANK LIMITED', 'step': 10, 'lot_size': 550, 'yf_sym': 'HDFCBANK.NS', 'base_iv': 0.180},
    'ICICIBANK': {'name': 'ICICI BANK LIMITED', 'step': 10, 'lot_size': 700, 'yf_sym': 'ICICIBANK.NS', 'base_iv': 0.185},
    'SBIN': {'name': 'STATE BANK OF INDIA', 'step': 5, 'lot_size': 750, 'yf_sym': 'SBIN.NS', 'base_iv': 0.210},
    'TCS': {'name': 'TATA CONSULTANCY SERVICES', 'step': 20, 'lot_size': 175, 'yf_sym': 'TCS.NS', 'base_iv': 0.175},
    'INFY': {'name': 'INFOSYS LIMITED', 'step': 10, 'lot_size': 400, 'yf_sym': 'INFY.NS', 'base_iv': 0.200},
    'TATAMOTORS': {'name': 'TATA MOTORS LIMITED', 'step': 10, 'lot_size': 700, 'yf_sym': 'TATAMOTORS.NS', 'base_iv': 0.240},
    'BAJFINANCE': {'name': 'BAJAJ FINANCE LIMITED', 'step': 50, 'lot_size': 125, 'yf_sym': 'BAJFINANCE.NS', 'base_iv': 0.225},
    'ITC': {'name': 'ITC LIMITED', 'step': 5, 'lot_size': 1600, 'yf_sym': 'ITC.NS', 'base_iv': 0.160},
    'LT': {'name': 'LARSEN & TOUBRO', 'step': 20, 'lot_size': 150, 'yf_sym': 'LT.NS', 'base_iv': 0.195},
    'BHARTIARTL': {'name': 'BHARTI AIRTEL LIMITED', 'step': 10, 'lot_size': 475, 'yf_sym': 'BHARTIARTL.NS', 'base_iv': 0.170},
}

def norm_cdf(x):
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0

def norm_pdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)

def bs_call(S, K, T, r, sigma):
    if T <= 0.0001:
        return max(0.0, S - K), 1.0 if S > K else 0.0, 0.0, 0.0, 0.0
    sigma = max(0.01, sigma)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    price = S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
    delta = norm_cdf(d1)
    gamma = norm_pdf(d1) / (S * sigma * math.sqrt(T))
    theta = -(S * norm_pdf(d1) * sigma) / (2.0 * math.sqrt(T)) - r * K * math.exp(-r * T) * norm_cdf(d2)
    theta = theta / 365.0
    vega = (S * math.sqrt(T) * norm_pdf(d1)) / 100.0

    return max(0.05, round(price, 2)), round(delta, 3), round(gamma, 5), round(theta, 2), round(vega, 2)

def bs_put(S, K, T, r, sigma):
    if T <= 0.0001:
        return max(0.0, K - S), -1.0 if K > S else 0.0, 0.0, 0.0, 0.0
    sigma = max(0.01, sigma)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    price = K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)
    delta = norm_cdf(d1) - 1.0
    gamma = norm_pdf(d1) / (S * sigma * math.sqrt(T))
    theta = -(S * norm_pdf(d1) * sigma) / (2.0 * math.sqrt(T)) + r * K * math.exp(-r * T) * norm_cdf(-d2)
    theta = theta / 365.0
    vega = (S * math.sqrt(T) * norm_pdf(d1)) / 100.0

    return max(0.05, round(price, 2)), round(delta, 3), round(gamma, 5), round(theta, 2), round(vega, 2)

def get_upcoming_expiries(symbol):
    now = datetime.now(IST)
    target_weekday = 2 if symbol == 'BANKNIFTY' else 3
    
    expiries = []
    d = now
    while len(expiries) < 3:
        days_ahead = target_weekday - d.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        next_expiry = d + timedelta(days=days_ahead)
        expiries.append(next_expiry.strftime('%d-%b-%Y').upper())
        d = next_expiry

    return expiries

def get_underlying_quote(symbol):
    spec = FO_SPECS.get(symbol, {})
    yf_sym = spec.get('yf_sym', f"{symbol}.NS")

    try:
        s = requests.Session(impersonate="chrome124")
        r = s.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_sym}?interval=5m&range=2d", headers=YF_HEADERS, timeout=7)
        if r.status_code == 200:
            data = r.json()
            res = data.get('chart', {}).get('result', [{}])[0]
            meta = res.get('meta', {})
            ltp = float(meta.get('regularMarketPrice') or meta.get('chartPreviousClose') or 22600.0)
            prev_close = float(meta.get('previousClose') or meta.get('chartPreviousClose') or ltp)
            chg = round(ltp - prev_close, 2)
            pChg = round((chg / prev_close) * 100, 2) if prev_close else 0.0
            return ltp, prev_close, chg, pChg
    except Exception as e:
        print(f"Error fetching quote for {symbol}:", e)

    defaults = {
        'NIFTY': (22600.0, 22687.7, -87.7, -0.39),
        'BANKNIFTY': (54287.35, 54925.7, -638.35, -1.16),
        'FINNIFTY': (24150.0, 24220.0, -70.0, -0.29),
        'RELIANCE': (1340.0, 1335.0, 5.0, 0.37),
    }
    return defaults.get(symbol, (22600.0, 22687.7, -87.7, -0.39))

def compute_option_chain(symbol='NIFTY', expiry=None):
    symbol = symbol.upper().strip()
    spec = FO_SPECS.get(symbol, {
        'name': f"{symbol} EQUITY",
        'step': 10 if 'BANK' not in symbol else 100,
        'lot_size': 100,
        'yf_sym': f"{symbol}.NS",
        'base_iv': 0.18
    })

    spot, prev_close, chg, pChg = get_underlying_quote(symbol)
    expiries = get_upcoming_expiries(symbol)
    selected_expiry = expiry if (expiry and expiry in expiries) else expiries[0]

    # Calculate days to expiry (DTE)
    exp_dt = datetime.strptime(selected_expiry, '%d-%b-%Y').replace(hour=15, minute=30, tzinfo=IST)
    now = datetime.now(IST)
    diff = exp_dt - now
    days_to_exp = max(0.5, diff.total_seconds() / 86400.0)
    T = days_to_exp / 365.0
    r = 0.07
    base_iv = spec.get('base_iv', 0.15)

    step = spec['step']
    atm_strike = round(spot / step) * step

    # 15 strikes below and 15 strikes above ATM (total 31 strikes)
    strikes_range = 15
    strike_list = [atm_strike + (i * step) for i in range(-strikes_range, strikes_range + 1)]

    chain_rows = []
    total_call_oi = 0
    total_put_oi = 0
    total_call_vol = 0
    total_put_vol = 0

    highest_call_oi = 0
    major_resistance = atm_strike + (2 * step)
    highest_put_oi = 0
    major_support = atm_strike - (2 * step)

    call_oi_map = {}
    put_oi_map = {}

    for k in strike_list:
        is_atm = (k == atm_strike)
        dist_pct = (k - spot) / spot

        # Volatility smile / skew
        iv_call = max(0.08, base_iv + 0.04 * (dist_pct ** 2) - 0.02 * dist_pct)
        iv_put  = max(0.08, base_iv + 0.05 * (dist_pct ** 2) + 0.03 * dist_pct)

        c_ltp, c_delta, c_gamma, c_theta, c_vega = bs_call(spot, k, T, r, iv_call)
        p_ltp, p_delta, p_gamma, p_theta, p_vega = bs_put(spot, k, T, r, iv_put)

        c_prev, _, _, _, _ = bs_call(prev_close, k, max(0.001, T + 1/365.0), r, iv_call)
        p_prev, _, _, _, _ = bs_put(prev_close, k, max(0.001, T + 1/365.0), r, iv_put)
        c_chg = round(c_ltp - c_prev, 2)
        c_pChg = round((c_chg / c_prev) * 100, 2) if c_prev else 0.0
        p_chg = round(p_ltp - p_prev, 2)
        p_pChg = round((p_chg / p_prev) * 100, 2) if p_prev else 0.0

        # Distribution of Open Interest (higher for round strikes and ATM/OTM concentration)
        abs_dist = abs(k - spot) / (step * 7.0)
        oi_weight = math.exp(-0.45 * (abs_dist ** 2))

        # Higher weight for major round numbers
        major_mod = step * 10 if 'NIFTY' in symbol else step * 5
        is_major_round = (k % major_mod == 0)
        round_mult = 1.7 if is_major_round else (1.3 if (k % (step * 5) == 0) else 1.0)

        # Base OI factor
        base_oi_scale = 1800000 if 'NIFTY' in symbol else 140000
        # Call OI peaks above spot (resistance); Put OI peaks below spot (support)
        c_bias = 1.25 if k > spot else (0.9 if is_atm else 0.65)
        p_bias = 1.25 if k < spot else (0.9 if is_atm else 0.65)

        c_oi = int(base_oi_scale * oi_weight * round_mult * c_bias)
        p_oi = int(base_oi_scale * oi_weight * round_mult * p_bias)

        c_oichg = int(c_oi * (0.09 if chg < 0 else -0.06))
        p_oichg = int(p_oi * (0.14 if chg < 0 else -0.05))

        c_vol = int(c_oi * 0.38)
        p_vol = int(p_oi * 0.34)

        total_call_oi += c_oi
        total_put_oi  += p_oi
        total_call_vol += c_vol
        total_put_vol  += p_vol

        call_oi_map[k] = c_oi
        put_oi_map[k]  = p_oi

        # Track Major Resistance (Highest Call OI at or above spot)
        if k >= spot and c_oi > highest_call_oi:
            highest_call_oi = c_oi
            major_resistance = k

        # Track Major Support (Highest Put OI at or below spot)
        if k <= spot and p_oi > highest_put_oi:
            highest_put_oi = p_oi
            major_support = k

        # Buildup determination
        if c_chg >= 0 and c_oichg >= 0: c_buildup = "LONG BUILDUP"
        elif c_chg < 0 and c_oichg >= 0: c_buildup = "SHORT BUILDUP"
        elif c_chg >= 0 and c_oichg < 0: c_buildup = "SHORT COVERING"
        else: c_buildup = "LONG UNWINDING"

        if p_chg >= 0 and p_oichg >= 0: p_buildup = "LONG BUILDUP"
        elif p_chg < 0 and p_oichg >= 0: p_buildup = "SHORT BUILDUP"
        elif p_chg >= 0 and p_oichg < 0: p_buildup = "SHORT COVERING"
        else: p_buildup = "LONG UNWINDING"

        chain_rows.append({
            'strike': k,
            'is_atm': is_atm,
            'ce': {
                'ltp': c_ltp,
                'change': c_chg,
                'pChange': c_pChg,
                'oi': c_oi,
                'oi_change': c_oichg,
                'volume': c_vol,
                'iv': round(iv_call * 100, 2),
                'delta': c_delta,
                'gamma': c_gamma,
                'theta': c_theta,
                'vega': c_vega,
                'buildup': c_buildup,
                'in_the_money': (k <= spot)
            },
            'pe': {
                'ltp': p_ltp,
                'change': p_chg,
                'pChange': p_pChg,
                'oi': p_oi,
                'oi_change': p_oichg,
                'volume': p_vol,
                'iv': round(iv_put * 100, 2),
                'delta': p_delta,
                'gamma': p_gamma,
                'theta': p_theta,
                'vega': p_vega,
                'buildup': p_buildup,
                'in_the_money': (k >= spot)
            }
        })

    # PCR
    pcr = round(total_put_oi / total_call_oi, 2) if total_call_oi else 1.0
    if pcr >= 1.25: pcr_signal = "BULLISH (HEAVY PUT WRITING / STRONG SUPPORT)"
    elif pcr <= 0.75: pcr_signal = "BEARISH (HEAVY CALL WRITING / OVERHEAD RESISTANCE)"
    else: pcr_signal = "NEUTRAL / SIDEWAYS CONSOLIDATION"

    # Max Pain Calculation
    min_loss = float('inf')
    max_pain = atm_strike
    for candidate in strike_list:
        total_loss = 0
        for k in strike_list:
            if candidate > k:
                total_loss += (candidate - k) * call_oi_map.get(k, 0)
            if candidate < k:
                total_loss += (k - candidate) * put_oi_map.get(k, 0)
        if total_loss < min_loss:
            min_loss = total_loss
            max_pain = candidate

    # ATM Straddle
    atm_row = next((r for r in chain_rows if r['is_atm']), chain_rows[len(chain_rows) // 2])
    atm_call_ltp = atm_row['ce']['ltp']
    atm_put_ltp  = atm_row['pe']['ltp']
    atm_straddle = round(atm_call_ltp + atm_put_ltp, 2)
    expected_low = round(spot - atm_straddle, 2)
    expected_high = round(spot + atm_straddle, 2)

    return {
        'symbol': symbol,
        'underlying_name': spec.get('name', f"{symbol} DERIVATIVE"),
        'spot_price': spot,
        'prev_close': prev_close,
        'change': chg,
        'pChange': pChg,
        'timestamp': datetime.now(IST).strftime('%d-%b-%Y %I:%M:%S %p IST'),
        'current_expiry': selected_expiry,
        'available_expiries': expiries,
        'days_to_expiry': round(days_to_exp, 1),
        'lot_size': spec.get('lot_size', 25),
        'pcr': pcr,
        'pcr_signal': pcr_signal,
        'max_pain': max_pain,
        'atm_strike': atm_strike,
        'atm_straddle': atm_straddle,
        'expected_range_low': expected_low,
        'expected_range_high': expected_high,
        'total_call_oi': total_call_oi,
        'total_put_oi': total_put_oi,
        'total_call_vol': total_call_vol,
        'total_put_vol': total_put_vol,
        'major_resistance': major_resistance,
        'major_support': major_support,
        'strikes': chain_rows
    }
