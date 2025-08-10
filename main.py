# -*- coding: utf-8 -*-
# ====== بوت توصيات تداول عملات Binance تحت 10$ مع مؤشرات EMA/RSI/MACD/OBV ======
# تشغيل ويب صغير (FastAPI) + مهمة تعمل بالخلفية ترسل توصية واحدة يوميًا على الأقل
# ملاحظة: المستخدم طلب وضع التوكن و الـ ID داخل الكود مباشرة.

import os, time, math, json, asyncio, statistics
from datetime import datetime, timezone, date
import requests
import pandas as pd
import numpy as np

from fastapi import FastAPI
import uvicorn

# ---------------- إعدادات تيليجرام ----------------
TELEGRAM_TOKEN = "8295831234:AAHgdvWal7E_5_hsjPmbPiIEra4LBDRjbgU"
TELEGRAM_CHAT_ID = "1820224574"

# ---------------- إعدادات عامة ----------------
INTERVAL = "15m"           # إطار زمني للحسابات
MIN_CANDLES = 300          # عدد الشموع المطلوبة (يفضل >= 300)
SLEEP_BETWEEN_SCANS = 60   # بالدقائق (فحص كل 60 دقيقة)
TARGET_MIN = 0.02          # 2%
TARGET_MAX = 0.10          # 10%
BINANCE_BASE = "https://api.binance.com"
USER_AGENT = "SignalBot/1.0"

# ====================== أدوات مساعدة ======================
def log(*args):
    print(*args, flush=True)

def send_telegram(text: str):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        requests.post(url, data=payload, timeout=15)
    except Exception as e:
        log("Telegram send error:", e)

def http_get(url, params=None):
    headers = {"User-Agent": USER_AGENT}
    r = requests.get(url, params=params, headers=headers, timeout=25)
    r.raise_for_status()
    return r.json()

def get_all_usdt_under_10():
    """جلب جميع أزواج USDT المتداولة وسعرها أقل من 10$"""
    # احصل على الأسعار الحالية
    prices = http_get(f"{BINANCE_BASE}/api/v3/ticker/price")
    price_map = {p["symbol"]: float(p["price"]) for p in prices if "USDT" in p["symbol"]}

    # معلومات السوق لتصفية الأزواج السبوت فقط و TRADING
    info = http_get(f"{BINANCE_BASE}/api/v3/exchangeInfo")
    symbols = []
    for s in info["symbols"]:
        if s.get("status") != "TRADING":
            continue
        if s.get("quoteAsset") != "USDT":
            continue
        if s.get("isSpotTradingAllowed") is not True:
            continue
        sym = s["symbol"]
        price = price_map.get(sym)
        if price is None:
            continue
        if price < 10.0:
            symbols.append(sym)
    return symbols

def get_klines(symbol: str, interval: str = INTERVAL, limit: int = 500) -> pd.DataFrame:
    url = f"{BINANCE_BASE}/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": min(limit, 1000)}
    data = http_get(url, params=params)
    cols = [
        "open_time","open","high","low","close","volume",
        "close_time","qav","num_trades","taker_base_vol",
        "taker_quote_vol","ignore"
    ]
    df = pd.DataFrame(data, columns=cols)
    for c in ["open","high","low","close","volume","qav","taker_base_vol","taker_quote_vol"]:
        df[c] = df[c].astype(float)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    return df

def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def rsi(series, period=14):
    delta = series.diff()
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    roll_up = pd.Series(gain).rolling(period).mean()
    roll_down = pd.Series(loss).rolling(period).mean()
    rs = roll_up / (roll_down + 1e-12)
    rsi_vals = 100.0 - (100.0 / (1.0 + rs))
    rsi_series = pd.Series(rsi_vals, index=series.index)
    return rsi_series

def macd(series, fast=12, slow=26, signal=9):
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist

def obv(close, volume):
    direction = np.sign(close.diff().fillna(0))
    return (direction * volume).fillna(0).cumsum()

def atr(df, period=14):
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def slope(series, window=20):
    """انحدار بسيط كإشارة اتجاه"""
    if len(series) < window:
        return 0.0
    y = series[-window:]
    x = np.arange(len(y))
    x_mean = x.mean()
    y_mean = y.mean()
    denom = ((x - x_mean) ** 2).sum()
    if denom == 0:
        return 0.0
    m = ((x - x_mean) * (y - y_mean)).sum() / denom
    return float(m)

# ====================== إستراتيجية الإشارات ======================
def score_and_signal(df: pd.DataFrame):
    """إرجاع (score, signal_dict) أو (None, None)"""
    if len(df) < MIN_CANDLES:
        return None, None

    close = df["close"]
    vol = df["volume"]

    df["ema20"]  = ema(close, 20)
    df["ema50"]  = ema(close, 50)
    df["ema200"] = ema(close, 200)
    df["rsi14"]  = rsi(close, 14)
    macd_line, signal_line, hist = macd(close)
    df["macd"] = macd_line
    df["macd_signal"] = signal_line
    df["macd_hist"] = hist
    df["obv"] = obv(close, vol)
    df["atr14"] = atr(df, 14)

    # آخر سطر
    last = df.iloc[-1]
    prev = df.iloc[-2]

    # شروط الإتجاه
    trend_up = (last["ema20"] > last["ema50"] > last["ema200"]) and (last["close"] > last["ema20"])
    # زخم
    rsi_ok = 50 <= last["rsi14"] <= 75
    # MACD صعودي أو هيستوجرام يتحسن
    macd_bullish = (last["macd"] > last["macd_signal"]) or (last["macd_hist"] > prev["macd_hist"] > 0)
    # OBV صاعد (انحدار إيجابي)
    obv_slope = slope(df["obv"], 30)
    obv_up = obv_slope > 0

    # فلتر حجم تداول: أعلى من متوسط 20 شمعة
    vol_ok = last["volume"] > df["volume"].rolling(20).mean().iloc[-1]

    # احسب نقاط (هيوريستك)
    score = 0
    score += 35 if trend_up else 0
    score += 20 if rsi_ok else 0
    score += 25 if macd_bullish else 0
    score += 10 if obv_up else 0
    score += 10 if vol_ok else 0

    if score == 0:
        return None, None

    entry = float(last["close"])
    atr_val = float(last["atr14"]) if not math.isnan(last["atr14"]) else entry * 0.01  # احتياط
    # ستوب لوز مقترح: 1×ATR أو 2% (الأكبر)
    sl = entry - max(atr_val, entry * 0.02)
    # هدف ربح: 1.5×ATR كحد أولي
    tp_raw = entry + 1.5 * atr_val
    tp_pct = (tp_raw / entry) - 1.0
    # اضبط ضمن 2%-10%
    if tp_pct < TARGET_MIN:
        tp = entry * (1.0 + TARGET_MIN)
    elif tp_pct > TARGET_MAX:
        tp = entry * (1.0 + TARGET_MAX)
    else:
        tp = tp_raw

    # نسبة نجاح تقديرية (هيوريستك بسيطة)
    prob = 50
    if trend_up:    prob += 12
    if rsi_ok:      prob += 8
    if macd_bullish:prob += 12
    if obv_up:      prob += 6
    if vol_ok:      prob += 6
    prob = max(40, min(90, prob))

    signal = {
        "entry": round(entry, 8),
        "take_profit": round(tp, 8),
        "stop_loss": round(sl, 8),
        "success_prob": int(prob)
    }
    return int(score), signal

def format_signal_msg(symbol: str, sig: dict) -> str:
    # "اسم العمله :\nسعر الدخول :\nسعر البيع مع الربح :\nستوب لوز مناسب\nنسبة نجاح الصفقه"
    return (
        f"اسم العمله : {symbol}\n"
        f"سعر الدخول : {sig['entry']}\n"
        f"سعر البيع مع الربح : {sig['take_profit']}\n"
        f"ستوب لوز مناسب : {sig['stop_loss']}\n"
        f"نسبة نجاح الصفقه : {sig['success_prob']}%"
    )

# ====================== جدولة المسح اليومي ======================
last_sent_date: date | None = None

async def daily_scanner():
    global last_sent_date
    await asyncio.sleep(5)  # مهلة قصيرة بعد الإقلاع
    while True:
        try:
            now_date = datetime.now(timezone.utc).date()
            should_send_today = (last_sent_date != now_date)

            log(f"[SCAN] Start — {datetime.now().isoformat()} | should_send_today={should_send_today}")

            symbols = get_all_usdt_under_10()
            candidates = []

            for sym in symbols:
                try:
                    df = get_klines(sym, INTERVAL, limit=600)
                    if len(df) < MIN_CANDLES:
                        continue
                    score, sig = score_and_signal(df)
                    if score is not None:
                        candidates.append((score, sym, sig))
                except Exception as e:
                    # تجاهل أخطاء زوج محدد
                    continue

            # رتب حسب أعلى نقاط
            candidates.sort(key=lambda x: x[0], reverse=True)

            if candidates:
                best_score, best_sym, best_sig = candidates[0]
                msg = "توصية اليوم:\n" + format_signal_msg(best_sym, best_sig)
                if should_send_today:
                    send_telegram(msg)
                    last_sent_date = now_date
                    log(f"[SCAN] Sent daily pick {best_sym} score={best_score}")
                else:
                    log("[SCAN] Already sent today; skipped sending.")
            else:
                # في حال لم نجد أي مرشح—والمستخدم طلب على الأقل توصية يوميًا
                # سنحاول اختيار أفضل زوج عبر فلتر بدائي (أعلى حجم) ثم إرسال رسالة معلوماتية
                prices = http_get(f"{BINANCE_BASE}/api/v3/ticker/24hr")
                under10 = [p for p in prices if p["symbol"].endswith("USDT") and float(p["lastPrice"]) < 10.0]
                under10.sort(key=lambda x: float(x.get("quoteVolume", 0.0)), reverse=True)
                if under10 and should_send_today:
                    alt = under10[0]
                    sym = alt["symbol"]
                    df = get_klines(sym, INTERVAL, limit=600)
                    _score, sig = score_and_signal(df)
                    if sig:
                        msg = "توصية اليوم (أفضل المتاح):\n" + format_signal_msg(sym, sig)
                    else:
                        # إذا ما قدرنا نحسب مؤشرات، نرسل أقرب نقطة دخول معلوماتية
                        entry = float(df["close"].iloc[-1]) if len(df) else float(alt["lastPrice"])
                        tp = round(entry * (1.0 + TARGET_MIN), 8)
                        sl = round(entry * (1.0 - TARGET_MIN), 8)
                        msg = (
                            "توصية اليوم (بديلة مبسطة):\n"
                            f"اسم العمله : {sym}\n"
                            f"سعر الدخول : {round(entry,8)}\n"
                            f"سعر البيع مع الربح : {tp}\n"
                            f"ستوب لوز مناسب : {sl}\n"
                            f"نسبة نجاح الصفقه : 50%"
                        )
                    send_telegram(msg)
                    last_sent_date = now_date
                    log(f"[SCAN] Sent fallback pick {sym}")
                else:
                    log("[SCAN] No candidates; nothing sent this hour.")

        except Exception as e:
            log("[SCAN] Error:", e)

        await asyncio.sleep(SLEEP_BETWEEN_SCANS * 60)

# ====================== تطبيق FastAPI (صحيّات فقط) ======================
app = FastAPI()

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(daily_scanner())
    send_telegram("✅ تم تشغيل البوت وهو يعمل الآن.")

@app.get("/")
def root():
    return {"ok": True, "msg": "Crypto Signal Bot running."}

@app.get("/health")
def health():
    return {"status": "healthy", "last_sent_date": str(last_sent_date) if last_sent_date else None}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), workers=1)
