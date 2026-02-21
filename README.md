# 🤖 CEnT@CASA Telegram Bildirim Botu

testcisia.it sitesindeki **CEnT-S** takvim sayfasını düzenli aralıklarla kontrol eder.  
**CENT@CASA** kısmında yer açıldığında Telegram üzerinden bildirim gönderir.

---

## 🚀 Kurulum

### 1. Telegram Bot Oluştur

1. Telegram'da **@BotFather**'a git
2. `/newbot` komutunu gönder
3. Bot adını ve kullanıcı adını belirle
4. Sana verilen **API Token**'ı kopyala

### 2. Chat ID'ni Öğren

1. Oluşturduğun bota Telegram'dan `/start` mesajı gönder
2. Tarayıcında şu adresi aç (TOKEN kısmını kendi token'ınla değiştir):
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
3. Gelen JSON'da `"chat":{"id": 123456789}` kısmındaki sayıyı kopyala

### 3. Ayarları Yap

`config.py` dosyasını aç ve şu değerleri doldur:

```python
TELEGRAM_BOT_TOKEN = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
TELEGRAM_CHAT_ID = "123456789"
```

### 4. Bağımlılıkları Kur

```bash
cd /Users/metemac/bang
pip install -r requirements.txt
```

### 5. Botu Başlat

```bash
python monitor.py
```

---

## ⚙️ Ayarlar (config.py)

| Ayar | Açıklama | Varsayılan |
|------|----------|------------|
| `TELEGRAM_BOT_TOKEN` | BotFather'dan alınan token | - |
| `TELEGRAM_CHAT_ID` | Bildirim alacak kişinin chat ID'si | - |
| `CHECK_INTERVAL_SECONDS` | Kaç saniyede bir kontrol edilsin | `60` |
| `ONLY_CASA` | Sadece CENT@CASA mı izlensin | `True` |

---

## 📌 Nasıl Çalışır?

1. Her `CHECK_INTERVAL_SECONDS` saniyede bir sayfayı kontrol eder
2. CENT@CASA satırlarını parse eder
3. Durumu **POSTI ESAURITI**, **ISCRIZIONI CONCLUSE** veya **ISCRIZIONI CHIUSE** olmayan satırları tespit eder
4. Yeni açılan yer bulursa Telegram'dan bildirim gönderir
5. Aynı satır için tekrar bildirim göndermez (spam önleme)

---

## 🖥️ Arka Planda Çalıştırma (opsiyonel)

Mac'te terminali kapatsan bile çalışmaya devam etmesi için:

```bash
nohup python monitor.py > monitor.log 2>&1 &
```

Durdurmak için:
```bash
pkill -f monitor.py
```

Log'ları görmek için:
```bash
tail -f monitor.log
```
