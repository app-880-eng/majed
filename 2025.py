import time
import requests
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD

# ====== إعدادات التليجرام ======
TOKEN = "8295831234:AAHgdvWal7E_5_hsjPmbPiIEra4LBDRjbgU"
CHAT_ID = "1820224574"

def send_telegram(text: str):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"[Telegram Error] {e}")

# ====== بيانات Binance ======
def get_binance_data(symbol, interval='1h', limit=100):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        data = requests.get(url, timeout=10).json()
        df = pd.DataFrame(data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'qav', 'num_trades', 'tbbav', 'tbqav', 'ignore'
        ])
        df['close'] = df['close'].astype(float)
        df['volume'] = df['volume'].astype(float)
        return df
    except Exception as e:
        print(f"[Binance Data Error] {e}")
        return pd.DataFrame()

def analyze_binance(symbol, sent_set):
    try:
        df = get_binance_data(symbol)
        if df.empty: return

        rsi = RSIIndicator(df['close']).rsi()
        macd = MACD(df['close']).macd_diff()
        latest_rsi = rsi.iloc[-1]
        latest_macd = macd.iloc[-1]
        price = df['close'].iloc[-1]
        volume_now = df['volume'].iloc[-1]
        volume_prev = df['volume'].iloc[-2]

        # شروط مخففة حسب طلبك
        if latest_rsi < 50 and latest_macd > -0.05 and volume_now > volume_prev * 1.1:
            if symbol in sent_set:
                return
            sent_set.add(symbol)

            success = 65
            if latest_rsi < 40: success += 10
            if latest_macd > 0: success += 5
            profit_target = round(price * 1.02, 6)  # ربح 2%
            profit_percent = round((profit_target - price) / price * 100, 2)

            message = (
                f"🚀 *توصية من Binance*\n\n"
                f"💰 العملة: `{symbol}`\n"
                f"🎯 سعر الدخول: `${price}`\n"
                f"💸 الهدف للبيع: `${profit_target}`\n"
                f"📊 نسبة النجاح: `{success}%`\n"
                f"📈 نسبة الربح المتوقعة: `{profit_percent}%`\n"
                f"🔗 [رابط مباشر](https://www.binance.com/en/trade/{symbol})"
            )
            send_telegram(message)
    except Exception as e:
        print(f"[Analyze Binance Error] {e}")

def get_binance_pairs():
    try:
        url = "https://api.binance.com/api/v3/ticker/price"
        data = requests.get(url, timeout=10).json()
        return [item['symbol'] for item in data if item['symbol'].endswith("USDT") and float(item['price']) < 10]
    except Exception as e:
        print(f"[Binance Pairs Error] {e}")
        return []

# ====== بيانات Pump.fun ======
def fetch_pumpfun_data():
    try:
        url = "https://pump.fun/api/coins/recent"
        data = requests.get(url, timeout=10).json()
        return data.get('coins', [])
    except Exception as e:
        print(f"[Pump.fun API Error] {e}")
        return []

def analyze_pumpfun(coin, sent_set):
    try:
        coin_id = coin['id']
        if coin_id in sent_set:
            return
        sent_set.add(coin_id)

        symbol = coin['symbol']
        liquidity = float(coin['liquidity'] / 1e9)
        buys = coin['buyCount']
        price = float(coin['price'] / 1e9)
        url = f"https://pump.fun/{coin_id}"

        if liquidity >= 4 and buys >= 15:
            message = (
                f"🚀 *توصية من Pump.fun (Solana)*\n\n"
                f"💰 العملة: `${symbol}`\n"
                f"🔒 العقد: آمن ✅\n"
                f"💧 السيولة: `{round(liquidity, 2)} SOL`\n"
                f"🛒 عدد المشتريات: `{buys}`\n"
                f"📈 السعر الحالي: `{round(price, 6)} SOL`\n"
                f"🔗 [رابط مباشر للعملة]({url})"
            )
            send_telegram(message)
    except Exception as e:
        print(f"[Analyze Pump.fun Error] {e}")

# ====== تشغيل البوت ======
def run_bot():
    sent_binance = set()
    sent_pump = set()

    while True:
        print("🔁 فحص العملات...")

        binance_pairs = get_binance_pairs()
        for symbol in binance_pairs:
            analyze_binance(symbol, sent_binance)
            time.sleep(1)

        pump_coins = fetch_pumpfun_data()
        for coin in pump_coins:
            analyze_pumpfun(coin, sent_pump)
            time.sleep(1)

        print("✅ تم الفحص. بانتظار 10 دقائق...")
        time.sleep(600)

if __name__ == "__main__":
    run_bot()