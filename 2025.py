# Pump.fun Sniper via Jupiter — BUY & SELL (startup ping)

import re, time, json, base64, requests
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

SOL_MINT = "So11111111111111111111111111111111111111112"
JUP_QUOTE = "https://quote-api.jup.ag/v6/quote"
JUP_SWAP  = "https://quote-api.jup.ag/v6/swap"
FEED_URL  = "https://pump.fun/feed"

client = Client(RPC_URL)

def send_telegram(msg: str):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=10)
    except Exception as e:
        print("Telegram error:", e)

def load_keypair(path: str) -> Keypair:
    with open(path, "r") as f:
        sk = json.load(f)
    return Keypair.from_secret_key(bytes(sk))

def get_new_token_mints():
    try:
        html = requests.get(FEED_URL, timeout=15).text
        return list(dict.fromkeys(re.findall(r"https://pump\.fun/token/([A-Za-z0-9]+)", html)))
    except Exception as e:
        print("feed error:", e); return []

def jup_quote(input_mint, output_mint, amount_lamports, slippage_bps=300):
    r = requests.get(JUP_QUOTE, params={
        "inputMint": input_mint, "outputMint": output_mint,
        "amount": str(amount_lamports), "slippageBps": str(slippage_bps),
        "onlyDirectRoutes": "false"
    }, timeout=20)
    r.raise_for_status()
    data = r.json()
    return data["data"][0] if data.get("data") else None

def jup_swap(quote_resp, user_pubkey, wrap_and_unwrap_sol=True):
    r = requests.post(JUP_SWAP, json={
        "quoteResponse": quote_resp,
        "userPublicKey": user_pubkey,
        "wrapAndUnwrapSol": wrap_and_unwrap_sol,
        "prioritizationFeeLamports": "auto"
    }, timeout=25)
    r.raise_for_status()
    return r.json().get("swapTransaction")

def send_signed_txn(swap_tx_b64: str) -> str:
    raw = base64.b64decode(swap_tx_b64)
    tx = Transaction.deserialize(raw)
    tx.sign(WALLET)
    sig = client.send_transaction(tx, WALLET, opts=TxOpts(skip_preflight=True, preflight_commitment=Confirmed))["result"]
    client.confirm_transaction(sig)
    return sig

def buy_token(mint: str, sol_amount: float):
    lamports = int(sol_amount * 1_000_000_000)
    q = jup_quote(SOL_MINT, mint, lamports)
    if not q or int(q.get("outAmount", "0")) == 0: return None
    sig = send_signed_txn(jup_swap(q, str(WALLET.public_key)))
    return {"sig": sig, "inAmount": lamports, "outAmount": int(q["outAmount"]), "price": lamports / max(1, int(q["outAmount"]))}

def sell_token(mint: str, token_amount_raw: int):
    q = jup_quote(mint, SOL_MINT, token_amount_raw)
    if not q or int(q.get("outAmount", "0")) == 0: return None
    return send_signed_txn(jup_swap(q, str(WALLET.public_key)))

def monitor_position(mint: str, entry_price: float, amount_tokens: int):
    send_telegram(f"📈 تتبع {mint}\nسعر الدخول التقريبي: {entry_price:.10f} SOL/Token")
    while True:
        try:
            q = jup_quote(mint, SOL_MINT, amount_tokens)
            if not q: time.sleep(8); continue
            out_sol = int(q["outAmount"]) / 1_000_000_000
            px_now  = (entry_price if amount_tokens==0 else (amount_tokens/ max(out_sol,1e-12)))**-1  # تقريب
            change  = ((px_now - entry_price) / entry_price) * 100

            if change <= STOP_LOSS_PERCENT:
                sig = sell_token(mint, amount_tokens)
                send_telegram(f"🛑 وقف خسارة {change:.2f}%\nTx: {sig}"); return
            if change >= TAKE_PROFIT_PERCENT:
                sig = sell_token(mint, amount_tokens)
                send_telegram(f"✅ جني أرباح {change:.2f}%\nTx: {sig}"); return
            time.sleep(8)
        except Exception as e:
            send_telegram(f"⚠️ monitor error: {e}"); time.sleep(10)

def run():
    global WALLET
    try:
        WALLET = load_keypair(KEYPAIR_PATH)
    except Exception as e:
        send_telegram(f"❌ فشل تحميل keypair: {e}")
        raise

    send_telegram("✅ تشغيل البوت (Jupiter mode) — بدأنا الرصد")
    seen = set()

    while True:
        try:
            for mint in get_new_token_mints():
                if mint in seen: continue
                seen.add(mint)
                send_telegram(f"🚀 توكن جديد: https://pump.fun/token/{mint}")

                res = buy_token(mint, BUY_AMOUNT_SOL)
                if not res: 
                    send_telegram("⚠️ فشل الشراء (quote أو swap غير صالح)"); 
                    continue

                send_telegram(f"🛒 اشترينا {BUY_AMOUNT_SOL} SOL\nTokens≈ {res['outAmount']}\nTx: {res['sig']}")
                monitor_position(mint, res["price"], res["outAmount"])

            time.sleep(15)
        except Exception as e:
            send_telegram(f"⚠️ runtime error: {e}")
            time.sleep(15)

if __name__ == "__main__":
    run()