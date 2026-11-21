"""
Veri erişim katmanı: CRUD fonksiyonları.

Temel kural: Her fonksiyon sirket_id alır ve SQL'de sirket_id ile filtreler.
Böylece bir şirket başka bir şirketin verisini okuyamaz, değiştiremez, silemez.

Tüm sorgular parametrelidir (?). Değerler SQL metnine yapıştırılmaz,
ayrı gönderilir. Bu, SQL injection saldırılarını engeller.
"""
from contextlib import contextmanager

import pyodbc

from app.data.db import get_connection

GECERLI_DURUMLAR = ("basarili", "basarisiz")

# Yeni kayıt olan her şirkete otomatik eklenen kurallar: (ad, tür, eşik, pencere_dk)
VARSAYILAN_KURALLAR = [
    ("Çok sayıda başarısız giriş", "cok_basarisiz_giris", 5, 10),
    ("Çok sayıda kullanıcı adı denemesi", "cok_kullanici_denemesi", 5, 15),
    ("Başarısızlıktan sonra başarılı giriş", "basarisizdan_basariya", 5, 30),
    ("Mesai dışı giriş", "mesai_disi", None, None),
]


@contextmanager
def _oturum():
    """Bağlantı açar. Hata yoksa commit, hata varsa rollback yapar ve kapatır."""
    conn = get_connection()
    try:
        yield conn.cursor()
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _sozluk_listesi(cur):
    """Sorgu sonucunu [{kolon: değer}, ...] biçimine çevirir."""
    kolonlar = [k[0] for k in cur.description]
    return [dict(zip(kolonlar, satir)) for satir in cur.fetchall()]


# ====================== CREATE ======================

def log_ekle(sirket_id, kaynak_id, zaman, ip_adresi, kullanici_adi,
             durum, ham_metin=None):
    """Yeni bir giriş kaydı ekler ve yeni kaydın id'sini döndürür.

    Kaynağın bu şirkete ait olup olmadığı SQL içinde kontrol edilir.
    Başka şirketin kaynağı verilirse hiçbir satır eklenmez ve hata fırlatılır.
    """
    if durum not in GECERLI_DURUMLAR:
        raise ValueError(f"durum şunlardan biri olmalı: {GECERLI_DURUMLAR}")

    sql = """
        INSERT INTO log_kaydi
            (sirket_id, kaynak_id, zaman, ip_adresi, kullanici_adi, durum, ham_metin)
        OUTPUT INSERTED.id
        SELECT k.sirket_id, k.id, ?, ?, ?, ?, ?
        FROM kaynak k
        WHERE k.id = ? AND k.sirket_id = ?
    """
    with _oturum() as cur:
        satir = cur.execute(sql, zaman, ip_adresi, kullanici_adi, durum,
                            ham_metin, kaynak_id, sirket_id).fetchone()
        if satir is None:
            raise ValueError("Bu kaynak bu şirkete ait değil.")
        return satir[0]


def kural_ekle(sirket_id, ad, kural_turu, esik=None, pencere_dk=None):
    """Şirkete yeni bir anomali kuralı ekler ve id'sini döndürür."""
    sql = """
        INSERT INTO kural (sirket_id, ad, kural_turu, esik, pencere_dk)
        OUTPUT INSERTED.id
        VALUES (?, ?, ?, ?, ?)
    """
    with _oturum() as cur:
        return cur.execute(sql, sirket_id, ad, kural_turu,
                           esik, pencere_dk).fetchone()[0]


# ======================= READ =======================

def son_loglar(sirket_id, adet=20):
    """Şirketin en yeni giriş kayıtlarını döndürür."""
    sql = """
        SELECT TOP (?) l.id, l.sirket_id, l.zaman, l.ip_adresi,
               l.kullanici_adi, l.durum, k.ad AS kaynak
        FROM log_kaydi l
        JOIN kaynak k ON k.id = l.kaynak_id
        WHERE l.sirket_id = ?
        ORDER BY l.zaman DESC
    """
    with _oturum() as cur:
        cur.execute(sql, adet, sirket_id)
        return _sozluk_listesi(cur)


def basarisiz_giris_ozeti(sirket_id, dakika=1440, en_az=1):
    """Son 'dakika' içindeki başarısız girişleri IP'ye göre özetler.

    Her IP için: başarısız sayısı, denenen farklı kullanıcı sayısı, son deneme.
    """
    sql = """
        SELECT ip_adresi,
               COUNT(*)                      AS basarisiz_sayisi,
               COUNT(DISTINCT kullanici_adi) AS farkli_kullanici,
               MAX(zaman)                    AS son_deneme
        FROM log_kaydi
        WHERE sirket_id = ?
          AND durum = 'basarisiz'
          AND zaman >= DATEADD(MINUTE, ?, SYSDATETIME())
        GROUP BY ip_adresi
        HAVING COUNT(*) >= ?
        ORDER BY basarisiz_sayisi DESC
    """
    with _oturum() as cur:
        cur.execute(sql, sirket_id, -dakika, en_az)
        return _sozluk_listesi(cur)


def kurallari_getir(sirket_id):
    """Şirketin tüm kurallarını döndürür."""
    sql = """
        SELECT id, ad, kural_turu, esik, pencere_dk, aktif
        FROM kural
        WHERE sirket_id = ?
        ORDER BY id
    """
    with _oturum() as cur:
        cur.execute(sql, sirket_id)
        return _sozluk_listesi(cur)


# ====================== UPDATE ======================

def kural_guncelle(sirket_id, kural_id, esik, pencere_dk):
    """Bir kuralın eşik ve zaman penceresini günceller.

    Dönen sayı etkilenen satır sayısıdır:
    1 = güncellendi, 0 = kural yok veya başka şirkete ait.
    """
    sql = """
        UPDATE kural
        SET esik = ?, pencere_dk = ?
        WHERE id = ? AND sirket_id = ?
    """
    with _oturum() as cur:
        return cur.execute(sql, esik, pencere_dk, kural_id, sirket_id).rowcount


def kural_getir(sirket_id, kural_id):
    """Tek bir kuralı döndürür. Kural yoksa veya başka şirkete aitse None."""
    with _oturum() as cur:
        cur.execute("SELECT id, ad, kural_turu, esik, pencere_dk, aktif FROM kural "
                    "WHERE id = ? AND sirket_id = ?", kural_id, sirket_id)
        satirlar = _sozluk_listesi(cur)
        return satirlar[0] if satirlar else None


def kurallar_ozetli(sirket_id):
    """Kural editörü listesi için: her kural ve bugüne kadar bulduğu anomali sayısı."""
    sql = """
        SELECT k.id, k.ad, k.kural_turu, k.esik, k.pencere_dk, k.aktif,
               (SELECT COUNT(*) FROM anomali a WHERE a.kural_id = k.id) AS anomali_sayisi
        FROM kural k
        WHERE k.sirket_id = ?
        ORDER BY k.id
    """
    with _oturum() as cur:
        cur.execute(sql, sirket_id)
        return _sozluk_listesi(cur)


def kural_duzenle(sirket_id, kural_id, ad, esik, pencere_dk):
    """Kuralın adını, eşiğini ve süresini değiştirir (Hafta 11, kural editörü).
    Kural türü değiştirilmez: türü değişen kural aslında başka bir kuraldır ve
    eski anomalilerin anlamı bozulur. Dönen değer 1 (güncellendi) veya 0."""
    sql = """
        UPDATE kural SET ad = ?, esik = ?, pencere_dk = ?
        WHERE id = ? AND sirket_id = ?
    """
    with _oturum() as cur:
        return cur.execute(sql, ad, esik, pencere_dk, kural_id, sirket_id).rowcount


def kural_aktiflik_degistir(sirket_id, kural_id, aktif):
    """Kuralı aktif (1) veya pasif (0) yapar. Pasif kural taramada çalışmaz."""
    sql = "UPDATE kural SET aktif = ? WHERE id = ? AND sirket_id = ?"
    with _oturum() as cur:
        return cur.execute(sql, 1 if aktif else 0, kural_id, sirket_id).rowcount


# ====================== DELETE ======================

def kural_sil(sirket_id, kural_id):
    """Bir kuralı siler. Dönen sayı etkilenen satır sayısıdır (1 veya 0).

    Kurala bağlı anomali kaydı varsa yabancı anahtar kısıtı silmeye izin vermez.
    """
    sql = "DELETE FROM kural WHERE id = ? AND sirket_id = ?"
    try:
        with _oturum() as cur:
            return cur.execute(sql, kural_id, sirket_id).rowcount
    except pyodbc.IntegrityError:
        raise ValueError("Bu kurala bağlı anomali kayıtları var, silinemez. "
                         "Kuralı pasif yaparak çalışmasını durdurabilirsiniz.")


# ====================== KULLANICI ======================

def sirket_ve_yonetici_ekle(sirket_adi, kullanici_adi, parola_hash):
    """Yeni şirketi, yöneticisini ve varsayılan kurallarını AYNI işlemde ekler.

    Biri başarısız olursa hepsi geri alınır (sahipsiz şirket kalmaz).
    """
    try:
        with _oturum() as cur:
            sirket_id = cur.execute(
                "INSERT INTO sirket (ad) OUTPUT INSERTED.id VALUES (?)",
                sirket_adi).fetchone()[0]
            cur.execute(
                "INSERT INTO kullanici (sirket_id, kullanici_adi, parola_hash, rol) "
                "VALUES (?, ?, ?, 'yonetici')",
                sirket_id, kullanici_adi, parola_hash)
            cur.executemany(
                "INSERT INTO kural (sirket_id, ad, kural_turu, esik, pencere_dk) "
                "VALUES (?, ?, ?, ?, ?)",
                [(sirket_id, ad, tur, esik, pencere) for ad, tur, esik, pencere in VARSAYILAN_KURALLAR])
            return sirket_id
    except pyodbc.IntegrityError:
        raise ValueError("Bu şirket adı veya kullanıcı adı zaten kayıtlı.")


def kullanici_getir(kullanici_adi):
    """Giriş için kullanıcıyı bulur. Yoksa None döndürür.

    Burada sirket_id filtresi yok: giriş yapan kişinin şirketini henüz
    bilmiyoruz, onu bu sorgu bulacak. kullanici_adi tüm sistemde benzersizdir.
    """
    sql = """
        SELECT k.id, k.sirket_id, k.kullanici_adi, k.parola_hash, k.rol,
               s.ad AS sirket_adi
        FROM kullanici k
        JOIN sirket s ON s.id = k.sirket_id
        WHERE k.kullanici_adi = ?
    """
    with _oturum() as cur:
        cur.execute(sql, kullanici_adi)
        satirlar = _sozluk_listesi(cur)
    return satirlar[0] if satirlar else None


# ====================== KAYNAK VE TOPLU LOG ======================

def kaynaklari_getir(sirket_id):
    """Şirketin log kaynaklarını döndürür."""
    sql = "SELECT id, ad, tur FROM kaynak WHERE sirket_id = ? ORDER BY ad"
    with _oturum() as cur:
        cur.execute(sql, sirket_id)
        return _sozluk_listesi(cur)


def kaynak_ekle(sirket_id, ad, tur=None):
    """Şirkete yeni bir log kaynağı ekler ve id'sini döndürür."""
    sql = "INSERT INTO kaynak (sirket_id, ad, tur) OUTPUT INSERTED.id VALUES (?, ?, ?)"
    with _oturum() as cur:
        return cur.execute(sql, sirket_id, ad, tur).fetchone()[0]


def loglar_toplu_ekle(sirket_id, kaynak_id, kayitlar):
    """Ayrıştırılmış kayıtları TEK işlemde ekler.

    İş kuralı: aynı kaynakta aynı zaman + IP + kullanıcı + durum
    zaten varsa o kayıt tekrar eklenmez (aynı dosya iki kez yüklenirse
    sahte anomali oluşmasın).
    Dönen değer: (eklenen_sayisi, atlanan_tekrar_sayisi)
    """
    with _oturum() as cur:
        sahip = cur.execute(
            "SELECT 1 FROM kaynak WHERE id = ? AND sirket_id = ?",
            kaynak_id, sirket_id).fetchone()
        if sahip is None:
            raise ValueError("Bu kaynak bu şirkete ait değil.")
        if not kayitlar:
            return 0, 0

        en_eski = min(k["zaman"] for k in kayitlar)
        en_yeni = max(k["zaman"] for k in kayitlar)
        cur.execute(
            "SELECT zaman, ip_adresi, kullanici_adi, durum FROM log_kaydi "
            "WHERE sirket_id = ? AND kaynak_id = ? AND zaman BETWEEN ? AND ?",
            sirket_id, kaynak_id, en_eski, en_yeni)
        mevcut = {tuple(satir) for satir in cur.fetchall()}

        yeniler = []
        for k in kayitlar:
            anahtar = (k["zaman"], k["ip_adresi"], k["kullanici_adi"], k["durum"])
            if anahtar not in mevcut:
                mevcut.add(anahtar)
                yeniler.append(k)

        if yeniler:
            cur.executemany(
                "INSERT INTO log_kaydi "
                "(sirket_id, kaynak_id, zaman, ip_adresi, kullanici_adi, durum, ham_metin) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(sirket_id, kaynak_id, k["zaman"], k["ip_adresi"],
                  k["kullanici_adi"], k["durum"], k["ham_metin"]) for k in yeniler])
        return len(yeniler), len(kayitlar) - len(yeniler)


# ====================== ANOMALİ ======================

def loglari_getir(sirket_id):
    """Kural motoru için şirketin tüm giriş kayıtlarını zamana göre sıralı döndürür."""
    sql = """
        SELECT id, zaman, ip_adresi, kullanici_adi, durum
        FROM log_kaydi
        WHERE sirket_id = ?
        ORDER BY zaman
    """
    with _oturum() as cur:
        cur.execute(sql, sirket_id)
        return _sozluk_listesi(cur)


def anomalileri_kaydet(sirket_id, bulgular):
    """Kural motorunun bulgularını anomali, anomali_log ve uyari tablolarına
    TEK işlemde yazar. Dönen değer: yeni kaydedilen anomalilerin id listesi
    (Hafta 9: e-posta ve özet için hangi anomalilerin yeni olduğu gerekiyor).

    İş kuralı: bir bulgunun kanıt log kayıtlarından biri, AYNI kural tarafından
    zaten bir anomaliye bağlanmışsa o bulgu tekrar kaydedilmez. Böylece tarama
    her çalıştığında aynı saldırı için yeni uyarı üretilmez.
    """
    if not bulgular:
        return []
    with _oturum() as cur:
        cur.execute(
            "SELECT a.kural_id, al.log_id FROM anomali a "
            "JOIN anomali_log al ON al.anomali_id = a.id "
            "WHERE a.sirket_id = ?", sirket_id)
        kullanilmis = {(satir[0], satir[1]) for satir in cur.fetchall()}

        yeni_idler = []
        for b in bulgular:
            if any((b["kural_id"], log_id) in kullanilmis for log_id in b["log_idler"]):
                continue
            anomali_id = cur.execute(
                "INSERT INTO anomali (sirket_id, kural_id, ip_adresi, onem, aciklama) "
                "OUTPUT INSERTED.id VALUES (?, ?, ?, ?, ?)",
                sirket_id, b["kural_id"], b["ip_adresi"], b["onem"], b["aciklama"]).fetchone()[0]
            cur.executemany(
                "INSERT INTO anomali_log (anomali_id, log_id) VALUES (?, ?)",
                [(anomali_id, log_id) for log_id in b["log_idler"]])
            cur.execute("INSERT INTO uyari (anomali_id, kanal) VALUES (?, 'panel')", anomali_id)
            kullanilmis.update((b["kural_id"], log_id) for log_id in b["log_idler"])
            yeni_idler.append(anomali_id)
        return yeni_idler


def anomalileri_getir(sirket_id, adet=20):
    """Şirketin anomalilerini önem sırasına göre döndürür (önce yüksek).
    Hafta 9: IP konumu (ip_konum tablosundan) ve kanıt sayısı eklendi.
    Hafta 10: yapay zekâ / kural tabanlı özet eklendi."""
    sql = """
        SELECT TOP (?) a.id, a.ip_adresi, a.onem, a.aciklama, a.ai_ozeti, a.ai_ozet_kaynagi,
               k.ad AS kural, k.kural_turu,
               ik.ulke, ik.sehir, ik.kurulus, ik.ayrilmis,
               (SELECT MIN(l.zaman)
                  FROM anomali_log al
                  JOIN log_kaydi l ON l.id = al.log_id
                 WHERE al.anomali_id = a.id) AS olay_zamani,
               (SELECT COUNT(*) FROM anomali_log al
                 WHERE al.anomali_id = a.id) AS kanit_sayisi
        FROM anomali a
        JOIN kural k ON k.id = a.kural_id
        LEFT JOIN ip_konum ik ON ik.ip_adresi = a.ip_adresi
        WHERE a.sirket_id = ?
        ORDER BY CASE a.onem WHEN 'yuksek' THEN 0 WHEN 'orta' THEN 1 ELSE 2 END, a.id DESC
    """
    with _oturum() as cur:
        cur.execute(sql, adet, sirket_id)
        return _sozluk_listesi(cur)


def anomali_kanitlari(sirket_id, anomali_id):
    """Bir anomaliyi ve ona bağlı (kanıt) log kayıtlarını döndürür.
    E-posta bildirimi ve özet üretimi bu veriyi kullanır.
    Anomali bu şirkete ait değilse None döner."""
    with _oturum() as cur:
        cur.execute(
            "SELECT a.id, a.ip_adresi, a.onem, a.aciklama, k.ad AS kural, k.kural_turu "
            "FROM anomali a JOIN kural k ON k.id = a.kural_id "
            "WHERE a.id = ? AND a.sirket_id = ?", anomali_id, sirket_id)
        satirlar = _sozluk_listesi(cur)
        if not satirlar:
            return None
        anomali = satirlar[0]
        cur.execute(
            "SELECT l.zaman, l.ip_adresi, l.kullanici_adi, l.durum "
            "FROM anomali_log al JOIN log_kaydi l ON l.id = al.log_id "
            "WHERE al.anomali_id = ? AND l.sirket_id = ? ORDER BY l.zaman",
            anomali_id, sirket_id)
        anomali["kanitlar"] = _sozluk_listesi(cur)
        return anomali


def uyari_ekle(anomali_id, kanal):
    """Gönderilen bir uyarıyı kaydeder (ör. kanal='eposta')."""
    with _oturum() as cur:
        cur.execute("INSERT INTO uyari (anomali_id, kanal) VALUES (?, ?)", anomali_id, kanal)


# ====================== IP KONUM ÖNBELLEĞİ (Hafta 9) ======================
# ip_konum tablosu şirkete özel değildir: bir IP'nin konumu herkes için aynıdır.
# Kişisel veri tutmaz; sadece IP adresinin hangi ülke/kuruma ait olduğunu saklar.

def ip_konum_getir(ip_adresi):
    with _oturum() as cur:
        cur.execute("SELECT ip_adresi, ulke, sehir, kurulus, ayrilmis "
                    "FROM ip_konum WHERE ip_adresi = ?", ip_adresi)
        satirlar = _sozluk_listesi(cur)
        return satirlar[0] if satirlar else None


def ip_konum_kaydet(konum):
    """Konumu kaydeder; IP zaten varsa günceller."""
    with _oturum() as cur:
        cur.execute(
            "UPDATE ip_konum SET ulke = ?, sehir = ?, kurulus = ?, ayrilmis = ?, "
            "guncelleme = SYSDATETIME() WHERE ip_adresi = ?",
            konum["ulke"], konum["sehir"], konum["kurulus"], konum["ayrilmis"], konum["ip_adresi"])
        if cur.rowcount == 0:
            cur.execute(
                "INSERT INTO ip_konum (ip_adresi, ulke, sehir, kurulus, ayrilmis) "
                "VALUES (?, ?, ?, ?, ?)",
                konum["ip_adresi"], konum["ulke"], konum["sehir"], konum["kurulus"], konum["ayrilmis"])


# ====================== ÖZET (Hafta 10) ======================

def anomali_ozet_kaydet(sirket_id, anomali_id, metin, kaynak):
    """Anomalinin özetini yazar. kaynak: 'ai' (yapay zekâ) veya 'kural' (şablon)."""
    with _oturum() as cur:
        cur.execute("UPDATE anomali SET ai_ozeti = ?, ai_ozet_kaynagi = ? "
                    "WHERE id = ? AND sirket_id = ?", metin, kaynak, anomali_id, sirket_id)


def ozetsiz_anomaliler(sirket_id):
    """Henüz özeti olmayan anomalilerin id listesi."""
    with _oturum() as cur:
        cur.execute("SELECT id FROM anomali WHERE sirket_id = ? AND ai_ozeti IS NULL "
                    "ORDER BY id", sirket_id)
        return [satir[0] for satir in cur.fetchall()]

# ====================== PANO ======================

def pano_ozeti(sirket_id):
    """Panodaki sayı kartları için şirketin özet sayılarını döndürür."""
    sql = """
        SELECT
            (SELECT COUNT(*) FROM log_kaydi WHERE sirket_id = ?)                          AS toplam_log,
            (SELECT COUNT(*) FROM log_kaydi WHERE sirket_id = ? AND durum = 'basarisiz')  AS basarisiz,
            (SELECT COUNT(*) FROM anomali   WHERE sirket_id = ?)                          AS anomali,
            (SELECT COUNT(*) FROM anomali   WHERE sirket_id = ? AND onem = 'yuksek')      AS yuksek
    """
    with _oturum() as cur:
        cur.execute(sql, sirket_id, sirket_id, sirket_id, sirket_id)
        return _sozluk_listesi(cur)[0]


def saatlik_dagilim(sirket_id):
    """Girişlerin günün saatlerine (0-23) göre başarılı/başarısız dağılımı.
    Kaydı olmayan saatler 0 ile doldurulur, liste her zaman 24 elemanlıdır."""
    sql = """
        SELECT DATEPART(HOUR, zaman) AS saat,
               SUM(CASE WHEN durum = 'basarili'  THEN 1 ELSE 0 END) AS basarili,
               SUM(CASE WHEN durum = 'basarisiz' THEN 1 ELSE 0 END) AS basarisiz
        FROM log_kaydi
        WHERE sirket_id = ?
        GROUP BY DATEPART(HOUR, zaman)
    """
    with _oturum() as cur:
        cur.execute(sql, sirket_id)
        satirlar = {s["saat"]: s for s in _sozluk_listesi(cur)}
    return [satirlar.get(h, {"saat": h, "basarili": 0, "basarisiz": 0}) for h in range(24)]


def kural_dagilimi(sirket_id):
    """Panodaki grafik için: her kural kaç anomali buldu, önem derecesine göre.
    Hiç anomali bulmamış kurallar listede yer almaz."""
    sql = """
        SELECT k.ad AS kural,
               SUM(CASE WHEN a.onem = 'yuksek' THEN 1 ELSE 0 END) AS yuksek,
               SUM(CASE WHEN a.onem = 'orta'   THEN 1 ELSE 0 END) AS orta,
               SUM(CASE WHEN a.onem = 'dusuk'  THEN 1 ELSE 0 END) AS dusuk,
               COUNT(*) AS toplam
        FROM anomali a
        JOIN kural k ON k.id = a.kural_id
        WHERE a.sirket_id = ?
        GROUP BY k.ad
        ORDER BY toplam DESC
    """
    with _oturum() as cur:
        cur.execute(sql, sirket_id)
        return _sozluk_listesi(cur)


# ====================== RAPOR (Hafta 12) ======================
# Tüm rapor sorguları [baslangic, bitis) aralığında çalışır: başlangıç dahil,
# bitiş hariç. Böylece "1-7 Kasım" raporu 7 Kasım 23:59'a kadar her şeyi kapsar
# (bitiş olarak 8 Kasım 00:00 verilir).

def rapor_log_ozeti(sirket_id, baslangic, bitis):
    """Aralıktaki giriş sayıları: toplam, başarısız, farklı IP, farklı kullanıcı."""
    sql = """
        SELECT COUNT(*) AS toplam,
               SUM(CASE WHEN durum = 'basarisiz' THEN 1 ELSE 0 END) AS basarisiz,
               COUNT(DISTINCT ip_adresi) AS farkli_ip,
               COUNT(DISTINCT kullanici_adi) AS farkli_kullanici
        FROM log_kaydi
        WHERE sirket_id = ? AND zaman >= ? AND zaman < ?
    """
    with _oturum() as cur:
        cur.execute(sql, sirket_id, baslangic, bitis)
        sonuc = _sozluk_listesi(cur)[0]
    sonuc["basarisiz"] = sonuc["basarisiz"] or 0   # hiç kayıt yoksa SUM NULL döner
    return sonuc


def rapor_gunluk_loglar(sirket_id, baslangic, bitis):
    """Aralıktaki girişlerin günlere göre başarılı/başarısız sayıları.
    Kaydı olmayan günler burada yoktur; iş katmanı onları 0 ile doldurur."""
    sql = """
        SELECT CAST(zaman AS DATE) AS gun,
               SUM(CASE WHEN durum = 'basarili'  THEN 1 ELSE 0 END) AS basarili,
               SUM(CASE WHEN durum = 'basarisiz' THEN 1 ELSE 0 END) AS basarisiz
        FROM log_kaydi
        WHERE sirket_id = ? AND zaman >= ? AND zaman < ?
        GROUP BY CAST(zaman AS DATE)
        ORDER BY gun
    """
    with _oturum() as cur:
        cur.execute(sql, sirket_id, baslangic, bitis)
        return _sozluk_listesi(cur)


def rapor_anomalileri(sirket_id, baslangic, bitis):
    """Olay zamanı aralığa düşen anomaliler (olay zamanı = kanıt loglarının ilki).
    Rapordaki IP, kural ve önem dağılımları bu listeden hesaplanır."""
    sql = """
        WITH olaylar AS (
            SELECT al.anomali_id, MIN(l.zaman) AS olay_zamani, COUNT(*) AS kanit_sayisi
            FROM anomali_log al
            JOIN log_kaydi l ON l.id = al.log_id
            WHERE l.sirket_id = ?
            GROUP BY al.anomali_id
        )
        SELECT a.id, o.olay_zamani, k.ad AS kural, a.onem, a.ip_adresi, a.aciklama,
               a.ai_ozeti, o.kanit_sayisi, ik.ulke, ik.sehir, ik.ayrilmis
        FROM anomali a
        JOIN olaylar o ON o.anomali_id = a.id
        JOIN kural k ON k.id = a.kural_id
        LEFT JOIN ip_konum ik ON ik.ip_adresi = a.ip_adresi
        WHERE a.sirket_id = ? AND o.olay_zamani >= ? AND o.olay_zamani < ?
        ORDER BY o.olay_zamani
    """
    with _oturum() as cur:
        cur.execute(sql, sirket_id, sirket_id, baslangic, bitis)
        return _sozluk_listesi(cur)


def rapor_hedef_kullanicilar(sirket_id, baslangic, bitis, adet=10):
    """Aralıkta en çok başarısız giriş denenen kullanıcı adları."""
    sql = """
        SELECT TOP (?) kullanici_adi, COUNT(*) AS basarisiz,
               COUNT(DISTINCT ip_adresi) AS farkli_ip
        FROM log_kaydi
        WHERE sirket_id = ? AND durum = 'basarisiz' AND zaman >= ? AND zaman < ?
        GROUP BY kullanici_adi
        ORDER BY basarisiz DESC, kullanici_adi
    """
    with _oturum() as cur:
        cur.execute(sql, adet, sirket_id, baslangic, bitis)
        return _sozluk_listesi(cur)


def loglari_aralikta(sirket_id, baslangic, bitis, adet=50000):
    """CSV dışa aktarma için aralıktaki log kayıtları (en fazla 'adet' satır)."""
    sql = """
        SELECT TOP (?) l.zaman, k.ad AS kaynak, l.ip_adresi, l.kullanici_adi, l.durum
        FROM log_kaydi l
        JOIN kaynak k ON k.id = l.kaynak_id
        WHERE l.sirket_id = ? AND l.zaman >= ? AND l.zaman < ?
        ORDER BY l.zaman
    """
    with _oturum() as cur:
        cur.execute(sql, adet, sirket_id, baslangic, bitis)
        return _sozluk_listesi(cur)
