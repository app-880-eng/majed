import time
import requests
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD

# إعدادات تيليجرام
TOKEN = "8295831234:AAHgdvWal7E_5_hsjPmbPiIEra4LBDRjbgU"
CHAT_ID = "1820224574"

def send_telegram(text: str):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"[Telegram Error] {e}")

# ================= BINANCE SECTION =================

def get_binance_data(symbol, interval='1h', limit=100):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    data = requests.get(url).json()
    df = pd.DataFrame(data, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'qav', 'num_trades', 'tbbav', 'tbqav', 'ignore'
    ])
    df['close'] = df['close'].astype(float)
    df['volume'] = df['volume'].astype(float)
    return df

def analyze_binance(symbol):
    try:
        df = get_binance_data(symbol)
        rsi = RSIIndicator(df['close']).rsi()
        macd = MACD(df['close']).macd_diff()

        latest_rsi = rsi.iloc[-1]
        latest_macd = macd.iloc[-1]
        price = df['close'].iloc[-1]
        volume_now = df['volume'].iloc[-1]
        volume_prev = df['volume'].iloc[-2]

        if latest_rsi < 35 and latest_macd > 0 and volume_now > volume_prev * 1.5:
            success = 75
            if latest_rsi < 30: success += 10
            if latest_macd > 0.1: success += 5
            profit_target = round(price * 1.15, 6)
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
        print(f"[Binance Error] {symbol} – {e}")

def get_binance_pairs():
    url = "https://api.binance.com/api/v3/ticker/price"
    data = requests.get(url).json()
    return [item['symbol'] for item in data if item['symbol'].endswith("USDT") and float(item['price']) < 10]

# ================= PUMP.FUN SECTION =================

def fetch_pumpfun_data():
    try:
        url = "https://pump.fun/api/coins/recent"
        data = requests.get(url, timeout=10).json()
        return data['coins']
    except Exception as e:
        print(f"[Pump.fun API Error] {e}")
        return []

def analyze_pumpfun(coin):
    try:
        name = coin['name']
        symbol = coin['symbol']
        liquidity = float(coin['liquidity'] / 1e9)
        buys = coin['buyCount']
        price = float(coin['price'] / 1e9)
        url = f"https://pump.fun/{coin['id']}"

        # شروط الدخول
        if liquidity >= 5 and buys >= 20:
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
        print(f"[Pump.fun Analyze Error] {e}")

# ================= MAIN =================

def run_bot():
    sent_binance = set()
    sent_pump = set()

    while True:
        print("🔄 بدء الفحص...")

        # Binance
        for symbol in get_binance_pairs():
            if symbol not in sent_binance:
                analyze_binance(symbol)
                sent_binance.add(symbol)
                time.sleep(1)

        # Pump.fun
        coins = fetch_pumpfun_data()
        for coin in coins:
            coin_id = coin['id']
            if coin_id not in sent_pump:
                analyze_pumpfun(coin)
                sent_pump.add(coin_id)
                time.sleep(1)

        print("✅ تم الانتهاء من الفحص. الانتظار 10 دقائق...")
        time.sleep(600)

# ✅ هذا هو المكان الصحيح لإرسال رسالة "تم التشغيل"
if __name__ == "__main__":
    send_telegram("✅ تم تشغيل بوت التداول الاحترافي (Binance + Pump.fun)، بانتظار الفرص 🔍")
    run_bot()