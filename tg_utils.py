# -*- coding: utf-8 -*-
import requests

def send_telegram(token: str, chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}, timeout=15)