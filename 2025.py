# bot: pump.fun sniper (fixed) — لا تحذف هذا السطر، مجرد تعليق

import re
import json
import time
import requests
from solana.keypair import Keypair
from solana.rpc.api import Client
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, BUY_AMOUNT_SOL, STOP_LOSS_PERCENT, KEYPAIR_PATH
from tg_utils import send_telegram

RPC_URL = "https://api.mainnet-beta.solana.com"

def load_keypair(path: str) -> Keypair:
    with open(path, "r") as f:
        secret = json.load(f)
    return Keypair.from_secret_key(bytes(secret))

def get_new_tokens() -> list[str]:
    """
    نجلب صفحة feed من pump.fun ونستخرج روابط التوكنات الجديدة.
    """
    try:
        html = requests.get("https://pump.fun/feed", timeout=15).text
        # روابط بالشكل: https://pump.fun/token/<MINT>
        return list(set(re.findall(r"https://pump\.fun/token/[A-Za-z0-9]+", html)))
    except Exception as e:
        print("Error fetching new tokens:", e)
        return []

def is_safe_token(url: str) -> bool:
    # فلترة مبدئية بسيطة — تقدر تطورها لاحقًا
    return url.startswith("https://pump.fun/token/")

def buy_token_placeholder(keypair: Keypair, token_url: str, sol_amount: float):
    """
    هذا مجرد Placeholder. الشراء الحقيقي من عقد pump.fun يحتاج دمج تعامل عقد فعلي.
    الآن فقط يرسل إشعار ويطبع للمراقبة.
    """
    send_telegram(f"🛒 شراء (تجريبي) بقيمة {sol_amount} SOL\n{token_url}")
    print(f"[BUY-PLACEHOLDER] {sol_amount} SOL -> {token_url}")

def main():
    send_telegram("✅ تم تشغيل البوت: Pump.fun watcher (fixed)")
    client = Client(RPC_URL)  # مُستخدم لاحقًا للشراء الحقيقي
    keypair = load_keypair(KEYPAIR_PATH)

    seen = set()
    while True:
        try:
            tokens = get_new_tokens()
            for t in tokens:
                if t in seen:
                    continue
                seen.add(t)

                if not is_safe_token(t):
                    continue

                # إشعار اكتشاف
                send_telegram(f"🚀 تم اكتشاف توكن جديد:\n{t}")

                # تنفيذ شراء تجريبي الآن (استبدله لاحقًا بشراء حقيقي)
                buy_token_placeholder(keypair, t, BUY_AMOUNT_SOL)

            time.sleep(20)
        except Exception as e:
            send_telegram(f"⚠️ خطأ أثناء التشغيل: {e}")
            time.sleep(30)

if __name__ == "__main__":
    main()