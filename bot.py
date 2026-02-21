import requests
from bs4 import BeautifulSoup
import os
import traceback
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ── Ayarlar ──────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8575472491:AAGMQ1g34d9tS1TD0rYOw2s2r0WRlunIt8M")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "120"))

URL = "https://testcisia.it/calendario.php?tolc=cents&lingua=inglese"

UNAVAILABLE = {"NOT LONGER AVAILABLE", "BOOKINGS CLOSED", "ENDED"}

already_notified = set()
monitoring = True
subscribers = set()  # /start yapan herkes otomatik abone olur


def main_menu():
    keyboard = [
        [InlineKeyboardButton("🔍 Şimdi Kontrol Et", callback_data="check")],
        [
            InlineKeyboardButton("▶️ Başlat", callback_data="start_mon"),
            InlineKeyboardButton("⏸ Durdur", callback_data="stop_mon"),
        ],
        [InlineKeyboardButton("📊 Durum", callback_data="status")],
    ]
    return InlineKeyboardMarkup(keyboard)


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
        print(f"[HATA] Sayfa cekilemedi: {e}")
        return results

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", {"id": "calendario"})
    if not table:
        print("[HATA] Tablo bulunamadi")
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


# ── Otomatik kontrol ─────────────────────────────────────
async def auto_check(context: ContextTypes.DEFAULT_TYPE):
    global monitoring
    if not monitoring or not subscribers:
        return

    print(f"[*] Otomatik kontrol... ({len(subscribers)} abone)")
    try:
        results = check_seats()
    except Exception as e:
        print(f"[HATA] {e}")
        return

    for r in results:
        if not r["available"]:
            already_notified.discard(f"{r['university']}|{r['test_date']}")
            continue

        key = f"{r['university']}|{r['test_date']}"
        if key in already_notified:
            continue

        already_notified.add(key)
        msg = (
            "🟢 <b>CENT@HOME YER AÇILDI!</b>\n\n"
            f"🏫 <b>{r['university']}</b>\n"
            f"📍 {r['city']}, {r['region']}\n"
            f"📅 Test: {r['test_date']}\n"
            f"📝 Son kayıt: {r['deadline']}\n"
            f"💺 Kalan yer: {r['seats']}\n\n"
            f"🔗 <a href='{URL}'>Hemen kayıt ol!</a>"
        )
        # Tüm abonelere gönder
        for chat_id in list(subscribers):
            try:
                await context.bot.send_message(
                    chat_id=chat_id, text=msg,
                    parse_mode="HTML", reply_markup=main_menu()
                )
            except Exception as e:
                print(f"[HATA] {chat_id} mesaj gonderilemedi: {e}")

    if not any(r["available"] for r in results):
        print("[·] Acik yer yok.")


# ── /start & /menu ───────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    subscribers.add(chat_id)
    print(f"[INFO] /start → chat_id: {chat_id} (toplam {len(subscribers)} abone)")
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "🤖 <b>CENT@HOME Takip Botu</b>\n\n"
                "✅ Bildirim almaya başladın!\n"
                "Yer açılınca otomatik mesaj gelecek.\n\n"
                "Tuşlarla kontrol et:"
            ),
            parse_mode="HTML",
            reply_markup=main_menu()
        )
    except Exception as e:
        print(f"[HATA] start: {e}")


# ── Tuş tıklamaları ─────────────────────────────────────
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global monitoring
    query = update.callback_query

    try:
        await query.answer()
    except Exception:
        pass

    action = query.data
    chat_id = query.message.chat_id
    subscribers.add(chat_id)

    try:
        if action == "check":
            try:
                await query.edit_message_text("🔍 Kontrol ediliyor...", parse_mode="HTML")
            except Exception:
                pass

            results = check_seats()

            if not results:
                text = "📋 <b>CENT@HOME</b>\n\nHiç CENT@HOME satırı bulunamadı."
            else:
                lines = []
                for r in results:
                    icon = "🟢" if r["available"] else "🔴"
                    lines.append(
                        f"{icon} <b>{r['university']}</b>\n"
                        f"    📍 {r['city']} | 📅 {r['test_date']} | 💺 {r['seats']}"
                    )
                text = "📋 <b>CENT@HOME Durumu</b>\n\n" + "\n\n".join(lines)

            try:
                await query.edit_message_text(text, parse_mode="HTML", reply_markup=main_menu())
            except Exception:
                await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=main_menu())

        elif action == "start_mon":
            monitoring = True
            text = "▶️ Takip <b>başlatıldı</b>! Her 2 dakikada kontrol edilecek."
            try:
                await query.edit_message_text(text, parse_mode="HTML", reply_markup=main_menu())
            except Exception:
                await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=main_menu())

        elif action == "stop_mon":
            monitoring = False
            text = "⏸ Takip <b>durduruldu</b>. Tekrar başlatmak için ▶️ bas."
            try:
                await query.edit_message_text(text, parse_mode="HTML", reply_markup=main_menu())
            except Exception:
                await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=main_menu())

        elif action == "status":
            st = "▶️ Aktif" if monitoring else "⏸ Durduruldu"
            text = (
                f"📊 <b>Bot Durumu</b>\n\n"
                f"Takip: {st}\n"
                f"Kontrol aralığı: {CHECK_INTERVAL}sn\n"
                f"Abone sayısı: {len(subscribers)}\n"
                f"Bildirim sayısı: {len(already_notified)}"
            )
            try:
                await query.edit_message_text(text, parse_mode="HTML", reply_markup=main_menu())
            except Exception:
                await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=main_menu())

    except Exception as e:
        print(f"[HATA] button: {traceback.format_exc()}")
        try:
            await context.bot.send_message(chat_id=chat_id, text=f"❌ Hata: {e}", reply_markup=main_menu())
        except Exception:
            pass


def main():
    print("=" * 50)
    print("  CENT@HOME Takip Botu")
    print(f"  Kontrol: {CHECK_INTERVAL}sn")
    print("=" * 50)

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_start))
    app.add_handler(CallbackQueryHandler(button_handler))

    app.job_queue.run_repeating(auto_check, interval=CHECK_INTERVAL, first=10)

    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
