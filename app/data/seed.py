"""
Sentetik veri üretici (Hafta 4).

KVKK uyumu: Buradaki kullanıcı adları uydurmadır, IP adresleri ise
dokümantasyon için ayrılmış aralıklardan seçilmiştir (192.0.2.x,
198.51.100.x, 203.0.113.x). Gerçek kişi veya kuruma ait veri yoktur.

Hafta 8: Panel kullanıcılarının parolası artık gerçek bcrypt hash'i.
Tüm demo hesapların parolası: demo12345  (sadece sentetik demo verisi için)
Veri yüklendikten sonra her şirket için kurallar çalıştırılır, böylece
pano ilk açılışta anomalileri gösterir.

DİKKAT: Bu betik tüm tabloları SİLİP baştan doldurur.

Çalıştırma (proje klasöründen):
    python -m app.data.seed
"""
import random
from datetime import datetime, timedelta

from app.business.anomali_servisi import anomali_taramasi
from app.business.auth import parola_hashle
from app.data.db import get_connection

random.seed(27)  # her çalıştırmada aynı veri üretilsin

DEMO_PAROLA = "demo12345"

# Silme sırası önemli: önce "çocuk" tablolar, sonra "ebeveyn" tablolar
SILME_SIRASI = ["uyari", "anomali_log", "anomali", "log_kaydi",
                "kural", "kaynak", "kullanici", "sirket"]
IDENTITY_TABLOLARI = ["uyari", "anomali", "log_kaydi",
                      "kural", "kaynak", "kullanici", "sirket"]

SIRKETLER = [
    {
        "ad": "Mavi Lojistik A.Ş.",
        "panel_kullanicilari": [("yonetici_mavi", "yonetici"),
                                ("analist_mavi", "analist")],
        "personel": ["ayse.k", "mehmet.t", "can.y", "zeynep.a", "admin", "burak.s"],
        "kaynaklar": [("Web sunucusu", "web"), ("VPN", "vpn")],
        "hacim": 320,
    },
    {
        "ad": "Yeşil Gıda Ltd.",
        "panel_kullanicilari": [("yonetici_yesil", "yonetici"),
                                ("analist_yesil", "analist")],
        "personel": ["elif.d", "ali.s", "depo", "muhasebe", "admin"],
        "kaynaklar": [("Web sunucusu", "web"), ("Muhasebe uygulaması", "uygulama")],
        "hacim": 180,
    },
]

KURALLAR = [
    # (ad, tür, eşik, pencere_dk)
    ("Çok sayıda başarısız giriş", "cok_basarisiz_giris", 5, 10),
    ("Çok sayıda kullanıcı adı denemesi", "cok_kullanici_denemesi", 5, 15),
    ("Başarısızlıktan sonra başarılı giriş", "basarisizdan_basariya", 5, 30),
    ("Mesai dışı giriş", "mesai_disi", None, None),
]

# Saatlere göre yoğunluk (0-23): mesai saatlerinde daha çok giriş
SAAT_AGIRLIGI = [1, 1, 1, 1, 1, 2, 6, 15, 25, 30, 28, 25,
                 22, 24, 26, 25, 20, 12, 6, 4, 3, 2, 1, 1]


def sifirla(cur):
    """Eski verileri siler ve sayaçları (IDENTITY) sıfırlar."""
    for tablo in SILME_SIRASI:
        cur.execute(f"DELETE FROM {tablo}")
    for tablo in IDENTITY_TABLOLARI:
        cur.execute(f"DBCC CHECKIDENT ('{tablo}', RESEED, 0)")


def satir(sirket_id, kaynak_id, zaman, ip, kullanici, durum):
    """log_kaydi tablosuna eklenecek tek bir satır üretir."""
    ham = f"{zaman:%Y-%m-%d %H:%M:%S} auth {durum} user={kullanici} ip={ip}"
    return (sirket_id, kaynak_id, zaman, ip, kullanici, durum, ham)


def normal_loglar(sirket_id, kaynak_idleri, personel, adet, simdi):
    """Son 24 saate yayılmış, çoğu başarılı olan olağan girişler."""
    ip_haritasi = {kisi: f"192.0.2.{10 + i}" for i, kisi in enumerate(personel)}
    satirlar = []
    for _ in range(adet):
        saat = random.choices(range(24), weights=SAAT_AGIRLIGI)[0]
        zaman = simdi.replace(hour=saat, minute=random.randint(0, 59),
                              second=random.randint(0, 59), microsecond=0)
        if zaman > simdi:
            zaman -= timedelta(days=1)
        kisi = random.choice(personel)
        durum = "basarisiz" if random.random() < 0.04 else "basarili"
        satirlar.append(satir(sirket_id, random.choice(kaynak_idleri),
                              zaman, ip_haritasi[kisi], kisi, durum))
    return satirlar


def saldiri_loglari(sirket_id, web_id, vpn_id, tip, simdi):
    """Kuralların yakalaması gereken şüpheli kalıplar."""
    def an(saat, dakika):
        t = simdi.replace(hour=saat, minute=dakika, second=0, microsecond=0)
        return t - timedelta(days=1) if t > simdi else t

    s = []
    if tip == "A":
        # 1) Kaba kuvvet: 10 dakikadan kısa sürede 12 başarısız giriş
        taban = an(9, 42)
        for i in range(12):
            s.append(satir(sirket_id, vpn_id, taban - timedelta(seconds=40 * i),
                           "203.0.113.45", "admin" if i % 2 == 0 else "root",
                           "basarisiz"))
        # 2) Başarısızlıktan sonra başarılı giriş
        taban = an(3, 5)
        for i in range(12):
            s.append(satir(sirket_id, vpn_id, taban + timedelta(seconds=20 * i),
                           "198.51.100.23", "admin", "basarisiz"))
        s.append(satir(sirket_id, vpn_id, taban + timedelta(minutes=7),
                       "198.51.100.23", "admin", "basarili"))
        # 3) Aynı IP'den çok sayıda farklı kullanıcı adı denemesi
        taban = an(11, 12)
        isimler = ["test", "guest", "oracle", "backup", "user", "info", "sql", "demo"]
        for i, isim in enumerate(isimler):
            s.append(satir(sirket_id, web_id, taban + timedelta(seconds=90 * i),
                           "198.51.100.9", isim, "basarisiz"))
        # 4) Mesai dışı giriş
        s.append(satir(sirket_id, vpn_id, an(2, 5),
                       "203.0.113.77", "ayse.k", "basarili"))
    else:
        taban = an(17, 0)
        for i in range(6):
            s.append(satir(sirket_id, web_id, taban + timedelta(seconds=50 * i),
                           "198.51.100.60", "depo", "basarisiz"))
        s.append(satir(sirket_id, web_id, an(6, 30),
                       "192.0.2.77", "elif.d", "basarili"))
    return s


def ozet(cur):
    print("\nTablo satır sayıları:")
    for tablo in ["sirket", "kullanici", "kaynak", "kural", "log_kaydi", "anomali"]:
        adet = cur.execute(f"SELECT COUNT(*) FROM {tablo}").fetchone()[0]
        print(f"  {tablo:<10} {adet}")


def main():
    simdi = datetime.now().replace(microsecond=0)
    with get_connection() as conn:
        cur = conn.cursor()
        sifirla(cur)
        parola_hash = parola_hashle(DEMO_PAROLA)   # bcrypt yavaş: bir kez hesapla
        sirket_idleri = []

        for sirket, tip in zip(SIRKETLER, ["A", "B"]):
            sirket_id = cur.execute(
                "INSERT INTO sirket (ad) OUTPUT INSERTED.id VALUES (?)",
                sirket["ad"]).fetchone()[0]
            sirket_idleri.append(sirket_id)

            for kadi, rol in sirket["panel_kullanicilari"]:
                cur.execute(
                    "INSERT INTO kullanici (sirket_id, kullanici_adi, parola_hash, rol) "
                    "VALUES (?, ?, ?, ?)",
                    sirket_id, kadi, parola_hash, rol)

            kaynak_idleri = []
            for ad, tur in sirket["kaynaklar"]:
                kid = cur.execute(
                    "INSERT INTO kaynak (sirket_id, ad, tur) OUTPUT INSERTED.id "
                    "VALUES (?, ?, ?)", sirket_id, ad, tur).fetchone()[0]
                kaynak_idleri.append(kid)

            for ad, tur, esik, pencere in KURALLAR:
                cur.execute(
                    "INSERT INTO kural (sirket_id, ad, kural_turu, esik, pencere_dk) "
                    "VALUES (?, ?, ?, ?, ?)", sirket_id, ad, tur, esik, pencere)

            loglar = normal_loglar(sirket_id, kaynak_idleri,
                                   sirket["personel"], sirket["hacim"], simdi)
            loglar += saldiri_loglari(sirket_id, kaynak_idleri[0],
                                      kaynak_idleri[-1], tip, simdi)
            cur.executemany(
                "INSERT INTO log_kaydi "
                "(sirket_id, kaynak_id, zaman, ip_adresi, kullanici_adi, durum, ham_metin) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)", loglar)

        conn.commit()

    # Kurallar ayrı bağlantıyla çalışır, bu yüzden veriler önce commit edildi.
    # ek_islemler=False: ilk yüklemede e-posta gönderilmez.
    for sirket_id in sirket_idleri:
        bulgu, yeni = anomali_taramasi(sirket_id, ek_islemler=False)
        print(f"  Şirket {sirket_id}: {bulgu} bulgu, {yeni} anomali kaydedildi")

    with get_connection() as conn:
        ozet(conn.cursor())
    print(f"\nSentetik veri yüklendi. Demo hesap parolası: {DEMO_PAROLA}")


if __name__ == "__main__":
    main()
