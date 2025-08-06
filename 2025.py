import requests
import time
import feedparser
from bs4 import BeautifulSoup
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD
from datetime import datetime

# إعدادات التليجرام
TOKEN = '8295831234:AAHgdvWal7E_5_hsjPmbPiIEra4LBDRjbgU'
CHAT_ID = '1820224574'

def send_telegram_message(text):
    url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
    payload = {'chat_id': CHAT_ID, 'text': text, 'parse_mode': 'Markdown'}
    requests.post(url, data=payload)

def get_crypto_data(symbol):
    url = f'https://api.binance.com/api/v3/klines?symbol={symbol.upper()}USDT&interval=15m&limit=100'
    data = requests.get(url).json()
    df = pd.DataFrame(data, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume', '_', '__', '___', '____', '_____', '______'
    ])
    df['close'] = df['close'].astype(float)
    return df

def analyze(symbol):
    df = get_crypto_data(symbol)
    rsi = RSIIndicator(df['close'], window=14).rsi().iloc[-1]
    macd = MACD(df['close']).macd_diff().iloc[-1]
    price = df['close'].iloc[-1]
    
    if rsi < 30 and macd > 0:
        send_telegram_message(f"🚀 فرصة شراء: {symbol} السعر: {price} RSI: {rsi:.2f} MACD: {macd:.2f}")

coins = ["DOGE", "XRP", "ADA", "SHIB", "TRX"]

while True:
    for coin in coins:
        analyze(coin)
    time.sleep(3600)
