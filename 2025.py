# -*- coding: utf-8 -*-
# Trading Suite — Binance Daily Signal (+2%) + Sniper Alerts + Whales Alerts
# بدون أي ربط بمحفظة — كله تنبيهات فقط على تيليجرام

import os, time, json, csv, hashlib, datetime
import requests
import pandas as pd

# ====== إعدادات ======
TELEGRAM_TOKEN = "PUT_YOUR_TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID = "PUT_YOUR_CHAT_ID"

BASE_USDT = True                   # فلترة الأزواج على USDT فقط
MIN_24H_VOLUME_USDT = 5_000_000    # حد أدنى للسيولة اليومية
INTERVAL = "5m"                    # إطار التحليل
LIMIT = 600                        # عدد الشمعات (~2 يوم بيانات 5m)

DAILY_SIGNAL_HOUR_LOCAL = 10       # وقت إرسال الصفقة اليومية (توقيت الكويت UTC+3)
MIN_EXPECTED_MOVE_PCT = 2.0        # هدف الربح اليومي
SL_ATR_MULT = 1.5                  # وقف الخسارة = ATR × هذا المعامل
MAX_CANDIDATES = 40                # عدد أفضل الأزواج اللي نفحصها

SNIPER_POLL_SEC = 90               # فحص فرص Sniper كل X ثانية
WHALES_POLL_SEC = 90               # فحص إشارات الحيتان كل X ثانية

DATA_DIR = "data"
STATE_DIR = "state"
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(STATE_DIR, exist_ok=True)

SNIPER_FILE = os.path.join(DATA_DIR, "manual_sniper.json")
WHALES_FILE = os.path.join(DATA_DIR, "whales_signals.csv")
TAG_DAILY_FILE = os.path.join(STATE_DIR, "daily_tag.json")
SNIPER_SENT_FILE = os.path.join(STATE_DIR, "sniper_sent.json")
WHALES_SEEN_FILE = os.path.join(STATE_DIR, "whales_seen.json")

# ملفات مثال تلقائية إذا مفقودة
if not os.path.exists(SNIPER_FILE):
    with open(SNIPER_FILE, "w", encoding="utf-8") as f:
        json.dump([{"symbol":"BTCUSDT","note":"Example only","when": datetime.date.today().isoformat()}], f, ensure_ascii=False, indent=2)
if not os.path.exists(WHALES_FILE):
    with open(WHALES_FILE, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date","symbol","side","confidence","source","note"])
        w.writerow([datetime.date.today().isoformat(),"BTCUSDT","BUY","0.8","Example","Address X accumulated 200 BTC"])

# ====== تيليجرام ======
def send_telegram(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ ضع TELEGRAM_TOKEN و CHAT_ID في أعلى الملف.", flush=True); return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=15)
    except Exception as e:
        print(f"Telegram error: {e}", flush=True)

# ====== Binance ======
def bget(path, params=None):
    try:
        r = requests.get(f"https://api.binance.com{path}", params=params, timeout=20)
        r.raise_for_status(); return r.json()
    except Exception as e:
        print(f"Binance error: {e}", flush=True); return None

def get_24h_tickers():
    return bget("/api/v3/ticker/24hr") or []

def get_klines(symbol: str, interval: str, limit: int) -> pd.DataFrame:
    data = bget("/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": limit})
    if not data or isinstance(data, dict): return pd.DataFrame()
    cols = ["open_time","open","high","low","close","volume","close_time","qav","trades","taker_base","taker_quote","ignore"]
    df = pd.DataFrame(data, columns=cols)
    for c in ["open","high","low","close","volume"]: df[c] = df[c].astype(float)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    return df

# ====== مؤشرات فنية ======
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty: return df
    close = df["close"]
    # EMA
    df["ema50"] = close.ewm(span=50, adjust=False).mean()
    df["ema200"] = close.ewm(span=200, adjust=False).mean()
    # RSI (14)
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / (loss + 1e-12)
    df["rsi"] = 100 - (100 / (1 + rs))
    # MACD (12,26,9)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]
    # OBV
    obv = [0.0]
    for i in range(1, len(df)):
        if df.loc[i,"close"] > df.loc[i-1,"close"]: obv.append(obv[-1] + df.loc[i,"volume"])
        elif df.loc[i,"close"] < df.loc[i-1,"close"]: obv.append(obv[-1] - df.loc[i,"volume"])
        else: obv.append(obv[-1])
    df["obv"] = obv
    df["obv_slope"] = df["obv"].diff().rolling(10).mean()
    # ATR(14)
    high, low, prev_close = df["high"], df["low"], df["close"].shift(1)
    tr = pd.concat([(high-low),(high-prev_close).abs(),(low-prev_close).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()
    df["atr_pct"] = (df["atr"] / (df["close"] + 1e-12)) * 100.0
    return df

def get_top_usdt_symbols():
    rows = []
    for d in get_24h_tickers():
        s = d.get("symbol","")
        if BASE_USDT and not s.endswith("USDT"): continue
        try: quote_vol = float(d.get("quoteVolume","0"))
        except: continue
        rows.append((s, quote_vol))
    rows.sort(key=lambda x: x[1], reverse=True)
    return [s for s,v in rows if v >= MIN_24H_VOLUME_USDT][:max(MAX_CANDIDATES,1)]

def candidate_score(df: pd.DataFrame) -> float:
    if df.empty or len(df) < 210: return -1e9
    last, prev = df.iloc[-1], df.iloc[-2]
    score = 0.0
    if last["close"] > last["ema50"] > last["ema200"]: score += 2.5
    elif last["close"] > last["ema50"]: score += 1.5
    if last["rsi"] > 50: score += 1.0
    if last["rsi"] > prev["rsi"] and 45 <= last["rsi"] <= 70: score += 1.0
    if last["macd_hist"] > 0: score += 1.0
    if last["macd_hist"] > prev["macd_hist"]: score += 0.5
    if last["obv_slope"] > 0: score += 0.7
    if last["atr_pct"] >= (MIN_EXPECTED_MOVE_PCT/2): score += 1.0
    else: score -= 1.0
    if last["rsi"] > 80: score -= 1.0
    return float(score)

def pick_best_signal():
    ranked = []
    for s in get_top_usdt_symbols():
        df = get_klines(s, INTERVAL, LIMIT)
        if df.empty: continue
        df = compute_indicators(df)
        ranked.append((candidate_score(df), s, df))
    if not ranked: return None
    ranked.sort(key=lambda x: x[0], reverse=True)
    sc, sym, df = ranked[0]
    last = df.iloc[-1]
    entry = float(last["close"])
    tp = round(entry * (1 + MIN_EXPECTED_MOVE_PCT/100.0), 8)
    sl = round(entry - (last["atr"] * SL_ATR_MULT), 8)
    return {
        "symbol": sym, "score": sc, "entry": entry, "tp": tp, "sl": sl,
        "rsi": float(last["rsi"]), "macd_hist": float(last["macd_hist"]),
        "atr_pct": float(last["atr_pct"]), "ema50": float(last["ema50"]), "ema200": float(last["ema200"]),
    }

def compose_daily_msg(sig: dict) -> str:
    return (
        "🚀 *Daily Signal (Binance)*\n"
        f"• الزوج: {sig['symbol']}\n"
        f"• دخول: {sig['entry']}\n"
        f"• هدف (≈ +{MIN_EXPECTED_MOVE_PCT:.1f}%): {sig['tp']}\n"
        f"• وقف خسارة (ATR×{SL_ATR_MULT}): {sig['sl']}\n"
        f"• RSI: {sig['rsi']:.1f} | MACD_hist: {sig['macd_hist']:.4f}\n"
        f"• ATR%: {sig['atr_pct']:.2f}% | EMA50: {sig['ema50']:.6f} | EMA200: {sig['ema200']:.6f}\n"
        "ملاحظة: هذه توصية تحليل وليست أمرًا ماليًا."
    )

# ====== Helpers للحالة ======
def _get_json(path, default):
    try:
        with open(path,"r",encoding="utf-8") as f: return json.load(f)
    except: return default
def _set_json(path, obj):
    with open(path,"w",encoding="utf-8") as f: json.dump(obj, f, ensure_ascii=False, indent=2)

# ====== Daily Worker ======
def daily_worker():
    send_telegram("✅ المنصة تعمل — (Daily + Sniper + Whales) | تنبيهات فقط.")
    last_sent_date = None
    while True:
        now_utc = datetime.datetime.utcnow()
        kw_now = now_utc + datetime.timedelta(hours=3)  # توقيت الكويت
        if kw_now.hour == DAILY_SIGNAL_HOUR_LOCAL:
            today = kw_now.date().isoformat()
            if last_sent_date != today:
                try:
                    sig = pick_best_signal()
                    if sig: send_telegram(compose_daily_msg(sig))
                    else:   send_telegram("ℹ️ لم أجد فرصة قوية اليوم — تم التخطي.")
                    last_sent_date = today
                except Exception as e:
                    send_telegram(f"⚠️ Daily error: {e}")
        time.sleep(60)

# ====== Sniper Worker ======
def sniper_worker():
    sent = _get_json(SNIPER_SENT_FILE, {})
    while True:
        try:
            items = _get_json(SNIPER_FILE, [])
            today = datetime.date.today().isoformat()
            new_msgs = []
            for it in items:
                sym = (it.get("symbol") or "").upper()
                note = it.get("note","")
                when = it.get("when", today)
                if when != today: continue
                key = hashlib.md5(f"{sym}|{note}|{when}".encode()).hexdigest()
                if sent.get(key): continue
                sent[key] = True
                new_msgs.append(f"🎯 *Sniper Alert* — {sym}\n• التاريخ: {when}\n• ملاحظة: {note}")
            if new_msgs:
                _set_json(SNIPER_SENT_FILE, sent)
                for m in new_msgs: send_telegram(m)
        except Exception as e:
            send_telegram(f"⚠️ Sniper error: {e}")
        time.sleep(SNIPER_POLL_SEC)

# ====== Whales Worker ======
def _valid_binance_symbols():
    syms = set()
    for d in get_24h_tickers():
        s = d.get("symbol","").upper()
        if BASE_USDT and not s.endswith("USDT"): continue
        syms.add(s)
    return syms

def whales_worker():
    seen = _get_json(WHALES_SEEN_FILE, {})
    valid = _valid_binance_symbols()
    tick = 0
    while True:
        try:
            if os.path.exists(WHALES_FILE):
                with open(WHALES_FILE,"r",encoding="utf-8",newline="") as f:
                    for row in csv.DictReader(f):
                        date = (row.get("date") or "").strip()
                        symbol = (row.get("symbol") or "").strip().upper()
                        side = (row.get("side") or "").strip().upper()
                        conf = (row.get("confidence") or "").strip()
                        source = (row.get("source") or "").strip()
                        note = (row.get("note") or "").strip()
                        if not date or not symbol: continue
                        if date != datetime.date.today().isoformat(): continue
                        if symbol not in valid: continue
                        key = hashlib.md5(f"{date}|{symbol}|{side}|{note}".encode()).hexdigest()
                        if seen.get(key): continue
                        seen[key] = True
                        send_telegram(f"🐋 *Whale Signal* — {symbol}\n• التاريخ: {date}\n• العملية: {side}\n• الوثوق: {conf}\n• المصدر: {source}\n• ملاحظة: {note}")
                _set_json(WHALES_SEEN_FILE, seen)
        except Exception as e:
            send_telegram(f"⚠️ Whales error: {e}")

        tick += 1
        if tick % 20 == 0: valid = _valid_binance_symbols()
        time.sleep(WHALES_POLL_SEC)

if __name__ == "__main__":
    import threading
    threading.Thread(target=daily_worker, daemon=True).start()
    threading.Thread(target=sniper_worker, daemon=True).start()
    threading.Thread(target=whales_worker, daemon=True).start()
    while True:
        time.sleep(3600)