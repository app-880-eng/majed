import time
import json
import requests
from solana.rpc.api import Client
from solana.keypair import Keypair
from solana.transaction import Transaction
from solana.system_program import TransferParams, transfer
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, BUY_AMOUNT_SOL, STOP_LOSS_PERCENT, KEYPAIR_PATH

# ====== إعداد عميل سولانا ======
SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"
client = Client(SOLANA_RPC_URL)

# ====== تحميل بيانات المحفظة ======
with open(KEYPAIR_PATH, "r") as f:
    secret_key = json.load(f)
keypair = Keypair.from_secret_key(bytes(secret_key))

# ====== إرسال رسالة تيليجرام ======
def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"خطأ في إرسال تيليجرام: {e}")

# ====== تنفيذ أمر شراء ======
def buy_new_token():
    send_telegram("🚀 تم شراء العملة الجديدة بنجاح!")
    # هنا تضع كود الشراء من pump.fun أو المنصة المطلوبة

# ====== تنفيذ أمر بيع ======
def sell_token():
    send_telegram("💰 تم بيع العملة عند وصولها لوقف الخسارة أو الهدف.")

# ====== مراقبة العملات ======
def monitor_tokens():
    while True:
        try:
            # 🔍 منطق البحث عن عملة جديدة
            # إذا تم العثور على عملة جديدة
            buy_new_token()

            # مثال لوقف الخسارة
            price_drop = -25  # نسبة افتراضية كمثال
            if price_drop <= STOP_LOSS_PERCENT:
                sell_token()

        except Exception as e:
            print(f"خطأ في المراقبة: {e}")

        time.sleep(10)  # فاصل بين كل فحص

if __name__ == "__main__":
    send_telegram("✅ البوت بدأ العمل الآن.")
    monitor_tokens()