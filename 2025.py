# -*- coding: utf-8 -*-
# Forex Reco Bot — exchangerate.host + Telegram — Worker على Render
# مؤشرات: EMA50/200 + RSI14 + MACD(12,26,9)
# يرسل توصيات BUY/SELL مع سبب الإشارة، مرة واحدة لكل كسر/تقاطع (تبريد داخلي)

import time, os, math, requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

# ===== إعدادات عامة =====
PAIRS = os.getenv("PAIRS", "EURUSD,GBPUSD,USDJPY,XAUUSD").split(",")
CHECK_EVERY_MIN = int(os.getenv("CHECK_EVERY_MIN", "30"))   # كل كم دقيقة نعيد الفحص
COOLDOWN_HOURS  = float(os.getenv("COOLDOWN_HOURS", "12"))  # تبريد لمنع التكرار

# Telegram (حسب طلبك مدموجين)
TELEGRAM_TOKEN = "8295831234:AAHgdvWal7E_5_hsjPmbPiIEra4LBDRjbgU"
TELEGRAM_CHAT_ID = "1820224574"

def send_telegram(msg: str):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=15)
    except Exception as e:
        print("Telegram error:", e, flush=True)

def now_utc_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

# ===== بيانات الفوركس (يومي مجاني) =====
# exchangerate.host يعطينا سعر زوجين عبر base/quote (يومي)
def fetch_timeseries(pair: str, days: int = 400):
    # pair مثل EURUSD أو USDJPY أو XAUUSD
    pair = pair.strip().upper()
    base = pair[:3]
    quote = pair[3:]

    end = datetime.utcnow().date()
    start = end - timedelta(days=days)
    url = "https://api.exchangerate.host/timeseries"
    params = {"start_date": start.isoformat(), "end_date": end.isoformat(), "base": base, "symbols": quote}
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    if not data.get("rates"):
        raise RuntimeError(f"No rates for {pair}")

    dates = sorted(data["rates"].keys())
    prices = [float(list(data["rates"][d].values())[0]) for d in dates]

    df = pd.DataFrame({"time": pd.to_datetime(dates), "close": prices})
    df.set_index("time", inplace=True)
    return df

# ===== المؤشرات =====
def ema(series, n):
    return series.ewm(span=n, adjust=False).mean()

def rsi(series, n=14):
    delta = series.diff()
    up = np.where(delta > 0, delta, 0.0)
    down = np.where(delta < 0, -delta, 0.0)
    roll_up = pd.Series(up, index=series.index).rolling(n).mean()
    roll_down = pd.Series(down, index=series.index).rolling(n).mean()
    rs = roll_up / (roll_down + 1e-9)
    return 100.0 - (100.0 / (1.0 + rs))

def macd(series, fast=12, slow=26, signal_len=9):
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal = ema(macd_line, signal_len)
    hist = macd_line - signal
    return macd_line, signal, hist

# تبريد لمنع إعادة نفس الإشارة
last_signal_ts = {}  # key=(pair, side) -> timestamp

def cooldown_ok(pair, side):
    key = (pair, side)
    t = time.time()
    last = last_signal_ts.get(key, 0)
    if (t - last) >= COOLDOWN_HOURS * 3600:
        last_signal_ts[key] = t
        return True
    return False

def analyze_pair(pair: str):
    df = fetch_timeseries(pair, days=400)
    if len(df) < 220:
        print(f"[{pair}] بيانات غير كافية"); return None

    df["ema50"] = ema(df["close"], 50)
    df["ema200"] = ema(df["close"], 200)
    df["rsi14"] = rsi(df["close"], 14)
    macd_line, macd_sig, _ = macd(df["close"], 12, 26, 9)
    df["macd"] = macd_line
    df["macd_sig"] = macd_sig

    c0 = df.iloc[-1]  # الشمعة الحالية (يومي)
    c1 = df.iloc[-2]  # السابقة

    up_trend = (c0["close"] > c0["ema50"] > c0["ema200"])
    dn_trend = (c0["close"] < c0["ema50"] < c0["ema200"])

    rsi_up   = (c1["rsi14"] < 30) and (c0["rsi14"] > c1["rsi14"])
    rsi_down = (c1["rsi14"] > 70) and (c0["rsi14"] < c1["rsi14"])

    macd_cross_up = (c1["macd"] <= c1["macd_sig"]) and (c0["macd"] > c0["macd_sig"])
    macd_cross_dn = (c1["macd"] >= c1["macd_sig"]) and (c0["macd"] < c0["macd_sig"])

    price = float(c0["close"])

    if up_trend and (rsi_up or macd_cross_up):
        side = "BUY"
        if cooldown_ok(pair, side):
            why = "EMA Up + " + ("RSI↑" if rsi_up else "MACD↑")
            return {"pair": pair, "side": side, "price": price, "why": why}

    if dn_trend and (rsi_down or macd_cross_dn):
        side = "SELL"
        if cooldown_ok(pair, side):
            why = "EMA Down + " + ("RSI↓" if rsi_down else "MACD↓")
            return {"pair": pair, "side": side, "price": price, "why": why}

    return None

def fmt(x, d=5): 
    return f"{x:.{d}f}"

def run_once():
    for p in PAIRS:
        p = p.strip().upper()
        try:
            sig = analyze_pair(p)
            if sig:
                msg = (f"📣 توصية {sig['side']} — {sig['pair']}\n"
                       f"⏱️ {now_utc_str()} | فريم: Daily\n"
                       f"سعر الإشارة: {fmt(sig['price'])}\n"
                       f"السبب: {sig['why']}\n"
                       f"تنبيه: لا توجد أرباح مضمونة — جرّب على Demo أولاً.")
                print(msg, flush=True)
                send_telegram(msg)
            else
