import requests
from bs4 import BeautifulSoup
import time
import os

# ── Ayarlar ──────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8575472491:AAGMQ1g34d9tS1TD0rYOw2s2r0WRlunIt8M")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "7097055241")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "120"))  # saniye

URL = "https://testcisia.it/calendario.php?tolc=cents&lingua=inglese"

# İngilizce sayfadaki "yer yok" durumları
UNAVAILABLE = {"NOT LONGER AVAILABLE", "BOOKINGS CLOSED", "ENDED"}

already_notified = set()


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        r = requests.post(url, data=data, timeout=15)
        print(f"[Telegram] {r.status_code}")
    except Exception as e:
        print(f"[Telegram HATA] {e}")


def check_seats():
    print("[*] Sayfa kontrol ediliyor...")
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36"
        }
        resp = requests.get(URL, headers=headers, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"[HATA] Sayfa çekilemedi: {e}")
        return

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", {"id": "calendario"})
    if not table:
        print("[HATA] Tablo bulunamadı!")
        return

    rows = table.find_all("tr")
    found_any = False

    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 8:
            continue

        format_type = cols[0].get_text(strip=True).upper()

        if "CENT@HOME" not in format_type:
            continue

        university = cols[1].get_text(strip=True)
        region = cols[2].get_text(strip=True)
        city = cols[3].get_text(strip=True)
        booking_deadline = cols[4].get_text(strip=True)
        seats = cols[5].get_text(strip=True)
        state = cols[6].get_text(strip=True).upper()
        test_date = cols[7].get_text(strip=True)

        # Durum kontrol — yer kapalı mı?
        is_available = not any(s in state for s in UNAVAILABLE)

        key = f"{university}|{test_date}"

        if is_available:
            found_any = True
            if key not in already_notified:
                already_notified.add(key)
                msg = (
                    "🟢 <b>CENT@HOME YER AÇILDI!</b>\n\n"
                    f"🏫 <b>{university}</b>\n"
                    f"📍 {city}, {region}\n"
                    f"📅 Test: {test_date}\n"
                    f"📝 Son kayıt: {booking_deadline}\n"
                    f"💺 Kalan yer: {seats}\n"
                    f"📌 Durum: {state}\n\n"
                    f"🔗 <a href='{URL}'>Hemen kayıt ol!</a>"
                )
                print(f"[!] YER AÇIK: {university} - {test_date}")
                send_telegram(msg)
        else:
            # Tekrar kapanırsa listeden çıkar, tekrar açılınca bildirim gelsin
            already_notified.discard(key)

    if not found_any:
        print("[·] CENT@HOME için açık yer yok.")


def main():
    print("=" * 50)
    print("  CENT@HOME Yer Takip Botu Başlatıldı")
    print(f"  Kontrol aralığı: {CHECK_INTERVAL} saniye")
    print("=" * 50)

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[HATA] TELEGRAM_BOT_TOKEN ve TELEGRAM_CHAT_ID env ayarla!")
        return

    send_telegram("🤖 CENT@HOME Takip Botu aktif! Her 2 dakikada kontrol edilecek.")

    while True:
        try:
            check_seats()
        except Exception as e:
            print(f"[HATA] {e}")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
