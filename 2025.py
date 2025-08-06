import os
import time
import requests
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD

# اقرأ القيم من Environment Variables
TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

assert TOKEN, "TOKEN env var is missing"
assert CHAT_ID, "CHAT_ID env var is missing"

def send_telegram(text):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": text}, timeout=15)
    except Exception as e:
        print(f"Telegram error: {e}")

def get_crypto_data(symbol):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol.upper()}USDT&interval=15m&limit=120"
    try:
        data = requests.get(url, timeout=20).json()
        if not isinstance(data, list) or len(data) == 0:
            return pd.DataFrame()
        df = pd.DataFrame(data, columns=[
            'timestamp','open','high','low','close','volume','c1','c2','c3','c4','c5','c6'
        ])
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        df.dropna(subset=['close'], inplace=True)
        return df
    except Exception as e:
        print(f"Fetch error {symbol}: {e}")
        return pd.DataFrame()

def analyze(symbol):
    df = get_crypto_data(symbol)
    if df.empty or len(df) < 35:
        print(f"No/low data for {symbol}")
        return
    try:
        rsi_val = RSIIndicator(df['close'], window=14).rsi().iloc[-1]
        macd_hist = MACD(df['close']).macd_diff().iloc[-1]
        price = float(df['close'].iloc[-1])
    except Exception as e:
        print(f"Indicators error {symbol}: {e}")
        return

    if rsi_val < 30 and macd_hist > 0:
        send_telegram(f"🚀 فرصة شراء {symbol} | السعر: {price:.6f} | RSI: {rsi_val:.2f} | MACD: {macd_hist:.4f}")
    else:
        print(f"{symbol} no signal. price={price:.6f} rsi={rsi_val:.2f} macdH={macd_hist:.4f}")

def main():
    send_telegram("✅ البوت تم تشغيله على Render بنجاح.")
    coins = ["BTC", "ETH", "XRP", "ADA", "DOGE", "TRX", "SHIB"]
    while True:
        for c in coins:
            analyze(c)
            time.sleep(2)
        time.sleep(60)

if __name__ == "__main__":
    main()