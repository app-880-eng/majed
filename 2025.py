# Pump.fun Sniper via Jupiter — BUY & SELL

import re
import os
import time
import json
import base64
import requests
from decimal import Decimal
from typing import Optional

from solana.rpc.api import Client
from solana.keypair import Keypair
from solana.transaction import Transaction
from solana.rpc.types import TxOpts
from solana.rpc.commitment import Confirmed

from config import (
    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
    BUY_AMOUNT_SOL, STOP_LOSS_PERCENT, TAKE_PROFIT_PERCENT,
    KEYPAIR_PATH, RPC_URL
)

# ----- إعدادات عامة -----
SOL_MINT = "So11111111111111111111111111111111111111112"
JUP_QUOTE = "https://quote-api.jup.ag/v6/quote"
JUP_SWAP  = "https://quote-api.jup.ag/v6/swap"
FEED_URL  = "https://pump.fun/feed"

client = Client(RPC_URL)

# ----- تيليجرام -----
def send_telegram(msg: str):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=10)
    except Exception as e:
        print("Telegram error:", e)

# ----- تحميل المحفظة -----
def load_keypair(path: str) -> Keypair:
    with open(path, "r") as f:
        sk = json.load(f)
    return Keypair.from_secret_key(bytes(sk))

WALLET = load_keypair(KEYPAIR_PATH)

# ----- جلب توكنات جديدة من pump.fun -----
def get_new_token_mints() -> list[str]:
    try:
        html = requests.get(FEED_URL, timeout=15).text
        # روابط بالشكل https://pump.fun/token/<MINT>
        mints = re.findall(r"https://pump\.fun/token/([A-Za-z0-9]+)", html)
        return list(dict.fromkeys(mints))  # remove dups مع الحفاظ على الترتيب
    except Exception as e:
        print("feed error:", e)
        return []

# ----- دوال Jupiter (Quote + Swap) -----
def jup_quote(input_mint: str, output_mint: str, amount_lamports: int, slippage_bps: int = 300):
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount_lamports),
        "slippageBps": str(slippage_bps),
        "onlyDirectRoutes": "false"
    }
    r = requests.get(JUP_QUOTE, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    # أفضل مسار أول عنصر عادة
    return data["data"][0] if data.get("data") else None

def jup_swap(quote_resp: dict, user_pubkey: str, wrap_and_unwrap_sol: bool = True) -> Optional[str]:
    payload = {
        "quoteResponse": quote_resp,
        "userPublicKey": user_pubkey,
        "wrapAndUnwrapSol": wrap_and_unwrap_sol,
        "prioritizationFeeLamports": "auto"
    }
    r = requests.post(JUP_SWAP, json=payload, timeout=25)
    r.raise_for_status()
    data = r.json()
    return data.get("swapTransaction")  # base64

def send_signed_txn(swap_tx_b64: str) -> str:
    # استرجاع المعاملة الموقّعة من Jupiter وتوقيعها بالمحفظة
    raw = base64.b64decode(swap_tx_b64)
    tx = Transaction.deserialize(raw)
    tx.sign(WALLET)
    sig = client.send_transaction(tx, WALLET, opts=TxOpts(skip_preflight=True, preflight_commitment=Confirmed))["result"]
    # تأكيد سريع
    client.confirm_transaction(sig)
    return sig

# ----- شراء عبر Jupiter (SOL -> TOKEN) -----
def buy_token(mint: str, sol_amount: float) -> Optional[dict]:
    lamports = int(sol_amount * 1_000_000_000)
    q = jup_quote(SOL_MINT, mint, lamports)
    if not q or int(q.get("outAmount", "0")) == 0:
        return None
    swap_tx = jup_swap(q, str(WALLET.public_key))
    sig = send_signed_txn(swap_tx)
    return {
        "sig": sig,
        "inAmount": lamports,
        "outAmount": int(q["outAmount"]),
        "price": lamports / max(1, int(q["outAmount"]))  # SOL per token (approx)
    }

# ----- بيع عبر Jupiter (TOKEN -> SOL) -----
def sell_token(mint: str, token_amount_raw: int) -> Optional[str]:
    q = jup_quote(mint, SOL_MINT, token_amount_raw)
    if not q or int(q.get("outAmount", "0")) == 0:
        return None
    swap_tx = jup_swap(q, str(WALLET.public_key))
    sig = send_signed_txn(swap_tx)
    return sig

# ----- تتبع مركز واحد ووقف الخسارة/جني الربح -----
def monitor_position(mint: str, entry_price: float, amount_tokens: int):
    """
    entry_price = SOL per token (تقريب)
    """
    send_telegram(f"📈 بدأ تتبع {mint}\nسعر الدخول (تقريب): {entry_price:.10f} SOL")

    while True:
        try:
            # اسأل الجهة المعاكسة (بيع التوكن -> SOL) لتقدير السعر الحالي
            q = jup_quote(mint, SOL_MINT, amount_tokens)
            if not q: 
                time.sleep(8); 
                continue

            out_sol = int(q["outAmount"]) / 1_000_000_000
            px_now  = (1.0 / max(out_sol / (amount_tokens or 1), 1e-18))  # تقريب, ما نريد قسمة صفر
            change  = ((entry_price - px_now) / entry_price) * 100 * -1  # % الربح/الخسارة

            # قرارات:
            if change <= STOP_LOSS_PERCENT:  # سالب
                sig = sell_token(mint, amount_tokens)
                send_telegram(f"🛑 وقف خسارة {change:.2f}%\nمعاملة: {sig}")
                return

            if change >= TAKE_PROFIT_PERCENT:
                sig = sell_token(mint, amount_tokens)
                send_telegram(f"✅ جني أرباح {change:.2f}%\nمعاملة: {sig}")
                return

            time.sleep(8)
        except Exception as e:
            print("monitor err:", e)
            time.sleep(10)

# ----- التشغيل الرئيسي -----
def run():
    send_telegram("✅ تشغيل البوت (Jupiter mode)")
    seen = set()

    while True:
        try:
            mints = get_new_token_mints()
            for mint in mints:
                if mint in seen:
                    continue
                seen.add(mint)

                # شراء
                res = buy_token(mint, BUY_AMOUNT_SOL)
                if not res:
                    continue

                sig = res["sig"]
                out_amt = res["outAmount"]
                entry_price = res["price"]

                send_telegram(
                    f"🛒 تم الشراء\nMint: {mint}\n"
                    f"قيمة الشراء: {BUY_AMOUNT_SOL} SOL\n"
                    f"توكنات مستلمة (تقريب): {out_amt}\n"
                    f"معاملة: {sig}"
                )

                # تتبع المركز وبيع تلقائي
                monitor_position(mint, entry_price, out_amt)

            time.sleep(15)
        except Exception as e:
            send_telegram(f"⚠️ خطأ أثناء التشغيل: {e}")
            time.sleep(15)

if __name__ == "__main__":
    run()