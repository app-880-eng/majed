# لا تُعدّ جزءًا من التطبيق إن ما تبي، بس للعلم: 
# 1) ارفع الملفات إلى GitHub (main.py / requirements.txt / Procfile).
# 2) على Render: أنشئ خدمة Web من المستودع، Build Command: pip install -r requirements.txt ،
#    Start Command: uvicorn main:app --host 0.0.0.0 --port $PORT
# البوت يرسل رسالة تشغيل فور الإقلاع، ثم يفحص كل ساعة ويرسل توصية واحدة يوميًا على الأقل.
