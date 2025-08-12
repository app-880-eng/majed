# -*- coding: utf-8 -*-
# Forex Scalper (Paper Trading) — EMA20/EMA50 + RSI(14) + ATR(14)
# Runs on Render (FastAPI) + background loop every 5 minutes
# Telegram alerts enabled with fixed token/chat_id

import os, time, threading, json, math
from datetime import datetime, timedelta, timezone, date
import pandas as pd
import numpy as np
import yfinance as yf
from fastapi import FastAPI
from typing import Dict, Any

# -------- Config --------
PAIRS = [
    "EURUSD=X","GBPUSD=X","USDJPY=X","USDCHF=X","USDCAD=X",
    "AUDUSD=X","NZDUSD=X","EURJPY=X","GBPJPY=X","EURGBP=X"
]
INTERVAL = "5m"          # 1m أو 5m، الأفضل 5m على ياهو
LOOKBACK = 300           # عدد الشموع المحمّلة
EMA_FAST = 20
EMA_SLOW = 50
RSI_PERIOD = 14
ATR_PERIOD = 14
RISK_PER_TRADE = 0.01    # 1%
RR = 1.0                 # 1:1
MAX_TRADES_PER_DAY = 5
MAX_DAILY_DD = -0.03     # -3%
ATR_SL_BUFFER = 0.5
BREAKOUT_LOOKBACK = 10   # كسر قمة/قاع صغيرة
START_EQUITY = 10000.0

# -------- Telegram fixed --------
TELEGRAM_TOKEN = "8295831234:AAHgdvWal7E_5_hsjPmbPiIEra4LBDRjbgU"
TELEGRAM_CHAT_ID = "1820224574"

# -------- State --------
STATE_FILE = "state.json"
state = {
    "equity": START_EQUITY,
    "day": str(date.today()),
    "day_start_equity": START_EQUITY,
    "trades_today": 0,
    "open_positions": {},
    "log": []
}

def load_state():
    global state
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                s = json.load(f)
                state.update(s)
        except Exception:
            pass

def save_state():
    tmp = state.copy()
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(tmp, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def log(msg):
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts} UTC] {msg}"
    print(line, flush=True)
    state["log"].append(line)
    state["log"] = state["log"][-200:]
    save_state()

def send_telegram(text: str):
    import requests
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=10)
    except Exception:
        pass

# -------- Indicators --------
def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()

def rsi(series: pd.Series, length: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/length, adjust=False).mean()
    rs = avg_gain / (avg_loss.replace(0, np.nan))
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)

def atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low).abs(),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/length, adjust=False).mean()

# -------- Strategy --------
def fetch_df(pair: str) -> pd.DataFrame:
    df = yf.download(pair, period="7d", interval=INTERVAL, progress=False)
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.rename(columns=str.strip)
    df.dropna(inplace=True)
    df["EMA20"] = ema(df["Close"], EMA_FAST)
    df["EMA50"] = ema(df["Close"], EMA_SLOW)
    df["RSI"] = rsi(df["Close"], RSI_PERIOD)
    df["ATR"] = atr(df["High"], df["Low"], df["Close"], ATR_PERIOD)
    return df

def buy_signal(df: pd.DataFrame) -> bool:
    c = df.iloc[-1]
    prev = df.iloc[-2]
    if not (c.EMA20 > c.EMA50 and 40 < c.RSI < 70):
        return False
    recent_high = df["High"].iloc[-(BREAKOUT_LOOKBACK+1):-1].max()
    return prev.Close > recent_high

def sell_signal(df: pd.DataFrame) -> bool:
    c = df.iloc[-1]
    prev = df.iloc[-2]
    if not (c.EMA20 < c.EMA50 and 30 < c.RSI < 60):
        return False
    recent_low = df["Low"].iloc[-(BREAKOUT_LOOKBACK+1):-1].min()
    return prev.Close < recent_low

# -------- Paper Trading --------
def reset_day_if_needed():
    today = str(date.today())
    if state["day"] != today:
        state["day"] = today
        state["day_start_equity"] = state["equity"]
        state["trades_today"] = 0
        log("New trading day — counters reset.")

def daily_limits_ok() -> bool:
    if state["trades_today"] >= MAX_TRADES_PER_DAY:
        return False
    dd = (state["equity"] - state["day_start_equity"]) / state["day_start_equity"]
    return dd > MAX_DAILY_DD

def position_size(entry: float, sl: float) -> float:
    risk_money = state["equity"] * RISK_PER_TRADE
    dist = abs(entry - sl)
    if dist <= 0:
        return 0.0
    units = risk_money / dist
    return units

def open_trade(pair: str, side: str, entry: float, sl: float, tp: float):
    state["open_positions"][pair] = {
        "side": side,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "size": position_size(entry, sl),
        "time": datetime.utcnow().isoformat()
    }
    state["trades_today"] += 1
    log(f"OPEN {pair} {side} @ {entry:.5f} SL {sl:.5f} TP {tp:.5f}")
    send_telegram(f"OPEN {pair} {side} @ {entry:.5f} SL {sl:.5f} TP {tp:.5f}")

def close_trade(pair: str, price: float, reason: str):
    pos = state["open_positions"].pop(pair, None)
    if not pos: 
        return
    side = pos["side"]
    size = pos["size"]
    pnl = (price - pos["entry"]) * size if side == "BUY" else (pos["entry"] - price) * size
    state["equity"] += pnl
    log(f"CLOSE {pair} {side} @ {price:.5f} PnL={pnl:.2f} Eq={state['equity']:.2f} ({reason})")
    send_telegram(f"CLOSE {pair} {side} @ {price:.5f} PnL={pnl:.2f} Eq={state['equity']:.2f} ({reason})")

def evaluate_pair(pair: str):
    df = fetch_df(pair)
    if df.empty or len(df) < max(EMA_SLOW, RSI_PERIOD, ATR_PERIOD) + BREAKOUT_LOOKBACK + 5:
        return

    pos = state["open_positions"].get(pair)
    price = df.iloc[-1].Close

    if pos:
        if (pos["side"] == "BUY" and (price <= pos["sl"] or price >= pos["tp"])):
            reason = "TP" if price >= pos["tp"] else "SL"
            close_trade(pair, price, reason)
        elif (pos["side"] == "SELL" and (price >= pos["sl"] or price <= pos["tp"])):
            reason = "TP" if price <= pos["tp"] else "SL"
            close_trade(pair, price, reason)
        return

    if not daily_limits_ok():
        return

    if buy_signal(df):
        atr_val = df["ATR"].iloc[-1]
        entry = df["Close"].iloc[-1]
        swing_low = df["Low"].iloc[-(BREAKOUT_LOOKBACK+1):-1].min()
        sl = swing_low - (atr_val * ATR_SL_BUFFER)
        tp = entry + (entry - sl) * RR
        open_trade(pair, "BUY", entry, sl, tp)

    elif sell_signal(df):
        atr_val = df["ATR"].iloc[-1]
        entry = df["Close"].iloc[-1]
        swing_high = df["High"].iloc[-(BREAKOUT_LOOKBACK+1):-1].max()
        sl = swing_high + (atr_val * ATR_SL_BUFFER)
        tp = entry - (sl - entry) * RR
        open_trade(pair, "SELL", entry, sl, tp)

# -------- Scheduler --------
def loop():
    load_state()
    log("PaperTrader started.")
    while True:
        try:
            reset_day_if_needed()
            for p in PAIRS:
                evaluate_pair(p)
        except Exception as e:
            log(f"Loop error: {e}")
        save_state()
        time.sleep(300)

# -------- FastAPI --------
app = FastAPI()

@app.get("/")
def root() -> Dict[str, Any]:
    return {
        "status": "ok",
        "equity": state["equity"],
        "day": state["day"],
        "trades_today": state["trades_today"],
        "open_positions": state["open_positions"],
        "log_tail": state["log"][-10:]
    }

@app.get("/signals")
def signals():
    return {"open_positions": state["open_positions"], "log": state["log"][-50:]}

t = threading.Thread(target=loop, daemon=True)
t.start()