# Trading Suite (Signals Only)
- صفقة يومية واحدة (هدف +2%) لعملات Binance فقط
- تنبيهات Sniper من `data/manual_sniper.json`
- تنبيهات Whales من `data/whales_signals.csv`
- بدون ربط بمحفظة — إشعارات فقط

## التشغيل
1) عدّل أعلى `2025.py` وضع TELEGRAM_TOKEN و CHAT_ID.
2) ثبّت المتطلبات:
   ```bash
   pip install -r requirements.txt