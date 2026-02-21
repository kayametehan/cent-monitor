import requests
from bs4 import BeautifulSoup
import threading
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ── Ayarlar ──────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8575472491:AAGMQ1g34d9tS1TD0rYOw2s2r0WRlunIt8M")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "7097055241")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "120"))  # saniye

URL = "https://testcisia.it/calendario.php?tolc=cents&lingua=inglese"

UNAVAILABLE = {"NOT LONGER AVAILABLE", "BOOKINGS CLOSED", "ENDED"}

already_notified = set()
monitoring = True  # takip açık/kapalı


# ── Ana Menü ─────────────────────────────────────────────
def main_menu():
    keyboard = [
        [InlineKeyboardButton("🔍 Şimdi Kontrol Et", callback_data="check")],
        [
            InlineKeyboardButton("▶️ Başlat", callback_data="start"),
            InlineKeyboardButton("⏸ Durdur", callback_data="stop"),
        ],
        [InlineKeyboardButton("📊 Durum", callback_data="status")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ── Site Kontrol ─────────────────────────────────────────
def check_seats():
    results = []
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36"
        }
        resp = requests.get(URL, headers=headers, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"[HATA] {e}")
        return results

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", {"id": "calendario"})
    if not table:
        return results

    for row in table.find_all("tr"):
        cols = row.find_all("td")
        if len(cols) < 8:
            continue

        fmt = cols[0].get_text(strip=True).upper()
        if "CENT@HOME" not in fmt:
            continue

        university = cols[1].get_text(strip=True)
        region = cols[2].get_text(strip=True)
        city = cols[3].get_text(strip=True)
        deadline = cols[4].get_text(strip=True)
        seats = cols[5].get_text(strip=True)
        state = cols[6].get_text(strip=True).upper()
        test_date = cols[7].get_text(strip=True)
        available = not any(s in state for s in UNAVAILABLE)

        results.append({
            "university": university, "city": city, "region": region,
            "deadline": deadline, "seats": seats, "state": state,
            "test_date": test_date, "available": available,
        })

    return results


# ── Otomatik Kontrol (arka plan) ─────────────────────────
async def auto_check(context: ContextTypes.DEFAULT_TYPE):
    global monitoring
    if not monitoring:
        return

    print("[*] Otomatik kontrol...")
    results = check_seats()
    found = False

    for r in results:
        if not r["available"]:
            already_notified.discard(f"{r['university']}|{r['test_date']}")
            continue

        key = f"{r['university']}|{r['test_date']}"
        if key in already_notified:
            continue

        already_notified.add(key)
        found = True
        msg = (
            "🟢 <b>CENT@HOME YER AÇILDI!</b>\n\n"
            f"🏫 <b>{r['university']}</b>\n"
            f"📍 {r['city']}, {r['region']}\n"
            f"📅 Test: {r['test_date']}\n"
            f"📝 Son kayıt: {r['deadline']}\n"
            f"💺 Kalan yer: {r['seats']}\n"
            f"📌 Durum: {r['state']}\n\n"
            f"🔗 <a href='{URL}'>Hemen kayıt ol!</a>"
        )
        await context.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID, text=msg,
            parse_mode="HTML", reply_markup=main_menu()
        )

    if not found:
        print("[·] Açık yer yok.")


# ── /start komutu ────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 <b>CENT@HOME Takip Botu</b>\n\n"
        "Aşağıdaki tuşlarla kontrol et:",
        parse_mode="HTML", reply_markup=main_menu()
    )


# ── Tuş Tıklamaları ─────────────────────────────────────
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global monitoring
    query = update.callback_query
    await query.answer()

    if query.data == "check":
        await query.edit_message_text("🔍 Kontrol ediliyor...", parse_mode="HTML")
        results = check_seats()
        home_rows = [r for r in results if True]

        if not home_rows:
            text = "📋 <b>CENT@HOME</b>\n\nHiç satır bulunamadı."
        else:
            lines = []
            for r in home_rows:
                icon = "🟢" if r["available"] else "🔴"
                lines.append(
                    f"{icon} <b>{r['university']}</b>\n"
                    f"   📍 {r['city']} | 📅 {r['test_date']} | 💺 {r['seats']}"
                )
            text = "📋 <b>CENT@HOME Durumu</b>\n\n" + "\n\n".join(lines)

        await query.edit_message_text(text, parse_mode="HTML", reply_markup=main_menu())

    elif query.data == "start":
        monitoring = True
        await query.edit_message_text(
            "▶️ Takip <b>başlatıldı</b>! Her 2 dakikada kontrol edilecek.",
            parse_mode="HTML", reply_markup=main_menu()
        )

    elif query.data == "stop":
        monitoring = False
        await query.edit_message_text(
            "⏸ Takip <b>durduruldu</b>. Tekrar başlatmak için ▶️ bas.",
            parse_mode="HTML", reply_markup=main_menu()
        )

    elif query.data == "status":
        status = "▶️ Aktif" if monitoring else "⏸ Durduruldu"
        notified_count = len(already_notified)
        await query.edit_message_text(
            f"📊 <b>Bot Durumu</b>\n\n"
            f"Takip: {status}\n"
            f"Kontrol aralığı: {CHECK_INTERVAL}sn\n"
            f"Bildirim gönderilen: {notified_count}",
            parse_mode="HTML", reply_markup=main_menu()
        )


# ── Ana ──────────────────────────────────────────────────
def main():
    print("=" * 50)
    print("  CENT@HOME Takip Botu Başlatıldı")
    print(f"  Kontrol aralığı: {CHECK_INTERVAL} saniye")
    print("=" * 50)

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(button_handler))

    # Otomatik kontrol job'ı
    app.job_queue.run_repeating(auto_check, interval=CHECK_INTERVAL, first=10)

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
