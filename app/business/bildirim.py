"""E-posta bildirimi (Hafta 9).

Yüksek önemli bir anomali bulunduğunda şirket yöneticisine e-posta gönderir.
Ayarlar .env dosyasından okunur. Ayar yoksa bildirim KAPALI kabul edilir ve
uygulama normal çalışmaya devam eder (e-posta zorunlu değildir).

Gerekli .env değişkenleri:
    SMTP_HOST=smtp.gmail.com
    SMTP_PORT=587
    SMTP_KULLANICI=gonderen@ornek.com
    SMTP_PAROLA=uygulama_parolasi      (Gmail için "uygulama şifresi")
    BILDIRIM_EPOSTA=alici@ornek.com

Parola koda veya GitHub'a ASLA yazılmaz, sadece .env'de durur.
"""
import os
import smtplib
from email.message import EmailMessage

from app.data import crud

ONEM_ADI = {"yuksek": "Yüksek", "orta": "Orta", "dusuk": "Düşük"}


def ayarlar():
    """.env'deki e-posta ayarlarını okur. Eksik varsa None döner."""
    a = {
        "host": os.getenv("SMTP_HOST"),
        "port": int(os.getenv("SMTP_PORT") or 587),
        "kullanici": os.getenv("SMTP_KULLANICI"),
        "parola": os.getenv("SMTP_PAROLA"),
        "alici": os.getenv("BILDIRIM_EPOSTA"),
    }
    if not all([a["host"], a["kullanici"], a["parola"], a["alici"]]):
        return None
    return a


def eposta_metni(anomali):
    """Anomaliden e-posta konusu ve gövdesi üretir. Kullanıcı adları yazılmaz."""
    konu = f"[Gözcü] {ONEM_ADI.get(anomali['onem'], anomali['onem'])} önemli uyarı: {anomali['kural']}"
    satirlar = [
        "Gözcü yeni bir anomali tespit etti.",
        "",
        f"Kural   : {anomali['kural']}",
        f"Önem    : {ONEM_ADI.get(anomali['onem'], anomali['onem'])}",
        f"IP      : {anomali['ip_adresi']}",
        f"Açıklama: {anomali.get('aciklama') or '-'}",
        f"Kanıt   : {len(anomali.get('kanitlar', []))} log kaydı",
    ]
    if anomali.get("ai_ozeti"):
        satirlar += ["", "Özet:", anomali["ai_ozeti"]]
    satirlar += ["", "Ayrıntılar için panoya giriş yapın."]
    return konu, "\n".join(satirlar)


def anomali_bildir(anomali):
    """Anomali için e-posta gönderir. Gönderildiyse True, değilse False.
    Hata fırlatmaz: e-posta sunucusu kapalı olsa bile yükleme işlemi bozulmaz."""
    a = ayarlar()
    if a is None:
        return False
    konu, govde = eposta_metni(anomali)
    mesaj = EmailMessage()
    mesaj["Subject"] = konu
    mesaj["From"] = a["kullanici"]
    mesaj["To"] = a["alici"]
    mesaj.set_content(govde)
    try:
        with smtplib.SMTP(a["host"], a["port"], timeout=10) as sunucu:
            sunucu.starttls()
            sunucu.login(a["kullanici"], a["parola"])
            sunucu.send_message(mesaj)
        crud.uyari_ekle(anomali["id"], "eposta")
        return True
    except Exception:
        return False
