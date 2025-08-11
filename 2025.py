# -*- coding: utf-8 -*-
# Telegram Crypto Picks — Every 12 Hours
# FastAPI web + APScheduler job
import os, asyncio, math, statistics
from datetime import datetime
import pytz
import httpx
import pandas as pd
import numpy as np
from fastapi import FastAPI
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

# ========= الإعدادات =========
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "PUT_YOUR_TELEGRAM_TOKEN_HERE")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "PUT_YOUR_CHAT_ID_HERE")

BINANCE_BASE = "https://api.binance.com"
KUWAIT_TZ = pytz.timezone("Asia/Kuwait")

startup_notified = False

app = FastAPI(title="Telegram Crypto Picks Every 12 Hours")

# ========= دوال مساعدة =========
async def send_telegram(text: str):
    if not TELEGRAM_TOKEN or "PUT_YOUR" in TELEGRAM_TOKEN:
        print("⚠️ TELEGRAM_TOKEN غير مضبوط")
        return
    if not TELEGRAM_CHAT_ID or "PUT_YOUR" in TELEGRAM_CHAT_ID:
        print("⚠️ TELEGRAM_CHAT_ID غير مضبوط")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    timeout = httpx.Timeout(15.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            r = await client.post(url, data=payload)
            if r.status_code != 200:
                print("Telegram error:", r.text)
        except Exception as e:
            print("Telegram exception:", e)

def rsi_14(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    gain = pd.Series(gain).ewm(alpha=1/period, adjust=False).mean()
    loss = pd.Series(loss).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / (loss.replace(0, np.nan))
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)

async def binance_get(path: str, params: dict = None):
    url = f"{BINANCE_BASE}{path}"
    timeout = httpx.Timeout(20.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(url, params=params or {})
        r.raise_for_status()
        return r.json()

async def get_under_1usd_symbols():
    tickers = await binance_get("/api/v3/ticker/price")
    symbols = []
    for t in tickers:
        sym = t.get("symbol", "")
        if sym.endswith("USDT"):
            try:
                price = float(t.get("price", "0"))
            except:
                continue
            if 0.000001 < price < 1.0:
                symbols.append((sym, price))
    return symbols

async def get_klines(symbol: str, interval="4h", limit=200):
    data = await binance_get("/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": limit})
    closes = [float(c[4]) for c in data]
    vols   = [float(c[5]) for c in data]
    times  = [int(c[0]) for c in data]
    return pd.DataFrame({"time": times, "close": closes, "vol": vols})

def pick_candidate(df: pd.DataFrame):
    rsi = rsi_14(df["close"])
    df = df.copy()
    df["rsi"] = rsi
    if len(df) < 20:
        return None

    cond_rsi_val = df["rsi"].iloc[-1] <= 45
    cond_rsi_turn = df["rsi"].iloc[-1] > df["rsi"].iloc[-2]
    vol_med = df["vol"].median()
    cond_vol = (df["vol"].iloc[-1] > vol_med) or (df["vol"].iloc[-2] > vol_med)

    score = 0
    if cond_rsi_val: score += 1
    if cond_rsi_turn: score += 1
    if cond_vol: score += 1

    return {
        "rsi_last": round(float(df["rsi"].iloc[-1]), 2),
        "rsi_prev": round(float(df["rsi"].iloc[-2]), 2),
        "vol_last": df["vol"].iloc[-1],
        "score": score,
        "close": float(df["close"].iloc[-1]),
    }

async def make_pick():
    symbols = await get_under_1usd_symbols()
    if not symbols:
        await send_telegram("⚠️ لم يتم العثور على رموز أقل من 1$ الآن.")
        return

    best = None
    best_sym = None
    to_check = symbols[:60]

    for sym, live_price in to_check:
        try:
            df = await get_klines(sym, interval="4h", limit=210)
            cand = pick_candidate(df)
            if not cand: 
                continue
            desirability = cand["score"] * 10 - abs(cand["rsi_last"] - 40)
            desirability += (df["vol"].iloc[-1] / (df["vol"].median() + 1e-9)) 
            if (best is None) or (desirability > best["desirability"]):
                best = {**cand, "desirability": desirability, "live_price": live_price}
                best_sym = sym
        except:
            continue

    if not best_sym:
        await send_telegram("⚠️ لا توجد توصية مناسبة الآن حسب الفلتر.")
        return

    entry = best["live_price"]
    stop = round(entry * 0.95, 6)
    tp1 = round(entry * 1.02, 6)
    tp2 = round(entry * 1.04, 6)

    msg = (
        "📈 *Pick Update*\n"
        f"• الرمز: {best_sym}\n"
        f"• السعر الحالي: {entry:.6f} USDT\n"
        f"• RSI(14) 4H: {best['rsi_last']} (السابق {best['rsi_prev']})\n"
        f"• وقف مبدئي: {stop}\n"
        f"• هدف 1: {tp1} — هدف 2: {tp2}\n\n"
        "تنويه: ليست نصيحة استثمارية. ✅"
    )
    await send_telegram(msg)

# ========= جدولة التشغيل =========
scheduler = AsyncIOScheduler(timezone=KUWAIT_TZ)

@app.on_event("startup")
async def on_startup():
    global startup_notified
    if not startup_notified:
        await send_telegram("✅ تم تشغيل البوت، سيتم إرسال توصية كل 12 ساعة.")
        startup_notified = True

    scheduler.add_job(make_pick, IntervalTrigger(hours=12))
    scheduler.start()

@app.get("/")
async def root():
    return {"status": "ok", "message": "Telegram Crypto Picks every 12h"}

@app.get("/healthz")
async def health():
    return {"ok": True, "now_kw": datetime.now(KUWAIT_TZ).isoformat()}