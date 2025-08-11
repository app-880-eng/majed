# -*- coding: utf-8 -*-
# Trading Suite — Binance Daily Signal (+2%) + Auto-Sniper + Auto-Whales
# تنبيهات تيليجرام فقط (بدون ربط بمحفظة)

import os, time, json, csv, hashlib, datetime
import requests
import pandas as pd

# ====== إعدادات تيليجرام ======
TELEGRAM_TOKEN = "8295831234:AAHgdvWal7E_5_hsjPmbPiIEra4LBDRjbgU"
TELEGRAM_CHAT_ID = "1820224574"

# ====== إعدادات التداول ======
BASE_USDT = True
MIN_24H_VOLUME_USDT = 5_000_000
INTERVAL = "5m"
LIMIT = 600
DAILY_SIGNAL_HOUR_LOCAL = 10   # توقيت الكويت (UTC+3)
MIN_EXPECTED_MOVE_PCT = 2.0
SL_ATR_MULT = 1.5
MAX_CANDIDATES = 40

# ====== Auto Mode (بدون إدخال يدوي) ======
AUTO_SNIPER_ENABLED = True
AUTO_WHALES_ENABLED = True
AUTO_SNIPER_POLL_SEC = 180
AUTO_WHALES_POLL_SEC = 180
AUTO_SNIPER_COOLDOWN_MIN = 45
AUTO_WHALES_COOLDOWN_MIN = 60
MAX_AUTO_SNIPER_PER_DAY = 6
MAX_AUTO_WHALES_PER_DAY = 6
SNIPER_SCORE_MIN = 4.0
BREAKOUT_MIN_PCT = 1.0
TAKER_BUY_RATIO_MIN = 0.62
DAY_CHANGE_MIN_PCT = 1.5

# ====== دورات عمل (لليدويين إذا فعّلتهم) ======
SNIPER_POLL_SEC = 90
WHALES_POLL_SEC = 90

# ====== مسارات وملفات ======
DATA_DIR = "data"
STATE_DIR = "state"
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(STATE_DIR, exist_ok=True)

SNIPER_FILE       = os.path.join(DATA_DIR, "manual_sniper.json")
WHALES_FILE       = os.path.join(DATA_DIR, "whales_signals.csv")
SNIPER_SENT_FILE  = os.path.join(STATE_DIR, "sniper_sent.json")
WHALES_SEEN_FILE  = os.path.join(STATE_DIR, "whales_seen.json")
STARTUP_SENT_FILE = os.path.join(STATE_DIR, "startup_sent.json")   # منع تكرار رسالة البدء يوميًا
STATUS_SENT_FILE  = os.path.join(STATE_DIR, "status_sent.json")    # منع تكرار “المنصة تعمل” يوميًا
AUTO_SNIPER_SENT_FILE = os.path.join(STATE_DIR, "auto_sniper_sent.json")
AUTO_WHALES_SENT_FILE = os.path.join(STATE_DIR, "auto_whales_sent.json")

# ====== إنشاء ملفات افتراضية (بدون أمثلة مزعجة) ======
if not os.path.exists(SNIPER_FILE):
    with open(SNIPER_FILE, "w", encoding="utf-8") as f:
        json.dump([], f, ensure_ascii=False, indent=2)
if not os.path.exists(WHALES_FILE):
    with open(WHALES_FILE, "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow(["date","symbol","side","confidence","source","note"])

# ====== فحص التكوين ======
def require_env():
    miss=[]
    if not TELEGRAM_TOKEN or "PUT_" in TELEGRAM_TOKEN: miss.append("TELEGRAM_TOKEN")
    if not TELEGRAM_CHAT_ID or "PUT_" in TELEGRAM_CHAT_ID: miss.append("TELEGRAM_CHAT_ID")
    if miss: raise RuntimeError("Missing required env: " + ", ".join(miss))

# ====== تيليجرام ======
def send_telegram(text: str):
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
    df["ema50"] = close.ewm(span=50,  adjust=False).mean()
    df["ema200"] = close.ewm(span=200, adjust=False).mean()

    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / (loss + 1e-12)
    df["rsi"] = 100 - (100 / (1 + rs))

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["macd"]        = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"]   = df["macd"] - df["macd_signal"]

    obv = [0.0]
    for i in range(1, len(df)):
        if df.loc[i,"close"] > df.loc[i-1,"close"]: obv.append(obv[-1] + df.loc[i,"volume"])
        elif df.loc[i,"close"] < df.loc[i-1,"close"]: obv.append(obv[-1] - df.loc[i,"volume"])
        else: obv.append(obv[-1])
    df["obv"] = obv
    df["obv_slope"] = df["obv"].diff().rolling(10).mean()

    high, low, prev_close = df["high"], df["low"], df["close"].shift(1)
    tr = pd.concat([(high-low),(high-prev_close).abs(),(low-prev_close).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()
    df["atr_pct"] = (df["atr"] / (df["close"] + 1e-12)) * 100.0
    return df

def get_top_usdt_symbols():
    rows=[]
    for d in get_24h_tickers():
        s = d.get("symbol","")
        if BASE_USDT and not s.endswith("USDT"): continue
        try: qv = float(d.get("quoteVolume","0"))
        except: continue
        rows.append((s, qv))
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
    ranked=[]
    for s in get_top_usdt_symbols():
        df = get_klines(s, INTERVAL, LIMIT)
        if df.empty: continue
        df = compute_indicators(df)
        ranked.append((candidate_score(df), s, df))
    if not ranked: return None
    ranked.sort(key=lambda x: x[0], reverse=True)
    sc, sym, df = ranked[0]
    last  = df.iloc[-1]
    entry = float(last["close"])
    tp    = round(entry * (1 + MIN_EXPECTED_MOVE_PCT/100.0), 8)
    sl    = round(entry - (last["atr"] * SL_ATR_MULT), 8)
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

# ====== Helpers (state I/O) ======
def _get_json(path, default):
    try:
        with open(path,"r",encoding="utf-8") as f: return json.load(f)
    except: return default
def _set_json(path, obj):
    with open(path,"w",encoding="utf-8") as f: json.dump(obj, f, ensure_ascii=False, indent=2)

def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def _now_kw():
    return datetime.datetime.utcnow() + datetime.timedelta(hours=3)

def _date_kw():
    return _now_kw().date().isoformat()

# ====== العمال اليدويون (اختياري) ======
def daily_worker():
    # “المنصة تعمل” مرة واحدة يوميًا
    today = datetime.date.today().isoformat()
    status_state = _get_json(STATUS_SENT_FILE, {})
    if status_state.get("date") != today:
        send_telegram("✅ المنصة تعمل — (Daily + Sniper + Whales) | تنبيهات فقط.")
        _set_json(STATUS_SENT_FILE, {"date": today})

    last_sent_date = None
    while True:
        now_utc = datetime.datetime.utcnow()
        kw_now = now_utc + datetime.timedelta(hours=3)
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

def _valid_binance_symbols():
    syms=set()
    for d in get_24h_tickers():
        s = d.get("symbol","").upper()
        if BASE_USDT and not s.endswith("USDT"): continue
        syms.add(s)
    return syms

def whales_worker():
    seen  = _get_json(WHALES_SEEN_FILE, {})
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
                        send_telegram(
                            f"🐋 *Whale Signal* — {symbol}\n"
                            f"• التاريخ: {date}\n"
                            f"• العملية: {side}\n"
                            f"• الوثوق: {conf}\n"
                            f"• المصدر: {source}\n"
                            f"• ملاحظة: {note}"
                        )
                _set_json(WHALES_SEEN_FILE, seen)
        except Exception as e:
            send_telegram(f"⚠️ Whales error: {e}")

        tick += 1
        if tick % 20 == 0: valid = _valid_binance_symbols()
        time.sleep(WHALES_POLL_SEC)

# ====== Auto Workers ======
def breakout_signal(df: pd.DataFrame):
    """اختراق بسيط فوق أعلى قمة 20 شمعة السابقة بنسبة BREAKOUT_MIN_PCT + فلاتر."""
    if df.empty or len(df) < 60:
        return None
    last = df.iloc[-1]
    prev20_high = df["high"].iloc[-21:-1].max()
    if prev20_high <= 0:
        return None
    breakout_pct = (last["close"] - prev20_high) / prev20_high * 100.0
    if breakout_pct < BREAKOUT_MIN_PCT:
        return None
    ok_trend = last["close"] > last["ema50"] > last["ema200"]
    ok_momentum = (last["rsi"] >= 50) and (last["macd_hist"] > 0)
    ok_volatility = last["atr_pct"] >= (MIN_EXPECTED_MOVE_PCT / 2)
    score = 0.0
    score += 2.0 if ok_trend else 0.0
    score += 1.2 if ok_momentum else 0.0
    score += 0.8 if ok_volatility else 0.0
    score += min(1.5, breakout_pct / 1.0)
    if score < SNIPER_SCORE_MIN:
        return None
    entry = float(last["close"])
    tp    = round(entry * (1 + MIN_EXPECTED_MOVE_PCT/100.0), 8)
    sl    = round(entry - (last["atr"] * SL_ATR_MULT), 8)
    return {
        "entry": entry, "tp": tp, "sl": sl,
        "score": float(score), "breakout_pct": float(breakout_pct),
        "rsi": float(last["rsi"]), "macd_hist": float(last["macd_hist"]),
        "atr_pct": float(last["atr_pct"]), "ema50": float(last["ema50"]), "ema200": float(last["ema200"]),
    }

def auto_sniper_worker():
    sent = read_json(AUTO_SNIPER_SENT_FILE, {"last_times": {}, "count": {}})
    while True:
        try:
            today = _date_kw()
            if sent.get("count", {}).get("date") != today:
                sent["count"] = {"date": today, "n": 0}

            if sent["count"]["n"] >= MAX_AUTO_SNIPER_PER_DAY:
                time.sleep(AUTO_SNIPER_POLL_SEC)
                continue

            for sym in get_top_usdt_symbols():
                df = compute_indicators(get_klines(sym, INTERVAL, LIMIT))
                if df.empty:
                    continue
                sig = breakout_signal(df)
                if not sig:
                    continue

                last_times = sent.get("last_times", {})
                last_ts = last_times.get(sym)
                if last_ts:
                    last_dt = datetime.datetime.fromisoformat(last_ts)
                    if (_now_kw() - last_dt).total_seconds() < AUTO_SNIPER_COOLDOWN_MIN * 60:
                        continue

                msg = (
                    f"🎯 *Auto-Sniper Breakout* — {sym}\n"
                    f"• دخول: {sig['entry']}\n"
                    f"• هدف (≈ +{MIN_EXPECTED_MOVE_PCT:.1f}%): {sig['tp']}\n"
                    f"• وقف خسارة (ATR×{SL_ATR_MULT}): {sig['sl']}\n"
                    f"• اختراق: +{sig['breakout_pct']:.2f}% | Score: {sig['score']:.2f}\n"
                    f"• RSI: {sig['rsi']:.1f} | MACD_hist: {sig['macd_hist']:.4f} | ATR%: {sig['atr_pct']:.2f}%\n"
                    f"• EMA50: {sig['ema50']:.6f} | EMA200: {sig['ema200']:.6f}"
                )
                send_telegram(msg)

                last_times[sym] = _now_kw().isoformat(timespec="seconds")
                sent["last_times"] = last_times
                sent["count"]["n"] += 1
                write_json(AUTO_SNIPER_SENT_FILE, sent)

                if sent["count"]["n"] >= MAX_AUTO_SNIPER_PER_DAY:
                    break
        except Exception as e:
            send_telegram(f"⚠️ Auto-Sniper error: {e}")
        time.sleep(AUTO_SNIPER_POLL_SEC)

def auto_whales_worker():
    sent = read_json(AUTO_WHALES_SENT_FILE, {"last_times": {}, "count": {}})
    while True:
        try:
            today = _date_kw()
            if sent.get("count", {}).get("date") != today:
                sent["count"] = {"date": today, "n": 0}

            if sent["count"]["n"] >= MAX_AUTO_WHALES_PER_DAY:
                time.sleep(AUTO_WHALES_POLL_SEC)
                continue

            tickers = get_24h_tickers() or []
            for d in tickers:
                sym = (d.get("symbol") or "").upper()
                if BASE_USDT and not sym.endswith("USDT"):
                    continue
                try:
                    qv = float(d.get("quoteVolume", "0"))
                    day_chg = float(d.get("priceChangePercent", "0"))
                    tbb = float(d.get("takerBuyBaseAssetVolume", "0"))
                    base_vol = float(d.get("volume", "0"))
                except:
                    continue
                if qv < MIN_24H_VOLUME_USDT:
                    continue
                if day_chg < DAY_CHANGE_MIN_PCT:
                    continue
                if base_vol <= 0:
                    continue
                taker_buy_ratio = (tbb / base_vol) if base_vol > 0 else 0.0
                if taker_buy_ratio < TAKER_BUY_RATIO_MIN:
                    continue

                last_times = sent.get("last_times", {})
                last_ts = last_times.get(sym)
                if last_ts:
                    last_dt = datetime.datetime.fromisoformat(last_ts)
                    if (_now_kw() - last_dt).total_seconds() < AUTO_WHALES_COOLDOWN_MIN * 60:
                        continue

                msg = (
                    f"🐋 *Auto-Whales Signal* — {sym}\n"
                    f"• تغير يومي: +{day_chg:.2f}%\n"
                    f"• سيولة 24h (Quote): {qv:,.0f} USDT\n"
                    f"• Taker Buy Ratio: {taker_buy_ratio*100:.1f}%\n"
                    f"• ملاحظة: نشاط شراء تاكر مرتفع مع سيولة كبيرة"
                )
                send_telegram(msg)

                last_times[sym] = _now_kw().isoformat(timespec="seconds")
                sent["last_times"] = last_times
                sent["count"]["n"] += 1
                write_json(AUTO_WHALES_SENT_FILE, sent)

                if sent["count"]["n"] >= MAX_AUTO_WHALES_PER_DAY:
                    break
        except Exception as e:
            send_telegram(f"⚠️ Auto-Whales error: {e}")
        time.sleep(AUTO_WHALES_POLL_SEC)

# ====== Main ======
if __name__ == "__main__":
    require_env()
    print("✅ Worker starting…", flush=True)

    # رسالة البدء: مرة واحدة يوميًا فقط
    today = datetime.date.today().isoformat()
    startup_state = _get_json(STARTUP_SENT_FILE, {})
    if startup_state.get("date") != today:
        send_telegram("✅ البوت بدأ العمل على Render (Worker).")
        _set_json(STARTUP_SENT_FILE, {"date": today})

    import threading
    threading.Thread(target=daily_worker, daemon=True).start()
    if AUTO_SNIPER_ENABLED:
        threading.Thread(target=auto_sniper_worker, daemon=True).start()
    if AUTO_WHALES_ENABLED:
        threading.Thread(target=auto_whales_worker, daemon=True).start()

    # إبقاء العملية حية
    while True:
        time.sleep(3600)