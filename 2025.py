import time
import requests
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD

# ====== إعدادات التليجرام ======
TOKEN = "8295831234:AAHgdvWal7E_5_hsjPmbPiIEra4LBDRjbgU"  # ضع التوكن هنا
CHAT_ID = "1820224574"  # ضع الـ ID هنا

# طباعة فورية للّوج
def log(msg: str):
    print(msg, flush=True)

# ====== إرسال رسالة تيليجرام ======
def send_telegram(text: str):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": text}
        requests.post(url, data=payload, timeout=15)
    except Exception as e:
        log(f"Telegram error: {e}")

# ====== جلب بيانات Binance ======
def get_crypto_data(symbol: str, interval: str = "15m", limit: int = 150) -> pd.DataFrame:
    url = (
        f"https://api.binance.com/api/v3/klines"
        f"?symbol={symbol.upper()}USDT&interval={interval}&limit={limit}"
    )
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        data = r.json()

        cols = [
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "number_of_trades",
            "taker_buy_base", "taker_buy_quote", "ignore"
        ]
        df = pd.DataFrame(data, columns=cols)[["open", "high", "low", "close", "volume"]]

        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")

        df.dropna(subset=["close"], inplace=True)
        return df

    except Exception as e:
        log(f"Fetch error {symbol}: {e}")
        return pd.DataFrame()

# ====== تحليل المؤشرات ======
def analyze(symbol: str):
    df = get_crypto_data(symbol)
    if df.empty or len(df) < 35:
        log(f"⚠️ No or low data for {symbol}")
        return

    try:
        rsi_val = RSIIndicator(df["close"], window=14).rsi().iloc[-1]
        macd_hist = MACD(df["close"]).macd_diff().iloc[-1]
        price = float(df["close"].iloc[-1])
        log(f"{symbol} => price={price}, RSI={rsi_val:.2f}, MACD_H={macd_hist:.4f}")
    except Exception as e:
        log(f"Indicators error {symbol}: {e}")
        return

    if rsi_val < 70 and macd_hist > -1:
        log(f"✅ Signal found for {symbol}")
        send_telegram(
            f"🚀 فرصة شراء {symbol}\n"
            f"السعر: {price}\nRSI: {rsi_val:.2f}\nMACD: {macd_hist:.4f}"
        )
    else:
        log(f"❌ No signal for {symbol}")

# ====== التشغيل ======
def main():
    log("🚀 Starting bot on Render...")
    send_telegram("✅ تم تشغيل البوت على Render")

    coins = ["BTC", "ETH", "XRP", "ADA", "DOGE", "TRX", "SHIB", "BCH", "BUN"]

    while True:
        log("🔍 Checking coins...")
        for c in coins:
            analyze(c)
            time.sleep(2)
        log("⏳ Waiting 60 seconds before next check...")
        time.sleep(60)

if __name__ == "__main__":
    main()