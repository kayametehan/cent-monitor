import os

# ============================================================
# TELEGRAM BOT AYARLARI
# ============================================================
# Render.com'da environment variable olarak da ayarlanabilir

TELEGRAM_BOT_TOKEN = os.environ.get(
    "TELEGRAM_BOT_TOKEN",
    "8575472491:AAGMQ1g34d9tS1TD0rYOw2s2r0WRlunIt8M"
)
TELEGRAM_CHAT_ID = os.environ.get(
    "TELEGRAM_CHAT_ID",
    "7097055241"
)

# ============================================================
# İZLEME AYARLARI
# ============================================================

# Birden fazla URL izlenebilir (farklı TOLC türleri)
URLS = [
    "https://testcisia.it/calendario.php?tolc=cents&lingua=inglese",
    # İstersen başka TOLC'lar da ekleyebilirsin:
    # "https://testcisia.it/calendario.php?tolc=ingegneria&lingua=inglese",
    # "https://testcisia.it/calendario.php?tolc=economia&lingua=inglese",
]

# Normal kontrol aralığı (saniye)
CHECK_INTERVAL_SECONDS = 60

# Yer açılınca daha sık kontrol (saniye)
FAST_CHECK_INTERVAL_SECONDS = 15

# Retry ayarları
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5

# Sadece CENT@CASA mı? (False = CENT@UNI de izlenir)
ONLY_CASA = True

# ============================================================
# ÜNİVERSİTE FİLTRESİ
# ============================================================
# Sadece belirli üniversiteleri izle (boş liste = hepsini izle)
# Kısmi eşleşme, büyük/küçük harf fark etmez
WATCH_UNIVERSITIES = [
    # "Politecnico di Milano",
    # "Sapienza",
    # "Bologna",
    # "Padova",
]

# "Son X yer kaldı!" uyarı eşiği
LOW_SPOTS_THRESHOLD = 5

# ============================================================
# BİLDİRİM AYARLARI
# ============================================================

# Heartbeat aralığı saat (0 = kapalı)
HEARTBEAT_HOURS = 6

# Yer açılınca kaç kez tekrar bildirim gönderilsin
ALERT_REPEAT_COUNT = 10
ALERT_REPEAT_DELAY_SECONDS = 30

# Günlük otomatik rapor saati (0-23 arası, -1 = kapalı)
DAILY_REPORT_HOUR = 8

# Telegram komutları
ENABLE_COMMANDS = True
COMMAND_POLL_SECONDS = 5

# State dosyası
STATE_FILE = "state.json"

# ============================================================
# HOSTING (Render.com / Railway)
# ============================================================

# Flask keep-alive (free hosting'de uyumayı engeller)
ENABLE_KEEP_ALIVE = bool(os.environ.get("RENDER") or os.environ.get("ENABLE_KEEP_ALIVE"))
KEEP_ALIVE_PORT = int(os.environ.get("PORT", 10000))
