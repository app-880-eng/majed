# Telegram Crypto Picks — Every 12h

## الخطوات
1) ارفع هذه الملفات إلى مستودع GitHub جديد.
2) في Render: New → Web Service → اربط المستودع.
3) Build: `pip install -r requirements.txt`
4) Start: `uvicorn 2025:app --host 0.0.0.0 --port $PORT`
5) أضف متغيرات البيئة:
   - `TELEGRAM_TOKEN` = توكن بوتك
   - `TELEGRAM_CHAT_ID` = رقم الـ ID في تليجرام
6) Deploy. أول ما يشتغل البوت، بيرسل رسالة “✅ تم تشغيل البوت…”.
7) بعدها توصية كل 12 ساعة تلقائيًا.

> لضبط وقت البداية (مثلاً تبدأ أول توصية 08:00 الكويت)، شغّل الخدمة ثم من لوحة Render اضغط **Manual Deploy** قريبًا من الوقت المطلوب؛ الجدول يتكرر كل 12 ساعة من لحظة التشغيل.