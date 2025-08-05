
import requests
import time

TOKEN = "8295831234:AAHgdvWal7E_5_hsjPmbPiIEra4LBDRjbgU"
CHAT_ID = "1820224574"

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {'chat_id': CHAT_ID, 'text': text}
    requests.post(url, data=payload)

if __name__ == "__main__":
    send_telegram_message("✅ البوت يعمل الآن على Render!")
    while True:
        time.sleep(60)
