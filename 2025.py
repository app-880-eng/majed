# -*- coding: utf-8 -*-
# Forex Reco Bot — Daily signals (EMA50/200 + RSI14 + MACD) → Telegram
# مصدر البيانات: exchangerate.host (مجاني، تايم فريم يومي)
# يعمل كـ Background Worker على Render

import time, os, requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

# ========= الإعدادات =========
# أزواج المراقبة (عدّلها من متغير البيئة PAIRS في Render أو هنا مباشرة)
PAIRS = [p.strip().upper() for p in os.getenv("PAIRS", "EURUSD,GBPUSD,USDJPY,XAUUSD").split(",")]

CHECK_EVERY_MIN = int(os.getenv("CHECK_EVERY_MIN", "30"))  # كل كم دقيقة يعيد الفحص
COOLDOWN_HOURS  = float(os.getenv("COOLDOWN_HOURS", "12")) # تبريد لمنع تكرار الإشارة

# ===== Telegram (طلبت تكون مدموجة) =====
TELEGRAM_TOKEN   = "8295831234:AAHgdvWal7E_5_hsjPmbPiIEra4LBDRjbgU"
TELEGRAM_CHAT_ID = "1820224574"

def send_telegram(text: str):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=15)
    except Exception as e:
        print("Telegram error:", e, flush=True)

def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

# ========= جلب بيانات يومية =========
# (exchangerate.host) نحول EURUSD إلى base=EUR, symbols=USD وهكذا
def fetch_timeseries(pair: str, days: int = 420) -> pd.DataFrame:
    base = pair[:3]
    quote = pair[3:]
    end = datetime.utcnow().date()
    start = end - timedelta(days=days)
    url = "https://api.exchangerate.host/timeseries"
    params = {"start_date": start.isoformat(), "end_date": end.isoformat(),
              "base": base, "symbols": quote}
    r = requests.get(url, params=params, timeout=25)
    r.raise_for_status()
    data = r.json()
    if not data.get("rates"):
        raise RuntimeError(f"No rates for {pair}")
    dates = sorted(data["rates"].keys())
    prices = [float(list(data["rates"][d].values())[0]) for d in dates]
    df = pd.DataFrame({"time": pd.to_datetime(dates), "close": prices})
    df.set_index("time", inplace=True)
    return df

# ========= مؤشرات بسيطة =========
def ema(x: pd.Series, n: int): return x.ewm(span=n, adjust=False).mean()

def rsi(x: pd.Series, n: int = 14):
    delta = x.diff()
    up = np.where(delta > 0, delta, 0.0)
    down = np.where(delta < 0, -delta, 0.0)
    roll_up = pd.Series(up, index=x.index).rolling(n).mean()
    roll_down = pd.Series(down, index=x.index).rolling(n).mean()
    rs = roll_up / (roll_down + 1e-9)
    return 100 - (100 / (1 + rs))

def macd(x: pd.Series, fast=12, slow=26, sig=9):
    fast_ = ema(x, fast); slow_ = ema(x, slow)
    m = fast_ - slow_
    s = ema(m, sig)
    return m, s, m - s

def fmt(n: float, d: int = 5): return f"{n:.{d}f}"

# منع تكرار نفس الإشارة خلال مدة التبريد
_last_signal_ts = {}  # key=(pair, side) -> epoch

def cooldown_ok(pair: str, side: str) -> bool:
    key = (pair, side)
    t = time.time()
    last = _last_signal_ts.get(key, 0)
    if (t - last) >= COOLDOWN_HOURS * 3600:
        _last_signal_ts[key] = t
        return True
    return False

def analyze_pair(pair: str):
    df = fetch_timeseries(pair, days=420)
    if len(df) < 220:
        print(f"[{pair}] بيانات غير كافية", flush=True)
        return None

    df["ema50"] = ema(df["close"], 50)
    df["ema200"] = ema(df["close"], 200)
    df["rsi14"] = rsi(df["close"], 14)
    macd_line, macd_sig, _ = macd(df["close"])
    df["macd"], df["macd_sig"] = macd_line, macd_sig

    c0 = df.iloc[-1]  # آخر شمعة (يومي)
    c1 = df.iloc[-2]

    up_trend = (c0["close"] > c0["ema50"] > c0["ema200"])
    dn_trend = (c0["close"] < c0["ema50"] < c0["ema200"])

    rsi_up   = (c1["rsi14"] < 30) and (c0["rsi14"] > c1["rsi14"])
    rsi_down = (c1["rsi14"] > 70) and (c0["rsi14"] < c1["rsi14"])

    macd_cross_up = (c1["macd"] <= c1["macd_sig"]) and (c0["macd"] > c0["macd_sig"])
    macd_cross_dn = (c1["macd"] >= c1["macd_sig"]) and (c0["macd"] < c0["macd_sig"])

    price = float(c0["close"])

    # إشارة شراء
    if up_trend and (rsi_up or macd_cross_up):
        if cooldown_ok(pair, "BUY"):
            reason = "EMA Up + " + ("RSI↑" if rsi_up else "MACD↑")
            return {"pair": pair, "side": "BUY", "price": price, "why": reason}

    # إشارة بيع
    if dn_trend and (rsi_down or macd_cross_dn):
        if cooldown_ok(pair, "SELL"):
            reason = "EMA Down + " + ("RSI↓" if rsi_down else "MACD↓")
            return {"pair": pair, "side": "SELL", "price": price, "why": reason}

    return None

def run_once():
    for p in PAIRS:
        p = p.strip().upper()
        try:
            sig = analyze_pair(p)
            if sig:
                msg = (f"📣 توصية {sig['side']} — {sig['pair']}\n"
                       f"⏱️ {now_utc()} | فريم: Daily\n"
                       f"سعر الإشارة: {fmt(sig['price'])}\n"
                       f"السبب: {sig['why']}\n"
                       f"⚠️ جرّب على حساب تجريبي أولاً — لا توجد أرباح مضمونة.")
                print(msg, flush=True)
                send_telegram(msg)
            else:
                print(f"[{p}] لا توجد إشارة الآن.", flush=True)
        except Exception as e:
            print(f"[{p}] Error: {e}", flush=True)

if __name__ == "__main__":
    send_telegram(f"🚀 بدء بوت توصيات الفوركس | أزواج: {', '.join(PAIRS)} | فريم: Daily")
    while True:
        run_once()
        time.sleep(CHECK_EVERY_MIN * 60)