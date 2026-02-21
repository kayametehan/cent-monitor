import requests
from bs4 import BeautifulSoup
import time
import os

# ── Ayarlar ──────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8575472491:AAGMQ1g34d9tS1TD0rYOw2s2r0WRlunIt8M")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "7097055241")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "120"))  # saniye

URL = "https://testcisia.it/calendario.php?tolc=cents&lingua=inglese"

UNAVAILABLE = {"POSTI ESAURITI", "ISCRIZIONI CONCLUSE", "ISCRIZIONI CHIUSE"}

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
    rows = soup.find_all("tr")

    found_any = False

    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 7:
            continue

        row_text = [c.get_text(strip=True) for c in cols]
        tip = row_text[0].upper() if row_text[0] else ""

        if "CENT@CASA" not in tip:
            continue

        universita = row_text[1]
        regione = row_text[2]
        citta = row_text[3]
        data_iscrizione = row_text[4]
        posti = row_text[5]
        stato = row_text[6].upper().strip()
        data_test = row_text[7] if len(row_text) > 7 else "?"

        # Eğer yer kapalı/dolu değilse → bildirim gönder
        is_available = not any(s in stato for s in UNAVAILABLE)

        key = f"{universita}|{data_test}"

        if is_available:
            found_any = True
            if key not in already_notified:
                already_notified.add(key)
                msg = (
                    "🟢 <b>CENT@CASA YER AÇILDI!</b>\n\n"
                    f"🏫 <b>{universita}</b>\n"
                    f"📍 {citta}, {regione}\n"
                    f"📅 Test: {data_test}\n"
                    f"📝 Kayıt kapanış: {data_iscrizione}\n"
                    f"💺 Kalan yer: {posti}\n"
                    f"📌 Durum: {stato}\n\n"
                    f"🔗 <a href='{URL}'>Hemen bak!</a>"
                )
                print(f"[!] YER AÇIK: {universita} - {data_test}")
                send_telegram(msg)
        else:
            # Tekrar kapanırsa listeden çıkar ki tekrar açılınca bildirim gelsin
            already_notified.discard(key)

    if not found_any:
        print("[·] CENT@CASA için açık yer yok.")


def main():
    print("=" * 50)
    print("  CENT@CASA Yer Takip Botu Başlatıldı")
    print(f"  Kontrol aralığı: {CHECK_INTERVAL} saniye")
    print("=" * 50)

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[HATA] TELEGRAM_BOT_TOKEN ve TELEGRAM_CHAT_ID env değişkenlerini ayarla!")
        return

    send_telegram("🤖 CENT@CASA Takip Botu aktif! Her 2 dakikada kontrol edilecek.")

    while True:
        try:
            check_seats()
        except Exception as e:
            print(f"[HATA] {e}")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
