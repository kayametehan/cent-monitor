#!/usr/bin/env python3
"""
CEnT@CASA Telegram Monitör
Sayfa her dakika kontrol edilir, yer açılırsa bildirim gelir.
"""

import time
import logging
import requests
from bs4 import BeautifulSoup
from config import BOT_TOKEN, CHAT_ID, URL, INTERVAL, ONLY_CASA, REPEAT

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

KAPALI = {"POSTI ESAURITI", "ISCRIZIONI CONCLUSE", "ISCRIZIONI CHIUSE"}
bildirildi = set()


def telegram(mesaj):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": mesaj, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=10,
        )
    except Exception as e:
        log.error("Telegram hatası: %s", e)


def sayfayi_cek():
    try:
        r = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        return r.text
    except Exception as e:
        log.error("Sayfa hatası: %s", e)
        return None


def satirlari_bul(html):
    soup = BeautifulSoup(html, "lxml")
    satirlar = []
    for tr in soup.find_all("tr"):
        td = [c.get_text(strip=True) for c in tr.find_all("td")]
        if len(td) < 8:
            continue
        tip = td[0].upper()
        if "CENT@CASA" not in tip and "CENT@UNI" not in tip:
            continue
        if ONLY_CASA and "CENT@CASA" not in tip:
            continue
        satirlar.append({
            "uni": td[1], "sehir": td[3], "kayit_bitis": td[4],
            "yer": td[5], "durum": td[6], "sinav": td[7],
        })
    return satirlar


def kontrol():
    html = sayfayi_cek()
    if not html:
        return

    satirlar = satirlari_bul(html)
    log.info("%d satır bulundu", len(satirlar))

    for s in satirlar:
        anahtar = f"{s['uni']}|{s['sinav']}"

        if s["durum"].upper().strip() not in KAPALI and anahtar not in bildirildi:
            mesaj = (
                "🚨🚨🚨 <b>YER AÇILDI!</b> 🚨🚨🚨\n\n"
                f"🏫 <b>{s['uni']}</b>\n"
                f"📍 {s['sehir']}\n"
                f"📅 Sınav: <b>{s['sinav']}</b>\n"
                f"📝 Kayıt bitiş: {s['kayit_bitis']}\n"
                f"💺 Yer: <b>{s['yer']}</b>\n"
                f"📌 Durum: <b>{s['durum']}</b>\n\n"
                f"🔗 <a href=\"{URL}\">HEMEN KAYIT OL!</a>"
            )
            for _ in range(REPEAT):
                telegram(mesaj)
                time.sleep(5)
            bildirildi.add(anahtar)
            log.info("🎉 YER AÇIK: %s", s["uni"])


def main():
    log.info("Bot başladı — %d saniyede bir kontrol", INTERVAL)
    telegram(f"🤖 <b>Bot aktif!</b>\nHer {INTERVAL}sn kontrol ediliyor.\n🔗 <a href=\"{URL}\">Sayfa</a>")

    while True:
        kontrol()
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
