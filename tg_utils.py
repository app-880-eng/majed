import requests
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

def send_telegram(text: str):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=10)
    except Exception as e:
        print("Telegram error:", e)
