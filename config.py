import os

# Telegram
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8575472491:AAGMQ1g34d9tS1TD0rYOw2s2r0WRlunIt8M")

# Chat ID veya Channel username
# Kişisel chat: "7097055241"
# Channel: "@kanal_adi" şeklinde yaz (botun channel'da admin olması lazım)
CHAT_ID = os.environ.get("CHAT_ID", "7097055241")

# İki dilde de kontrol — hangisinde açılırsa yakalasın
URLs = [
    "https://testcisia.it/calendario.php?tolc=cents&lingua=inglese",   # EN
    "https://testcisia.it/calendario.php?tolc=cents&lingua=italiano",  # IT
]

# Kaç saniyede bir kontrol
INTERVAL = 60

# Sadece CENT@HOME / CENT@CASA mı
ONLY_HOME = True

# Yer açılınca kaç kez bildirim
REPEAT = 3
