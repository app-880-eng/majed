import time
import requests
from solana.rpc.api import Client
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, RPC_URL, WALLET_PRIVATE_KEY

# إنشاء اتصال مع شبكة Solana
client = Client(RPC_URL)

# دالة إرسال رسالة إلى تيليجرام
def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"خطأ في إرسال الرسالة: {e}")

# فحص العملات الجديدة (pump.fun مثال)
def check_new_tokens():
    # مكان جلب بيانات العملات الجديدة
    # لازم تربط هنا API أو طريقة جلب البيانات من pump.fun
    # الكود هذا فقط مثال
    new_tokens = ["TokenA", "TokenB"]
    return new_tokens

# شراء العملة
def buy_token(token):
    # هنا تكتب كود الشراء باستخدام WALLET_PRIVATE_KEY
    send_telegram(f"تم شراء العملة: {token}")

# تشغيل البوت
if __name__ == "__main__":
    send_telegram("🚀 تم تشغيل البوت بنجاح!")
    while True:
        try:
            tokens = check_new_tokens()
            for token in tokens:
                buy_token(token)
            time.sleep(10)  # كل 10 ثواني يفحص
        except Exception as e:
            send_telegram(f"حدث خطأ: {e}")
            time.sleep(5)