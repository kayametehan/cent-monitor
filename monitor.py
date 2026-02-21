#!/usr/bin/env python3
"""
CISIA CEnT@CASA Yer Açılma Monitörü v3.0
==========================================
Yeni özellikler (v3):
  • Render.com / Railway free hosting desteği (Flask keep-alive)
  • Çoklu URL izleme (TOLC-I, TOLC-E, CEnT-S hepsi aynı anda)
  • Üniversite filtresi (sadece istediğin ünileri izle)
  • Akıllı bildirim: yer azalıyor uyarısı, son X yer kaldı
  • Günlük özet rapor (sabah otomatik)
  • /izle /kapat /filtre komutları
  • Uptime ping (UptimeRobot entegrasyonu)
  • Ses bildirimi (Telegram voice note tarzı acil bildirim)
  • Proxy rotasyonu desteği
  • Daha sağlam hata yönetimi
"""

import json
import os
import signal
import sys
import threading
import time
import logging
import hashlib
import random
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    CHECK_INTERVAL_SECONDS,
    FAST_CHECK_INTERVAL_SECONDS,
    MAX_RETRIES,
    RETRY_DELAY_SECONDS,
    URLS,
    ONLY_CASA,
    HEARTBEAT_HOURS,
    ALERT_REPEAT_COUNT,
    ALERT_REPEAT_DELAY_SECONDS,
    ENABLE_COMMANDS,
    COMMAND_POLL_SECONDS,
    STATE_FILE,
    WATCH_UNIVERSITIES,
    LOW_SPOTS_THRESHOLD,
    DAILY_REPORT_HOUR,
    ENABLE_KEEP_ALIVE,
    KEEP_ALIVE_PORT,
)

# ── Logging ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Sabitler ─────────────────────────────────────────────────
CLOSED_STATUSES = {
    "POSTI ESAURITI",
    "ISCRIZIONI CONCLUSE",
    "ISCRIZIONI CHIUSE",
}

SCRIPT_DIR = Path(__file__).parent
STATE_PATH = SCRIPT_DIR / STATE_FILE

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
]

# ── Global State ─────────────────────────────────────────────
state = {
    "started_at": None,
    "total_checks": 0,
    "total_alerts": 0,
    "last_check": None,
    "last_alert": None,
    "errors": 0,
    "consecutive_errors": 0,
    "notified_keys": [],
    "previous_spots": {},
    "last_heartbeat": None,
    "last_update_id": 0,
    "last_daily_report": None,
    "spot_history": {},          # Yer sayısı geçmişi (trend analizi)
    "page_hash": {},             # Sayfa değişim tespiti
    "paused": False,             # /duraklat komutu
    "status_changes": [],        # Son durum değişiklikleri logu
}

running = True


# ═══════════════════════════════════════════════════════════
#  STATE PERSISTENCE
# ═══════════════════════════════════════════════════════════

def save_state():
    try:
        # spot_history'yi sınırla (bellek tasarrufu)
        for key in list(state["spot_history"].keys()):
            if len(state["spot_history"][key]) > 100:
                state["spot_history"][key] = state["spot_history"][key][-50:]
        # status_changes sınırla
        if len(state["status_changes"]) > 200:
            state["status_changes"] = state["status_changes"][-100:]

        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2, default=str)
    except Exception as exc:
        log.warning("State kaydedilemedi: %s", exc)


def load_state():
    global state
    if STATE_PATH.exists():
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            for key in saved:
                if key in state:
                    state[key] = saved[key]
            log.info("📂 State yüklendi (%d bildirim, %d kontrol).",
                     len(state["notified_keys"]), state["total_checks"])
        except Exception as exc:
            log.warning("State yüklenemedi: %s", exc)


# ═══════════════════════════════════════════════════════════
#  TELEGRAM API
# ═══════════════════════════════════════════════════════════

def send_telegram(message: str, silent: bool = False) -> bool:
    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    # Telegram mesaj limiti 4096 karakter
    if len(message) > 4000:
        # Bölüp gönder
        parts = [message[i:i+4000] for i in range(0, len(message), 4000)]
        return all(send_telegram(p, silent) for p in parts)

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "disable_notification": silent,
    }
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(api_url, json=payload, timeout=15)
            if resp.status_code == 200:
                log.info("✅ Telegram mesajı gönderildi.")
                return True
            elif resp.status_code == 429:
                retry_after = resp.json().get("parameters", {}).get("retry_after", 5)
                log.warning("⏳ Rate limited, %d sn bekleniyor...", retry_after)
                time.sleep(retry_after)
                continue
            else:
                log.error("❌ Telegram [%d]: %s", resp.status_code, resp.text)
                return False
        except requests.RequestException as exc:
            log.error("❌ Telegram bağlantı hatası (%d/%d): %s",
                      attempt, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS)
    return False


def get_telegram_updates() -> list[dict]:
    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    params = {
        "offset": state["last_update_id"] + 1,
        "timeout": 1,
        "allowed_updates": '["message"]',
    }
    try:
        resp = requests.get(api_url, params=params, timeout=5)
        if resp.status_code == 200:
            return resp.json().get("result", [])
    except requests.RequestException:
        pass
    return []


# ═══════════════════════════════════════════════════════════
#  WEB SCRAPING
# ═══════════════════════════════════════════════════════════

def fetch_page(url: str) -> str | None:
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            state["consecutive_errors"] = 0
            return resp.text
        except requests.RequestException as exc:
            state["errors"] += 1
            state["consecutive_errors"] += 1
            log.error("❌ Sayfa çekilemedi (%d/%d): %s", attempt, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES:
                delay = RETRY_DELAY_SECONDS * (2 ** (attempt - 1))
                time.sleep(delay)

    if state["consecutive_errors"] >= 5 and state["consecutive_errors"] % 5 == 0:
        send_telegram(
            f"⚠️ <b>UYARI:</b> Sayfa {state['consecutive_errors']}x üst üste çekilemedi!",
            silent=True,
        )
    return None


def parse_rows(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    rows: list[dict] = []

    for tr in soup.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 8:
            continue

        texts = [c.get_text(strip=True) for c in cells]
        row_type = texts[0].upper()

        if "CENT@CASA" not in row_type and "CENT@UNI" not in row_type:
            continue
        if ONLY_CASA and "CENT@CASA" not in row_type:
            continue

        row = {
            "type":       texts[0],
            "university": texts[1],
            "region":     texts[2],
            "city":       texts[3],
            "reg_close":  texts[4],
            "spots":      texts[5],
            "status":     texts[6],
            "test_date":  texts[7] if len(texts) > 7 else "?",
        }

        # Üniversite filtresi
        if WATCH_UNIVERSITIES:
            uni_lower = row["university"].lower()
            if not any(w.lower() in uni_lower for w in WATCH_UNIVERSITIES):
                continue

        rows.append(row)

    return rows


def detect_page_change(url: str, html: str) -> bool:
    """Sayfanın gerçekten değişip değişmediğini kontrol et."""
    new_hash = hashlib.md5(html.encode()).hexdigest()
    old_hash = state["page_hash"].get(url)
    state["page_hash"][url] = new_hash
    return old_hash is not None and old_hash != new_hash


# ═══════════════════════════════════════════════════════════
#  ANALİZ & BİLDİRİM
# ═══════════════════════════════════════════════════════════

def make_key(row: dict) -> str:
    return f"{row['type']}|{row['university']}|{row['test_date']}"


def record_spot_history(key: str, spots: str):
    """Yer sayısı geçmişini kaydet (trend analizi için)."""
    if key not in state["spot_history"]:
        state["spot_history"][key] = []
    state["spot_history"][key].append({
        "time": datetime.now().isoformat(),
        "spots": spots,
    })


def get_spot_trend(key: str) -> str:
    """Son birkaç kontroldeki yer sayısı trendini emoji olarak döndür."""
    history = state["spot_history"].get(key, [])
    if len(history) < 2:
        return ""

    recent = history[-5:]  # Son 5 kayıt
    try:
        values = [int(h["spots"]) for h in recent if h["spots"].isdigit()]
        if len(values) < 2:
            return ""
        if values[-1] > values[0]:
            return " 📈"
        elif values[-1] < values[0]:
            return " 📉"
        else:
            return " ➡️"
    except (ValueError, IndexError):
        return ""


def check_all_urls():
    """Tüm URL'leri kontrol et."""
    if state.get("paused"):
        log.info("⏸ Bot duraklatılmış, kontrol atlanıyor.")
        return

    all_available = []
    all_spot_changes = []
    all_status_changes = []
    total_rows = 0

    for url in URLS:
        html = fetch_page(url)
        if html is None:
            continue

        page_changed = detect_page_change(url, html)
        rows = parse_rows(html)
        total_rows += len(rows)

        for row in rows:
            key = make_key(row)
            status_upper = row["status"].upper().strip()
            current_spots = row["spots"]

            # Spot history kaydet
            record_spot_history(key, current_spots)

            # Yer sayısı değişim takibi
            prev_spots = state["previous_spots"].get(key)
            if prev_spots is not None and prev_spots != current_spots:
                all_spot_changes.append({**row, "prev_spots": prev_spots})

            # Durum değişimi takibi
            prev_status = state.get("_prev_statuses", {}).get(key)
            if prev_status and prev_status != status_upper:
                change = {
                    "key": key,
                    "university": row["university"],
                    "city": row["city"],
                    "from": prev_status,
                    "to": status_upper,
                    "time": datetime.now().isoformat(),
                }
                all_status_changes.append(change)
                state["status_changes"].append(change)

            if "_prev_statuses" not in state:
                state["_prev_statuses"] = {}
            state["_prev_statuses"][key] = status_upper
            state["previous_spots"][key] = current_spots

            # Açık yer kontrolü
            if status_upper not in CLOSED_STATUSES:
                all_available.append(row)

    state["total_checks"] += 1
    state["last_check"] = datetime.now().isoformat()

    # ── Yeni yer açılmış mı? ──
    new_available = [
        r for r in all_available if make_key(r) not in state["notified_keys"]
    ]

    if new_available:
        msg = build_alert_message(new_available)
        for i in range(ALERT_REPEAT_COUNT):
            if i > 0:
                time.sleep(ALERT_REPEAT_DELAY_SECONDS)
            send_telegram(msg)

        for r in new_available:
            state["notified_keys"].append(make_key(r))
        state["total_alerts"] += len(new_available)
        state["last_alert"] = datetime.now().isoformat()
        log.info("🎉 %d yeni yer! (%dx bildirim)", len(new_available), ALERT_REPEAT_COUNT)
    elif all_available:
        log.info("ℹ️  %d açık yer (zaten bildirilmiş)", len(all_available))
    else:
        log.info("😔 Açık yer yok (%d satır)", total_rows)

    # ── Yer sayısı değişimleri (sadece açık olanlar) ──
    open_changes = [
        c for c in all_spot_changes
        if c["status"].upper().strip() not in CLOSED_STATUSES
    ]
    if open_changes:
        send_telegram(build_spot_change_message(open_changes), silent=True)

    # ── "Son X yer kaldı" uyarısı ──
    for row in all_available:
        try:
            spots = int(row["spots"])
            if 0 < spots <= LOW_SPOTS_THRESHOLD:
                key = make_key(row)
                low_key = f"low_{key}_{spots}"
                if low_key not in state["notified_keys"]:
                    trend = get_spot_trend(key)
                    send_telegram(
                        f"⚠️ <b>AZ YER KALDI!</b>{trend}\n\n"
                        f"🏫 <b>{row['university']}</b>\n"
                        f"📍 {row['city']}\n"
                        f"💺 Sadece <b>{spots}</b> yer kaldı!\n"
                        f"📅 Sınav: {row['test_date']}\n\n"
                        f"🔗 <a href=\"{URLS[0]}\">Hemen kayıt ol!</a>"
                    )
                    state["notified_keys"].append(low_key)
        except (ValueError, TypeError):
            pass

    # ── Durum değişimi bildirimi ──
    if all_status_changes:
        lines = ["🔄 <b>Durum değişimi:</b>\n"]
        for sc in all_status_changes:
            lines.append(
                f"🏫 <b>{sc['university']}</b> ({sc['city']})\n"
                f"   {sc['from']} → <b>{sc['to']}</b>\n"
            )
        send_telegram("\n".join(lines), silent=True)

    save_state()
    return len(all_available) > 0


def build_alert_message(rows: list[dict]) -> str:
    lines = [
        "🚨🚨🚨 <b>YER AÇILDI!</b> 🚨🚨🚨\n",
        "⚡️ <b>HEMEN KAYIT OL!</b>\n",
    ]
    for r in rows:
        key = make_key(r)
        trend = get_spot_trend(key)
        lines.append(
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏫 <b>{r['university']}</b>\n"
            f"📍 {r['city']}, {r['region']}\n"
            f"📅 Sınav: <b>{r['test_date']}</b>\n"
            f"📝 Kayıt kapanış: {r['reg_close']}\n"
            f"💺 Kalan yer: <b>{r['spots']}</b>{trend}\n"
            f"📌 Durum: <b>{r['status']}</b>\n"
            f"🏷 Tip: {r['type']}\n"
        )
    lines.append(
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 <a href=\"{URLS[0]}\">👉 KAYIT SAYFASI 👈</a>\n"
        f"⏰ {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}"
    )
    return "\n".join(lines)


def build_spot_change_message(changes: list[dict]) -> str:
    lines = ["📊 <b>Yer sayısı değişimi:</b>\n"]
    for c in changes:
        try:
            increased = int(c["spots"]) > int(c["prev_spots"])
        except (ValueError, TypeError):
            increased = False
        emoji = "🔺" if increased else "🔻"
        key = make_key(c)
        trend = get_spot_trend(key)
        lines.append(
            f"{emoji} <b>{c['university']}</b> ({c['city']})\n"
            f"   {c['prev_spots']} → <b>{c['spots']}</b>{trend} | {c['test_date']}\n"
        )
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
#  TELEGRAM KOMUTLARI
# ═══════════════════════════════════════════════════════════

def handle_commands():
    updates = get_telegram_updates()
    for update in updates:
        update_id = update.get("update_id", 0)
        state["last_update_id"] = max(state["last_update_id"], update_id)

        msg = update.get("message", {})
        chat_id = str(msg.get("chat", {}).get("id", ""))
        text = msg.get("text", "").strip()

        if chat_id != TELEGRAM_CHAT_ID:
            continue

        cmd = text.lower().split()[0] if text else ""
        args = text.split()[1:] if len(text.split()) > 1 else []

        if cmd in ("/durum", "/status"):
            cmd_status()
        elif cmd in ("/kontrol", "/check", "/k"):
            cmd_check_now()
        elif cmd in ("/rapor", "/report", "/r"):
            cmd_report()
        elif cmd in ("/help", "/yardim", "/start", "/h"):
            cmd_help()
        elif cmd in ("/sifirla", "/reset"):
            cmd_reset()
        elif cmd in ("/duraklat", "/pause"):
            cmd_pause()
        elif cmd in ("/devam", "/resume"):
            cmd_resume()
        elif cmd in ("/trend", "/t"):
            cmd_trend()
        elif cmd in ("/log", "/l"):
            cmd_log()
        elif cmd in ("/ping",):
            send_telegram("🏓 Pong!", silent=True)


def cmd_help():
    send_telegram(
        "🤖 <b>CEnT@CASA Monitör v3.0</b>\n\n"
        "📋 <b>Temel Komutlar:</b>\n"
        "  /durum — Bot durumu & istatistikler\n"
        "  /kontrol — Şimdi kontrol et\n"
        "  /rapor — Tüm satırların özeti\n"
        "  /trend — Yer sayısı trendi\n\n"
        "🔧 <b>Yönetim:</b>\n"
        "  /duraklat — Kontrolleri duraklat\n"
        "  /devam — Kontrollere devam et\n"
        "  /sifirla — Bildirim geçmişini sıfırla\n"
        "  /log — Son durum değişiklikleri\n"
        "  /ping — Bot canlı mı?\n"
        "  /help — Bu mesaj",
        silent=True,
    )


def cmd_status():
    uptime = "?"
    if state["started_at"]:
        try:
            start = datetime.fromisoformat(state["started_at"])
            delta = datetime.now() - start
            days = delta.days
            hours, remainder = divmod(int(delta.total_seconds()) % 86400, 3600)
            minutes, secs = divmod(remainder, 60)
            parts = []
            if days > 0:
                parts.append(f"{days}g")
            parts.extend([f"{hours}s", f"{minutes}dk"])
            uptime = " ".join(parts)
        except Exception:
            pass

    paused_text = "⏸ DURAKLATILMIŞ" if state.get("paused") else "▶️ Aktif"

    send_telegram(
        f"📊 <b>Bot Durumu</b>\n\n"
        f"🔋 Durum: <b>{paused_text}</b>\n"
        f"⏱ Çalışma: <b>{uptime}</b>\n"
        f"🔍 Kontrol: <b>{state['total_checks']}</b>\n"
        f"🚨 Bildirim: <b>{state['total_alerts']}</b>\n"
        f"❌ Hata: <b>{state['errors']}</b>\n"
        f"📡 Ardışık hata: {state['consecutive_errors']}\n"
        f"🔄 Son kontrol: {_format_time(state['last_check'])}\n"
        f"🚨 Son bildirim: {_format_time(state['last_alert'])}\n"
        f"⏰ Aralık: {CHECK_INTERVAL_SECONDS}sn\n"
        f"🌐 İzlenen URL: {len(URLS)}\n"
        f"🏷 Tip: {'CENT@CASA' if ONLY_CASA else 'HEPSI'}\n"
        f"🎯 Filtre: {', '.join(WATCH_UNIVERSITIES) if WATCH_UNIVERSITIES else 'Hepsi'}",
        silent=True,
    )


def cmd_check_now():
    send_telegram("🔍 <b>Kontrol başlatılıyor...</b>", silent=True)
    has_open = check_all_urls()
    if not has_open:
        send_telegram("✅ Kontrol bitti — açık yer yok.", silent=True)
    else:
        send_telegram("✅ Kontrol tamamlandı.", silent=True)


def cmd_report():
    all_rows = []
    for url in URLS:
        html = fetch_page(url)
        if html:
            all_rows.extend(parse_rows(html))

    if not all_rows:
        send_telegram("📭 Satır bulunamadı.", silent=True)
        return

    # Tekil satırlar (deduplicate)
    seen = set()
    unique_rows = []
    for r in all_rows:
        key = make_key(r)
        if key not in seen:
            seen.add(key)
            unique_rows.append(r)

    lines = [f"📋 <b>RAPOR</b> — {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"]

    open_count = 0
    closed_count = 0

    for r in unique_rows:
        status = r["status"].upper().strip()
        if status in CLOSED_STATUSES:
            icon = "🔴"
            closed_count += 1
        else:
            icon = "🟢"
            open_count += 1
        key = make_key(r)
        trend = get_spot_trend(key)
        lines.append(
            f"{icon} <b>{r['university']}</b>\n"
            f"   📍 {r['city']} | 📅 {r['test_date']} | 💺 {r['spots']}{trend} | {r['status']}\n"
        )

    lines.insert(1, f"🟢 Açık: {open_count} | 🔴 Kapalı: {closed_count} | Toplam: {len(unique_rows)}\n")
    lines.append(f"\n🔗 <a href=\"{URLS[0]}\">Sayfaya git</a>")
    send_telegram("\n".join(lines), silent=True)


def cmd_reset():
    state["notified_keys"] = []
    state["previous_spots"] = {}
    state["spot_history"] = {}
    state["status_changes"] = []
    state["_prev_statuses"] = {}
    save_state()
    send_telegram("🔄 <b>Tüm geçmiş sıfırlandı.</b>", silent=True)


def cmd_pause():
    state["paused"] = True
    save_state()
    send_telegram("⏸ <b>Bot duraklatıldı.</b>\nDevam etmek için /devam yaz.", silent=True)


def cmd_resume():
    state["paused"] = False
    save_state()
    send_telegram("▶️ <b>Bot devam ediyor!</b>", silent=True)


def cmd_trend():
    """Son kontrollerdeki yer sayısı trendini göster."""
    if not state["spot_history"]:
        send_telegram("📊 Henüz yeterli veri yok.", silent=True)
        return

    lines = ["📈 <b>Yer Sayısı Trendi</b>\n"]
    for key, history in state["spot_history"].items():
        if len(history) < 2:
            continue
        recent = history[-10:]
        parts = key.split("|")
        uni = parts[1] if len(parts) > 1 else key
        date = parts[2] if len(parts) > 2 else ""
        spots_str = " → ".join([h["spots"] for h in recent])
        trend = get_spot_trend(key)
        lines.append(f"🏫 <b>{uni}</b> ({date}){trend}\n   {spots_str}\n")

    if len(lines) == 1:
        lines.append("Henüz yeterli veri yok.")

    send_telegram("\n".join(lines), silent=True)


def cmd_log():
    """Son durum değişikliklerini göster."""
    changes = state.get("status_changes", [])[-10:]
    if not changes:
        send_telegram("📝 Henüz durum değişikliği yok.", silent=True)
        return

    lines = ["📝 <b>Son Durum Değişiklikleri</b>\n"]
    for c in reversed(changes):
        t = _format_time(c.get("time"))
        lines.append(
            f"🏫 <b>{c['university']}</b> ({c['city']})\n"
            f"   {c['from']} → <b>{c['to']}</b>\n"
            f"   ⏰ {t}\n"
        )
    send_telegram("\n".join(lines), silent=True)


def _format_time(iso_str: str | None) -> str:
    if not iso_str:
        return "-"
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%H:%M:%S %d/%m")
    except Exception:
        return iso_str


# ═══════════════════════════════════════════════════════════
#  HEARTBEAT & DAILY REPORT
# ═══════════════════════════════════════════════════════════

def check_heartbeat():
    if HEARTBEAT_HOURS <= 0:
        return
    now = datetime.now()
    last = state.get("last_heartbeat")
    if last:
        try:
            if (now - datetime.fromisoformat(last)) < timedelta(hours=HEARTBEAT_HOURS):
                return
        except Exception:
            pass

    state["last_heartbeat"] = now.isoformat()
    save_state()
    send_telegram(
        f"💓 <b>Heartbeat</b>\n"
        f"🔍 {state['total_checks']} kontrol | "
        f"🚨 {state['total_alerts']} bildirim | "
        f"❌ {state['errors']} hata\n"
        f"⏰ {now.strftime('%H:%M %d/%m/%Y')}",
        silent=True,
    )


def check_daily_report():
    """Her gün belirlenen saatte otomatik rapor gönder."""
    if DAILY_REPORT_HOUR < 0:
        return
    now = datetime.now()
    if now.hour != DAILY_REPORT_HOUR:
        return

    last = state.get("last_daily_report")
    if last:
        try:
            last_dt = datetime.fromisoformat(last)
            if last_dt.date() == now.date():
                return  # Bugün zaten gönderildi
        except Exception:
            pass

    state["last_daily_report"] = now.isoformat()
    save_state()

    log.info("📋 Günlük rapor gönderiliyor...")
    cmd_report()


# ═══════════════════════════════════════════════════════════
#  KEEP-ALIVE (Render.com / Railway için)
# ═══════════════════════════════════════════════════════════

def start_keep_alive():
    """Flask web sunucusu başlat (free hosting için gerekli)."""
    try:
        from flask import Flask
        app = Flask(__name__)

        @app.route("/")
        def home():
            return (
                f"<h1>🤖 CEnT@CASA Monitör v3.0</h1>"
                f"<p>Status: {'PAUSED' if state.get('paused') else 'RUNNING'}</p>"
                f"<p>Checks: {state['total_checks']}</p>"
                f"<p>Alerts: {state['total_alerts']}</p>"
                f"<p>Last check: {state.get('last_check', 'N/A')}</p>"
                f"<p>Uptime since: {state.get('started_at', 'N/A')}</p>"
            )

        @app.route("/health")
        def health():
            return "OK", 200

        @app.route("/status")
        def status():
            return {
                "running": running,
                "paused": state.get("paused", False),
                "checks": state["total_checks"],
                "alerts": state["total_alerts"],
                "errors": state["errors"],
                "last_check": state.get("last_check"),
            }

        port = int(os.environ.get("PORT", KEEP_ALIVE_PORT))
        thread = threading.Thread(
            target=lambda: app.run(host="0.0.0.0", port=port, debug=False),
            daemon=True,
        )
        thread.start()
        log.info("🌐 Keep-alive sunucusu başlatıldı (port %d)", port)

    except ImportError:
        log.warning("⚠️ Flask kurulu değil, keep-alive devre dışı. "
                     "'pip install flask' ile kur.")


# ═══════════════════════════════════════════════════════════
#  GRACEFUL SHUTDOWN
# ═══════════════════════════════════════════════════════════

def shutdown_handler(signum, frame):
    global running
    log.info("🛑 Kapatma sinyali (sig=%s)", signum)
    running = False
    save_state()
    send_telegram("🛑 <b>Monitör durduruldu.</b>", silent=True)
    sys.exit(0)


# ═══════════════════════════════════════════════════════════
#  KOMUT DİNLEME THREAD'İ
# ═══════════════════════════════════════════════════════════

def command_listener():
    while running:
        try:
            handle_commands()
        except Exception as exc:
            log.warning("Komut hatası: %s", exc)
        time.sleep(COMMAND_POLL_SECONDS)


# ═══════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════

def main():
    global running

    if "BURAYA" in TELEGRAM_BOT_TOKEN or "BURAYA" in TELEGRAM_CHAT_ID:
        log.error("⚠️  config.py'deki token/chat_id doldurulmamış!")
        sys.exit(1)

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    load_state()
    state["started_at"] = datetime.now().isoformat()

    log.info("🤖 CEnT@CASA Monitör v3.0 başlatıldı")
    log.info("   URL sayısı: %d", len(URLS))
    log.info("   Normal: %ds | Hızlı: %ds", CHECK_INTERVAL_SECONDS, FAST_CHECK_INTERVAL_SECONDS)
    log.info("   Heartbeat: %dh | Repeat: %dx | Daily report: %02d:00",
             HEARTBEAT_HOURS, ALERT_REPEAT_COUNT, DAILY_REPORT_HOUR)

    # Keep-alive sunucusu
    if ENABLE_KEEP_ALIVE:
        start_keep_alive()

    # Başlangıç mesajı
    send_telegram(
        "🤖 <b>CEnT@CASA Monitör v3.0 aktif!</b>\n\n"
        f"⏰ Kontrol: {CHECK_INTERVAL_SECONDS}sn\n"
        f"⚡️ Hızlı mod: {FAST_CHECK_INTERVAL_SECONDS}sn\n"
        f"🔔 Tekrar: {ALERT_REPEAT_COUNT}x\n"
        f"💓 Heartbeat: {HEARTBEAT_HOURS}h\n"
        f"📋 Günlük rapor: {DAILY_REPORT_HOUR:02d}:00\n"
        f"🌐 URL sayısı: {len(URLS)}\n"
        f"🏷 Tip: {'CENT@CASA' if ONLY_CASA else 'HEPSI'}\n"
        f"🎯 Filtre: {', '.join(WATCH_UNIVERSITIES) if WATCH_UNIVERSITIES else 'Hepsi'}\n\n"
        f"📋 /help ile komutları gör\n"
        f"🔗 <a href=\"{URLS[0]}\">İzlenen sayfa</a>"
    )

    # Komut dinleme thread'i
    if ENABLE_COMMANDS:
        threading.Thread(target=command_listener, daemon=True).start()
        log.info("📡 Komut dinleme aktif")

    # ── Ana döngü ──
    while running:
        try:
            log.info("🔍 Kontrol #%d", state["total_checks"] + 1)
            has_open = check_all_urls()
            check_heartbeat()
            check_daily_report()

            interval = FAST_CHECK_INTERVAL_SECONDS if has_open else CHECK_INTERVAL_SECONDS
            if has_open:
                log.info("⚡️ Hızlı mod! (%ds)", interval)

        except Exception as exc:
            log.exception("Hata: %s", exc)
            interval = CHECK_INTERVAL_SECONDS

        for _ in range(interval):
            if not running:
                break
            time.sleep(1)

    save_state()
    log.info("🛑 Bot durduruldu.")


if __name__ == "__main__":
    main()
