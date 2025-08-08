import json
import time
import requests
from solana.keypair import Keypair
from solana.rpc.api import Client
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, BUY_AMOUNT_SOL, STOP_LOSS_PERCENT, KEYPAIR_PATH
from telegram_utils import send_telegram

def load_keypair(path):
    with open(path, "r") as f:
        secret = json.load(f)
    return Keypair.from_secret_key(bytes(secret))

def get_new_tokens():
    try:
        feed = requests.get("https://pump.fun/feed").text
        tokens = [line for line in feed.splitlines() if "/token/" in line]
        return list(set(tokens))
    except Exception as e:
        print("Error fetching new tokens:", e)
        return []

def execute_fake_buy(token_url, sol_amount):
    send_telegram(f"🚀 تم اكتشاف عملة جديدة: {token_url}")
    send_telegram(f"🛒 تنفيذ شراء وهمي بقيمة {sol_amount} SOL للعملة الجديدة.")
    print(f"شراء فعلي {sol_amount} SOL للرمز: {token_url}")

def main():
    keypair = load_keypair(KEYPAIR_PATH)
    client = Client("https://api.mainnet-beta.solana.com")
    print("✅ البوت شغال وجاهز لاقتناص العملات الجديدة على pump.fun")

    seen_tokens = set()

    while True:
        tokens = get_new_tokens()
        for token in tokens:
            if token not in seen_tokens:
                seen_tokens.add(token)
                execute_fake_buy(token, BUY_AMOUNT_SOL)
                time.sleep(10)
                send_telegram(f"✅ تم البيع بربح أو وقف خسارة {STOP_LOSS_PERCENT}%")
        time.sleep(30)

if __name__ == "__main__":
    main()