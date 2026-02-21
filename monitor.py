#!/usr/bin/env python3
"""
CEnT@HOME Telegram Monitör
Her iki dilde (EN + IT) kontrol eder, yer açılırsa bildirim gönderir.
"""

import time
import logging
import threading
import requests
from flask import Flask
from bs4 import BeautifulSoup
from config import BOT_TOKEN, CHAT_ID, URLs, INTERVAL, ONLY_HOME, REPEAT

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

# Açık durum anahtar kelimeleri — EN ve IT
ACIK_KEYS = ["AVAILABLE SEATS", "ISCRIVITI", "POSTI DISPONIBILI"]
# HOME tipi
HOME_KEYS = ["CENT@HOME"]

bildirildi = set()

# ── Flask keep-alive (Render free tier uyumasın) ──
app = Flask(__name__)

@app.route("/")
def health():
    return "OK", 200

def keep_alive():
    app.run(host="0.0.0.0", port=10000, debug=False, use_reloader=False)


def telegram(mesaj):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": mesaj, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=10,
        )
    except Exception as e:
        log.error("Telegram hatası: %s", e)


def sayfayi_cek(url):
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        return r.text
    except Exception as e:
        log.error("Sayfa hatası (%s): %s", url, e)
        return None


def satirlari_bul(html):
    soup = BeautifulSoup(html, "lxml")
    satirlar = []
    for tr in soup.find_all("tr"):
        td = [c.get_text(strip=True) for c in tr.find_all("td")]
        if len(td) < 8:
            continue
        tip = td[0].upper()
        is_home = any(k in tip for k in HOME_KEYS)
        is_uni = "CENT@UNI" in tip
        if not is_home and not is_uni:
            continue
        if ONLY_HOME and not is_home:
            continue
        satirlar.append({
            "uni": td[1], "sehir": td[3], "kayit_bitis": td[4],
            "yer": td[5], "durum": td[6], "sinav": td[7],
        })
    return satirlar


def durum_acik(durum_text):
    """Durum metninin açık olup olmadığını kontrol et (EN veya IT)"""
    d = durum_text.upper().strip()
    return any(k in d for k in ACIK_KEYS)


def kontrol():
    tum_satirlar = []
    for url in URLs:
        html = sayfayi_cek(url)
        if not html:
            continue
        satirlar = satirlari_bul(html)
        log.info("%s → %d satır", "EN" if "inglese" in url else "IT", len(satirlar))
        tum_satirlar.extend(satirlar)

    for s in tum_satirlar:
        anahtar = f"{s['uni']}|{s['sinav']}"

        if durum_acik(s["durum"]) and anahtar not in bildirildi:
            mesaj = (
                "🚨🚨🚨 <b>YER AÇILDI!</b> 🚨🚨🚨\n\n"
                f"🏫 <b>{s['uni']}</b>\n"
                f"📍 {s['sehir']}\n"
                f"📅 Sınav: <b>{s['sinav']}</b>\n"
                f"📝 Kayıt bitiş: {s['kayit_bitis']}\n"
                f"💺 Yer: <b>{s['yer']}</b>\n"
                f"📌 Durum: <b>{s['durum']}</b>\n\n"
                f"🔗 <a href=\"{URLs[0]}\">HEMEN KAYIT OL!</a>"
            )
            for _ in range(REPEAT):
                telegram(mesaj)
                time.sleep(5)
            bildirildi.add(anahtar)
            log.info("🎉 YER AÇIK: %s", s["uni"])


def main():
    # Flask'ı arka planda başlat (Render ping'e cevap versin)
    threading.Thread(target=keep_alive, daemon=True).start()

    log.info("Bot başladı — %d saniyede bir kontrol (EN + IT)", INTERVAL)
    telegram(f"🤖 <b>Bot aktif!</b>\nHer {INTERVAL}sn EN+IT kontrol.\n🔗 <a href=\"{URLs[0]}\">Sayfa</a>")

    while True:
        kontrol()
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
