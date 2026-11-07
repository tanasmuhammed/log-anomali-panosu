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
        raise ValueError("Bu kurala bağlı anomali kayıtları var, silinemez.")


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
    TEK işlemde yazar. Dönen değer: yeni kaydedilen anomali sayısı.

    İş kuralı: bir bulgunun kanıt log kayıtlarından biri, AYNI kural tarafından
    zaten bir anomaliye bağlanmışsa o bulgu tekrar kaydedilmez. Böylece tarama
    her çalıştığında aynı saldırı için yeni uyarı üretilmez.
    """
    if not bulgular:
        return 0
    with _oturum() as cur:
        cur.execute(
            "SELECT a.kural_id, al.log_id FROM anomali a "
            "JOIN anomali_log al ON al.anomali_id = a.id "
            "WHERE a.sirket_id = ?", sirket_id)
        kullanilmis = {(satir[0], satir[1]) for satir in cur.fetchall()}

        yeni = 0
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
            yeni += 1
        return yeni


def anomalileri_getir(sirket_id, adet=20):
    """Şirketin anomalilerini önem sırasına göre döndürür (önce yüksek)."""
    sql = """
        SELECT TOP (?) a.id, a.ip_adresi, a.onem, a.aciklama, k.ad AS kural,
               (SELECT MIN(l.zaman)
                  FROM anomali_log al
                  JOIN log_kaydi l ON l.id = al.log_id
                 WHERE al.anomali_id = a.id) AS olay_zamani
        FROM anomali a
        JOIN kural k ON k.id = a.kural_id
        WHERE a.sirket_id = ?
        ORDER BY CASE a.onem WHEN 'yuksek' THEN 0 WHEN 'orta' THEN 1 ELSE 2 END, a.id DESC
    """
    with _oturum() as cur:
        cur.execute(sql, adet, sirket_id)
        return _sozluk_listesi(cur)

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
