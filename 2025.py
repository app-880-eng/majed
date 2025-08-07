import time
import requests
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD

# ====== إعدادات التليجرام ======
TOKEN = "8295831234:AAHgdvWal7E_5_hsjPmbPiIEra4LBDRjbgU"
CHAT_ID = "1820224574"

def log(msg: str):
    print(msg, flush=True)

def send_telegram(text: str):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": text}
        requests.post(url, data=payload, timeout=15)
    except Exception as e:
        log(f"Telegram error: {e}")

def get_crypto_data(symbol: str, interval: str = '1h', limit: int = 100):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    response = requests.get(url)
    data = response.json()
    df = pd.DataFrame(data, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'num_trades',
        'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
    ])
    df['close'] = df['close'].astype(float)
    df['volume'] = df['volume'].astype(float)
    return df

def check_entry(symbol):
    try:
        df = get_crypto_data(symbol)
        if len(df) < 50:
            return

        rsi = RSIIndicator(df['close'], window=14).rsi()
        macd = MACD(df['close']).macd_diff()

        latest_rsi = rsi.iloc[-1]
        latest_macd = macd.iloc[-1]
        volume = df['volume'].iloc[-1]
        volume_prev = df['volume'].iloc[-2]

        if latest_rsi < 35 and latest_macd > 0 and volume > volume_prev * 1.5:
            message = (
                f"🚨 *صفقة محتملة للمضاربة اليومية:*\n\n"
                f"📉 *العملة:* `{symbol}`\n"
                f"📊 RSI: `{round(latest_rsi, 2)}`\n"
                f"📈 MACD صاعد: ✅\n"
                f"🔊 حجم التداول مرتفع: ✅\n\n"
                f"[رابط Binance](https://www.binance.com/en/trade/{symbol})"
            )
            send_telegram(message)
            log(f"✅ Entry signal for {symbol}")
    except Exception as e:
        log(f"Error for {symbol}: {e}")

def get_usdt_pairs_under_1usd():
    url = "https://api.binance.com/api/v3/ticker/price"
    data = requests.get(url).json()
    pairs_under_1 = []
    for item in data:
        try:
            if item['symbol'].endswith('USDT') and float(item['price']) < 1.0:
                pairs_under_1.append(item['symbol'])
        except:
            continue
    return pairs_under_1

def main():
    sent = set()
    while True:
        symbols = get_usdt_pairs_under_1usd()
        for symbol in symbols:
            if symbol not in sent:
                check_entry(symbol)
                sent.add(symbol)
                time.sleep(2)
        log("✅ تم فحص جميع العملات تحت 1 دولار.")
        time.sleep(600)  # كل 10 دقائق

if __name__ == "__main__":
    send_telegram("✅ تم تشغيل البوت بنجاح، بانتظار الفرص 🔍")
    main()