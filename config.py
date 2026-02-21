import os

# Telegram
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8575472491:AAGMQ1g34d9tS1TD0rYOw2s2r0WRlunIt8M")
CHAT_ID = os.environ.get("CHAT_ID", "7097055241")

# Sayfa
URL = "https://testcisia.it/calendario.php?tolc=cents&lingua=inglese"

# Kaç saniyede bir kontrol
INTERVAL = 60

# Sadece CENT@CASA mı
ONLY_CASA = True

# Yer açılınca kaç kez bildirim
REPEAT = 3
