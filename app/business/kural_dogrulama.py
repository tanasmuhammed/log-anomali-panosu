"""Kural editörü için doğrulama (Hafta 11).

Yönetici panelden bir kural eklediğinde ya da değiştirdiğinde, formdan gelen
değerler veritabanına yazılmadan ÖNCE burada kontrol edilir. Hatalı kural
kaydedilirse kural motoru ya hiç çalışmaz ya da her girişi anomali sayar;
bu yüzden kontrol iş katmanındadır.

Veritabanında da CHECK kısıtları vardır (esik > 0, pencere_dk 1-1440).
Bu ikinci bir savunma hattıdır: biri kodu atlasa bile veritabanı hatalı
değeri kabul etmez. Buradaki kontroller ise kullanıcıya anlaşılır bir hata
mesajı gösterebilmek içindir.
"""

# Her kural türü için: ekranda görünen adı ve eşik/pencere isteyip istemediği.
KURAL_TURLERI = {
    "cok_basarisiz_giris": {
        "ad": "Çok sayıda başarısız giriş",
        "aciklama": "Aynı IP'den belirli sürede çok sayıda hatalı giriş (parola tahmini).",
        "esikli": True,
    },
    "cok_kullanici_denemesi": {
        "ad": "Çok sayıda kullanıcı adı denemesi",
        "aciklama": "Aynı IP'nin kısa sürede birçok farklı kullanıcı adını denemesi (hesap taraması).",
        "esikli": True,
    },
    "basarisizdan_basariya": {
        "ad": "Başarısızlıktan sonra başarılı giriş",
        "aciklama": "Art arda hatalı girişlerden sonra aynı IP'den başarılı giriş (parola ele geçmiş olabilir).",
        "esikli": True,
    },
    "mesai_disi": {
        "ad": "Mesai dışı giriş",
        "aciklama": "08:00-18:00 dışında yapılan başarılı giriş. Eşik ve süre kullanmaz.",
        "esikli": False,
    },
}

AD_EN_AZ, AD_EN_FAZLA = 3, 100
ESIK_EN_AZ, ESIK_EN_FAZLA = 2, 1000      # 1 olursa her hatalı giriş alarm olur
PENCERE_EN_AZ, PENCERE_EN_FAZLA = 1, 1440  # en fazla 1 gün (veritabanı kısıtıyla aynı)


def turkce_kucuk(metin):
    """Türkçeye uygun küçük harf. Python'un lower() fonksiyonu "I" harfini "i"
    yapar; Türkçede doğrusu "ı"dır. Bu yüzden "KURALI" ile "kuralı" aynı ad
    sayılmıyordu (Hafta 13'te testle bulunan hata)."""
    return metin.replace("I", "ı").replace("İ", "i").lower()


def _tam_sayi(deger):
    """Formdan gelen metni tam sayıya çevirir. Boşsa veya sayı değilse None."""
    if deger is None:
        return None
    deger = str(deger).strip()
    if not deger:
        return None
    try:
        return int(deger)
    except ValueError:
        return None


def kural_dogrula(ad, kural_turu, esik, pencere_dk, mevcut_adlar=()):
    """Kural bilgilerini kontrol eder.

    mevcut_adlar: şirketin diğer kurallarının adları (aynı ad iki kez olmasın diye).

    Dönen değer: (temiz_kural, hatalar)
      - hatalar boşsa temiz_kural veritabanına yazılabilir.
      - hatalar doluysa her biri kullanıcıya gösterilecek bir cümledir.
    """
    hatalar = []
    ad = (ad or "").strip()

    if len(ad) < AD_EN_AZ:
        hatalar.append(f"Kural adı en az {AD_EN_AZ} karakter olmalı.")
    elif len(ad) > AD_EN_FAZLA:
        hatalar.append(f"Kural adı en fazla {AD_EN_FAZLA} karakter olabilir.")
    elif turkce_kucuk(ad) in {turkce_kucuk(m) for m in mevcut_adlar}:
        hatalar.append("Bu adla bir kural zaten var. Farklı bir ad seçin.")

    tur = KURAL_TURLERI.get(kural_turu)
    if tur is None:
        hatalar.append("Geçerli bir kural türü seçin.")
        return None, hatalar

    if not tur["esikli"]:
        # Mesai dışı kuralı eşik/süre kullanmaz; gelen değerler yok sayılır.
        esik_sayi = pencere_sayi = None
    else:
        esik_sayi = _tam_sayi(esik)
        pencere_sayi = _tam_sayi(pencere_dk)
        if esik_sayi is None:
            hatalar.append("Eşik bir tam sayı olmalı.")
        elif not ESIK_EN_AZ <= esik_sayi <= ESIK_EN_FAZLA:
            hatalar.append(f"Eşik {ESIK_EN_AZ} ile {ESIK_EN_FAZLA} arasında olmalı.")
        if pencere_sayi is None:
            hatalar.append("Süre (dakika) bir tam sayı olmalı.")
        elif not PENCERE_EN_AZ <= pencere_sayi <= PENCERE_EN_FAZLA:
            hatalar.append(f"Süre {PENCERE_EN_AZ} ile {PENCERE_EN_FAZLA} dakika arasında olmalı.")

    if hatalar:
        return None, hatalar
    return {"ad": ad, "kural_turu": kural_turu, "esik": esik_sayi, "pencere_dk": pencere_sayi}, []


def kural_aciklamasi(kural):
    """Kuralı insanın okuyacağı tek cümleye çevirir (listede gösterilir)."""
    if kural.get("kural_turu") == "mesai_disi":
        return "Mesai dışında (08:00-18:00 dışı) yapılan başarılı girişler"
    if kural.get("kural_turu") == "cok_kullanici_denemesi":
        return f"Aynı IP {kural['pencere_dk']} dakika içinde en az {kural['esik']} farklı kullanıcı adı denerse"
    if kural.get("kural_turu") == "basarisizdan_basariya":
        return (f"{kural['pencere_dk']} dakika içinde en az {kural['esik']} hatalı girişten "
                f"sonra başarılı giriş gelirse")
    return f"Aynı IP {kural['pencere_dk']} dakika içinde en az {kural['esik']} hatalı giriş yaparsa"
