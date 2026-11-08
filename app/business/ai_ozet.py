"""Anomali özeti (Hafta 10).

Her anomali için analistin okuyacağı 2-3 cümlelik Türkçe bir özet üretir:
ne oldu, neden şüpheli, ne yapılmalı.

İki yol vardır:
  1) Yapay zekâ (LLM): .env'de ANTHROPIC_API_KEY varsa model özet yazar.
  2) Kural tabanlı: anahtar yoksa, servis hata verirse ya da modelin cevabı
     doğrulamadan geçmezse hazır şablonla özet yazılır.
Böylece yapay zekâ olmadan da sistem çalışır (PDF: yedek mekanizma).

GİZLİLİK: Modele ham log GÖNDERİLMEZ. Önce veri_hazirla() ile özet sayılar
çıkarılır, kullanıcı adları ("a***") ve IP'nin son kısmı ("198.51.100.x")
maskelenir. Şirket adı hiç gönderilmez.

HALÜSİNASYON KONTROLÜ: dogrula() modelin yazdığı metinde veride olmayan bir
sayı, maskesiz bir kullanıcı adı ya da tam bir IP adresi varsa metni reddeder.
"""
import ipaddress
import json
import os
import re
from urllib.request import Request, urlopen

API_ADRESI = "https://api.anthropic.com/v1/messages"
VARSAYILAN_MODEL = "claude-haiku-5-5"
EN_FAZLA_KARAKTER = 600
ZAMAN_ASIMI_SN = 15

SISTEM_TALIMATI = (
    "Sen bir güvenlik operasyon merkezinde çalışan analistsin. Sana bir giriş "
    "anomalisinin özet verisi JSON olarak verilecek. Yalnızca bu veriyi kullanarak "
    "Türkçe, en fazla 3 cümlelik bir özet yaz: ne oldu ve neden şüpheli. Son cümle "
    "'Önerilen adım:' ile başlasın ve tek bir somut öneri içersin. Veride olmayan "
    "hiçbir sayı, saat, kullanıcı adı, ülke veya IP adresi yazma. Maskeli değerleri "
    "(ör. a***, 198.51.100.x) aynen kullan. Başlık, madde işareti veya markdown kullanma."
)


# ---------------------------------------------------------------- maskeleme
def kullanici_maskele(ad):
    """'admin' -> 'a***'. Boşsa '?'."""
    return (ad[0] + "***") if ad else "?"


def ip_maskele(ip):
    """IPv4: son bölüm gizlenir (198.51.100.23 -> 198.51.100.x).
    IPv6: ilk 4 grup kalır (2001:db8:1:2::5 -> 2001:db8:1:2::x)."""
    try:
        adres = ipaddress.ip_address(ip)
    except ValueError:
        return "?"
    if adres.version == 4:
        return ".".join(ip.split(".")[:3]) + ".x"
    gruplar = adres.exploded.split(":")[:4]
    return ":".join(g.lstrip("0") or "0" for g in gruplar) + "::x"


# ---------------------------------------------------------------- veri
def veri_hazirla(anomali):
    """Anomali + kanıt loglarından modele gidecek maskeli özet veriyi çıkarır.
    anomali: crud.anomali_kanitlari() çıktısı."""
    kanitlar = anomali.get("kanitlar") or []
    zamanlar = [k["zaman"] for k in kanitlar]
    kullanicilar = sorted({k["kullanici_adi"] for k in kanitlar if k["kullanici_adi"]})
    veri = {
        "kural": anomali["kural"],
        "kural_turu": anomali["kural_turu"],
        "onem": anomali["onem"],
        "ip": ip_maskele(anomali["ip_adresi"]),
        "olay_sayisi": len(kanitlar),
        "basarisiz": sum(1 for k in kanitlar if k["durum"] == "basarisiz"),
        "basarili": sum(1 for k in kanitlar if k["durum"] == "basarili"),
        "kullanici_sayisi": len(kullanicilar),
        "kullanicilar": [kullanici_maskele(k) for k in kullanicilar[:5]],
    }
    if zamanlar:
        bas, bit = min(zamanlar), max(zamanlar)
        veri.update(
            tarih=bas.strftime("%d.%m.%Y"),
            baslangic=bas.strftime("%H:%M"),
            bitis=bit.strftime("%H:%M"),
            sure_dk=int((bit - bas).total_seconds() // 60),
        )
    return veri


# ---------------------------------------------------------------- kural tabanlı
def kural_tabanli_ozet(v):
    """Yapay zekâ olmadan, şablonla özet yazar. Her zaman çalışır."""
    zaman = f"{v.get('tarih', '')} {v.get('baslangic', '')}-{v.get('bitis', '')}".strip(" -")
    kisiler = ", ".join(v["kullanicilar"]) or "bilinmeyen"
    tur = v["kural_turu"]
    if tur == "cok_basarisiz_giris":
        return (f"{v['ip']} adresinden {zaman} arasında {v['basarisiz']} başarısız giriş "
                f"denemesi yapıldı ({v['kullanici_sayisi']} farklı kullanıcı adı). Kısa sürede bu "
                f"kadar hata, parola tahmin saldırısına işaret eder. Önerilen adım: Bu IP adresini "
                f"geçici olarak engelleyin ve hedef alınan hesapları kontrol edin.")
    if tur == "cok_kullanici_denemesi":
        return (f"{v['ip']} adresinden {zaman} arasında {v['kullanici_sayisi']} farklı kullanıcı "
                f"adıyla giriş denendi ({kisiler}). Bu, geçerli bir hesap bulmaya çalışan tarama "
                f"davranışıdır. Önerilen adım: IP adresini engelleyin ve var olmayan hesaplara "
                f"yapılan denemeleri izleyin.")
    if tur == "basarisizdan_basariya":
        return (f"{v['ip']} adresinden {v['basarisiz']} başarısız denemenin ardından {kisiler} "
                f"hesabıyla başarılı giriş yapıldı ({zaman}). Parola tahmin edilmiş olabilir. "
                f"Önerilen adım: Hesabın açık oturumlarını kapatın, parolasını sıfırlayın ve "
                f"girişi hesap sahibiyle doğrulayın.")
    if tur == "mesai_disi":
        return (f"{kisiler} hesabıyla mesai saatleri dışında ({zaman}) {v['ip']} adresinden "
                f"başarılı giriş yapıldı. Tek başına saldırı değildir ama alışılmadık bir "
                f"davranıştır. Önerilen adım: Girişin hesap sahibine ait olduğunu teyit edin.")
    return (f"{v['ip']} adresiyle ilgili '{v['kural']}' kuralı {v['olay_sayisi']} olay tespit etti. "
            f"Önerilen adım: Kanıt kayıtlarını inceleyin.")


# ---------------------------------------------------------------- yapay zekâ
def llm_ozet(veri):
    """Modelden özet ister. Anahtar yoksa ya da hata olursa None döner."""
    anahtar = os.getenv("ANTHROPIC_API_KEY")
    if not anahtar:
        return None
    govde = {
        "model": os.getenv("AI_MODEL") or VARSAYILAN_MODEL,
        "max_tokens": 300,
        "system": SISTEM_TALIMATI,
        "messages": [{"role": "user", "content": json.dumps(veri, ensure_ascii=False)}],
    }
    istek = Request(
        API_ADRESI,
        data=json.dumps(govde).encode("utf-8"),
        headers={"x-api-key": anahtar, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(istek, timeout=ZAMAN_ASIMI_SN) as yanit:
            cevap = json.loads(yanit.read().decode("utf-8"))
        return "".join(p.get("text", "") for p in cevap.get("content", [])).strip()
    except Exception:
        return None


def dogrula(metin, veri, gercek_kullanicilar=()):
    """Model çıktısını kontrol eder. Geçerse True.
    - boş olmamalı ve çok uzun olmamalı
    - tam IP adresi içermemeli (maskeli olmalı)
    - maskesiz kullanıcı adı içermemeli
    - metindeki her sayı veride de geçmeli (uydurma sayı yok)"""
    if not metin or len(metin) > EN_FAZLA_KARAKTER:
        return False
    if re.search(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", metin):
        return False
    kucuk = metin.lower()
    for ad in gercek_kullanicilar:
        if ad and len(ad) > 2 and re.search(rf"(?<![\w*]){re.escape(ad.lower())}(?![\w*])", kucuk):
            return False
    veri_sayilari = set(re.findall(r"\d+", json.dumps(veri, ensure_ascii=False)))
    metin_sayilari = set(re.findall(r"\d+", metin))
    return metin_sayilari <= veri_sayilari


def ozet_uret(anomali):
    """Anomali için özet döndürür: (metin, kaynak). kaynak 'ai' ya da 'kural'."""
    veri = veri_hazirla(anomali)
    gercek = {k["kullanici_adi"] for k in anomali.get("kanitlar") or []}
    metin = llm_ozet(veri)
    if metin and dogrula(metin, veri, gercek):
        return metin, "ai"
    return kural_tabanli_ozet(veri), "kural"
