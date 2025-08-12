# -*- coding: utf-8 -*-
# 2025.py — FX Quick Scalper Alerts (Render-ready, FastAPI + Background Task)
import os, time, threading, datetime as dt
from typing import Dict, Optional, Tuple, List
import pandas as pd
import numpy as np
import requests
import yfinance as yf
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

TELEGRAM_TOKEN = "8295831234:AAHgdvWal7E_5_hsjPmbPiIEra4LBDRjbgU"
TELEGRAM_CHAT_ID = "1820224574"

EMA_FAST = 50
EMA_SLOW = 200
RSI_LEN  = 14
BB_LEN   = 20
BB_STD   = 2.0
SL_PIPS = 10
TP_PIPS = 15
POLL_SECONDS = 60
HISTORY_M1   = 800
HISTORY_M15  = 900

SYMBOLS_MAP = {
    "EURUSD=X": "EURUSD",
    "GBPUSD=X": "GBPUSD",
    "USDJPY=X": "USDJPY",
    "USDCHF=X": "USDCHF",
    "USDCAD=X": "USDCAD",
    "AUDUSD=X": "AUDUSD",
    "NZDUSD=X": "NZDUSD",
    "EURJPY=X": "EURJPY",
    "GBPJPY=X": "GBPJPY",
    "XAUUSD=X": "XAUUSD",
}
YF_SYMBOLS: List[str] = list(SYMBOLS_MAP.keys())
_last_signal_key: Dict[str, str] = {}

def log(msg: str): print(f"[{dt.datetime.utcnow().isoformat()}] {msg}", flush=True)
def send_telegram(text: str):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=15)
    except Exception as e:
        log(f"Telegram error: {e}")

def pip_size(sym: str) -> float:
    s = sym.upper()
    if "JPY" in s: return 0.01
    if "XAU" in s or "GOLD" in s: return 0.1
    return 0.0001

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ema_fast"] = out["close"].ewm(span=EMA_FAST, adjust=False).mean()
    out["ema_slow"] = out["close"].ewm(span=EMA_SLOW, adjust=False).mean()
    d = out["close"].diff()
    gain = (d.where(d > 0, 0.0)).rolling(RSI_LEN).mean()
    loss = (-d.where(d < 0, 0.0)).rolling(RSI_LEN).mean()
    rs = gain / loss.replace(0, np.nan)
    out["rsi"] = 100 - (100 / (1 + rs))
    ma = out["close"].rolling(BB_LEN).mean()
    std = out["close"].rolling(BB_LEN).std(ddof=0)
    out["bb_mid"] = ma
    out["bb_up"]  = ma + BB_STD * std
    out["bb_dn"]  = ma - BB_STD * std
    return out

def trend_direction(df_m15: pd.DataFrame) -> Optional[str]:
    last = df_m15.iloc[-1]
    if np.isnan(last["ema_fast"]) or np.isnan(last["ema_slow"]): return None
    if last["ema_fast"] > last["ema_slow"]: return "up"
    if last["ema_fast"] < last["ema_slow"]: return "down"
    return None

def entry_signal(df_m1: pd.DataFrame, direction: str) -> Optional[Tuple[str, float, float]]:
    last = df_m1.iloc[-1]
    px = float(last["close"])
    bb_up, bb_dn, bb_mid = float(last["bb_up"]), float(last["bb_dn"]), float(last["bb_mid"])
    rsi = float(last["rsi"])
    if direction == "up" and px <= bb_dn and rsi < 30: return ("buy", px, bb_mid)
    if direction == "down" and px >= bb_up and rsi > 70: return ("sell", px, bb_mid)
    return None

def finalize_sl_tp(sym: str, side: str, entry_px: float) -> Tuple[float, float]:
    p = pip_size(sym)
    return (
        entry_px - SL_PIPS * p if side=="buy" else entry_px + SL_PIPS * p,
        entry_px + TP_PIPS * p if side=="buy" else entry_px - TP_PIPS * p
    )

def key_for(symbol: str, side: str, ts: pd.Timestamp) -> str:
    return f"{symbol}:{side}@{ts.isoformat()[:16]}"

def fetch_yf(symbol: str, interval: str, period: str) -> pd.DataFrame:
    t = yf.Ticker(symbol)
    df = t.history(interval=interval, period=period).reset_index().rename(
        columns={"Datetime":"time","Open":"open","High":"high","Low":"low","Close":"close","Date":"time"})
    df = df[["time","open","high","low","close"]]
    df["time"] = pd.to_datetime(df["time"])
    return df

def run_once_for_symbol(yf_symbol: str):
    try:
        mt5_symbol = SYMBOLS_MAP[yf_symbol]
        df15i = compute_indicators(fetch_yf(yf_symbol, "15m", "60d").tail(HISTORY_M15))
        dirn = trend_direction(df15i)
        if dirn is None: return
        df1i  = compute_indicators(fetch_yf(yf_symbol, "1m", "7d").tail(HISTORY_M1))
        sig = entry_signal(df1i, dirn)
        if sig is None: return
        side, entry_px, _ = sig
        ts = df1i.iloc[-1]["time"]
        k = key_for(mt5_symbol, side, pd.to_datetime(ts))
        if _last_signal_key.get(mt5_symbol) == k: return
        _last_signal_key[mt5_symbol] = k
        sl, tp = finalize_sl_tp(mt5_symbol, side, entry_px)
        msg = (
            f"⚡️ إشارة {('شراء' if side=='buy' else 'بيع')} {mt5_symbol}\n"
            f"الاتجاه (15م): {'صاعد' if dirn=='up' else 'هابط'}\n"
            f"الدخول (1م): {entry_px:.5f}\n"
            f"وقف الخسارة: {sl:.5f}\n"
            f"الهدف: {tp:.5f}\n"
            f"المصدر: Yahoo Finance — EMA(50/200)+Bollinger+RSI\n"
            f"التوقيت: {pd.to_datetime(ts).isoformat()}"
        )
        log(msg); send_telegram(msg)
    except Exception as e:
        log(f"[{yf_symbol}] Error: {e}")

def loop_worker():
    send_telegram("✅ تم تشغيل بوت توصيات المضاربة السريعة (Yahoo Finance).")
    log("Loop worker started.")
    while True:
        start = time.time()
        for s in YF_SYMBOLS: run_once_for_symbol(s)
        time.sleep(max(5, POLL_SECONDS - int(time.time() - start)))

app = FastAPI()
@app.get("/", response_class=PlainTextResponse) 
def root(): return "FX Quick Scalper Alerts — OK"
@app.get("/health", response_class=PlainTextResponse)
def health(): return "healthy"

def _ensure_thread():
    global _bg
    if "_bg" not in globals():
        _bg = threading.Thread(target=loop_worker, daemon=True); _bg.start()
_ensure_thread()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("2025:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=False)