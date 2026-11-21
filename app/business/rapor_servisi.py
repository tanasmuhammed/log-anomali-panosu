"""Güvenlik raporu (Hafta 12).

Veri katmanı ham sayıları getirir; bu modül onlardan rapordaki metrikleri
hesaplar: oranlar, önem dağılımı, günlük seri, eğilim (trend), en çok
anomali üreten IP'ler ve kurallar. Hesaplar burada olduğu için veritabanı
olmadan test edilebilir.

Eksik veri: günlük seride kaydı olmayan günler 0 ile doldurulur. Doldurulmazsa
grafikte o gün hiç görünmez ve iki uzak gün yan yana çizilerek eğilim yanlış
okunur.
"""
import csv
import io
from collections import Counter
from datetime import date, datetime, timedelta

from app.data import crud

VARSAYILAN_GUN = 14
EN_UZUN_ARALIK_GUN = 366
ONEM_SIRASI = {"yuksek": 0, "orta": 1, "dusuk": 2}
ONEM_ADI = {"yuksek": "Yüksek", "orta": "Orta", "dusuk": "Düşük"}


# ------------------------------------------------------------ tarih aralığı
def tarih_araligi(baslangic, bitis, bugun=None):
    """Formdan gelen 'YYYY-AA-GG' metinlerini tarihe çevirir ve kontrol eder.

    Boş bırakılırsa son VARSAYILAN_GUN gün kullanılır.
    Dönen değer: (bas_tarih, bit_tarih, hata). İki tarih de dahildir.
    """
    bugun = bugun or date.today()
    try:
        bit = date.fromisoformat(bitis) if bitis else bugun
        bas = date.fromisoformat(baslangic) if baslangic else bit - timedelta(days=VARSAYILAN_GUN - 1)
    except ValueError:
        return None, None, "Tarih biçimi geçersiz."
    if bas > bit:
        return None, None, "Başlangıç tarihi bitiş tarihinden sonra olamaz."
    if (bit - bas).days + 1 > EN_UZUN_ARALIK_GUN:
        return None, None, f"Rapor aralığı en fazla {EN_UZUN_ARALIK_GUN} gün olabilir."
    return bas, bit, None


def sorgu_sinirlari(bas, bit):
    """Tarihleri veritabanı sorgusu için [başlangıç 00:00, bitişten sonraki gün 00:00) yapar."""
    return datetime.combine(bas, datetime.min.time()), datetime.combine(bit + timedelta(days=1), datetime.min.time())


# ------------------------------------------------------------ metrikler
def oran(pay, payda):
    """Yüzde oranı, bir ondalıkla. Payda 0 ise 0 (sıfıra bölme hatası olmaz)."""
    if not payda:
        return 0.0
    return round(100 * pay / payda, 1)


def gunluk_seri(log_gunleri, anomaliler, bas, bit):
    """Her gün için başarılı, başarısız ve anomali sayısı. Eksik günler 0 olur."""
    loglar = {_gun(s["gun"]): s for s in log_gunleri}
    anomali_say = Counter(a["olay_zamani"].date() for a in anomaliler)
    seri = []
    gun = bas
    while gun <= bit:
        s = loglar.get(gun, {})
        seri.append({
            "gun": gun.isoformat(),
            "basarili": s.get("basarili", 0) or 0,
            "basarisiz": s.get("basarisiz", 0) or 0,
            "anomali": anomali_say.get(gun, 0),
        })
        gun += timedelta(days=1)
    return seri


def egilim(seri, alan):
    """Aralığın ikinci yarısını birinci yarısıyla karşılaştırır.

    Örn. 14 günlük raporda son 7 günün başarısız giriş toplamı ilk 7 güne göre
    yüzde kaç arttı ya da azaldı. Tek günlük aralıkta karşılaştırma yapılmaz.
    """
    if len(seri) < 2:
        return {"onceki": None, "sonraki": None, "degisim": None, "yon": "yok"}
    yari = len(seri) // 2
    onceki = sum(g[alan] for g in seri[:yari])
    sonraki = sum(g[alan] for g in seri[-yari:])
    if onceki == 0:
        degisim = None                       # 0'dan artış yüzde olarak ifade edilemez
        yon = "artis" if sonraki > 0 else "sabit"
    else:
        degisim = round(100 * (sonraki - onceki) / onceki)
        yon = "artis" if degisim > 0 else "azalis" if degisim < 0 else "sabit"
    return {"onceki": onceki, "sonraki": sonraki, "degisim": degisim, "yon": yon}


def onem_dagilimi(anomaliler):
    sayac = Counter(a["onem"] for a in anomaliler)
    return {onem: sayac.get(onem, 0) for onem in ("yuksek", "orta", "dusuk")}


def kural_dagilimi(anomaliler):
    """Her kural kaç anomali buldu, önem derecesine göre. Çoktan aza sıralı."""
    tablo = {}
    for a in anomaliler:
        satir = tablo.setdefault(a["kural"], {"kural": a["kural"], "yuksek": 0, "orta": 0, "dusuk": 0, "toplam": 0})
        satir[a["onem"]] += 1
        satir["toplam"] += 1
    return sorted(tablo.values(), key=lambda s: (-s["toplam"], s["kural"]))


def en_cok_ip(anomaliler, adet=10):
    """En çok anomaliye karışan IP adresleri. Önce sayı, eşitse en yüksek önem."""
    tablo = {}
    for a in anomaliler:
        ip = a["ip_adresi"] or "-"
        s = tablo.setdefault(ip, {"ip_adresi": ip, "anomali": 0, "en_yuksek": "dusuk",
                                  "kurallar": set(), "son_olay": a["olay_zamani"],
                                  "konum": _konum(a)})
        s["anomali"] += 1
        s["kurallar"].add(a["kural"])
        if ONEM_SIRASI[a["onem"]] < ONEM_SIRASI[s["en_yuksek"]]:
            s["en_yuksek"] = a["onem"]
        s["son_olay"] = max(s["son_olay"], a["olay_zamani"])
    sirali = sorted(tablo.values(), key=lambda s: (-s["anomali"], ONEM_SIRASI[s["en_yuksek"]], s["ip_adresi"]))
    for s in sirali:
        s["kurallar"] = sorted(s["kurallar"])
    return sirali[:adet]


def _konum(a):
    if a.get("ayrilmis"):
        return "Test/ayrılmış adres"
    if a.get("ulke"):
        return f"{a['sehir']}, {a['ulke']}" if a.get("sehir") else a["ulke"]
    return "Bilinmiyor"


def _gun(deger):
    """Veritabanından gelen günü date nesnesine çevirir (sürücüye göre metin gelebilir)."""
    if isinstance(deger, datetime):
        return deger.date()
    if isinstance(deger, date):
        return deger
    return date.fromisoformat(str(deger)[:10])


# ------------------------------------------------------------ rapor
def rapor_hazirla(sirket_id, bas, bit):
    """Bir şirket ve tarih aralığı için raporun tüm verisini hazırlar."""
    alt, ust = sorgu_sinirlari(bas, bit)
    log_ozeti = crud.rapor_log_ozeti(sirket_id, alt, ust)
    anomaliler = crud.rapor_anomalileri(sirket_id, alt, ust)
    seri = gunluk_seri(crud.rapor_gunluk_loglar(sirket_id, alt, ust), anomaliler, bas, bit)
    onemler = onem_dagilimi(anomaliler)
    return {
        "bas": bas, "bit": bit, "gun_sayisi": (bit - bas).days + 1,
        "ozet": {
            **log_ozeti,
            "basarisiz_orani": oran(log_ozeti["basarisiz"], log_ozeti["toplam"]),
            "anomali": len(anomaliler),
            "yuksek": onemler["yuksek"],
        },
        "onem": onemler,
        "seri": seri,
        "egilim_basarisiz": egilim(seri, "basarisiz"),
        "egilim_anomali": egilim(seri, "anomali"),
        "ipler": en_cok_ip(anomaliler),
        "kurallar": kural_dagilimi(anomaliler),
        "hedefler": crud.rapor_hedef_kullanicilar(sirket_id, alt, ust),
        "anomaliler": sorted(anomaliler, key=lambda a: (ONEM_SIRASI[a["onem"]], a["olay_zamani"])),
    }


# ------------------------------------------------------------ CSV
TEHLIKELI_BASLANGIC = ("=", "+", "-", "@", "\t", "\r")


def _guvenli_hucre(deger):
    """CSV enjeksiyonuna karşı koruma: '=' gibi karakterle başlayan bir değer
    Excel'de formül olarak çalışabilir (ör. log dosyasına yazılmış kötü niyetli
    bir kullanıcı adı). Başına tek tırnak eklenerek düz metin yapılır."""
    if deger is None:
        return ""
    if isinstance(deger, datetime):
        return deger.strftime("%Y-%m-%d %H:%M:%S")
    metin = str(deger)
    return "'" + metin if metin.startswith(TEHLIKELI_BASLANGIC) else metin


def csv_uret(satirlar, kolonlar):
    """Satırlardan CSV metni üretir.
    kolonlar: [(sözlükteki_anahtar, başlık), ...]
    Türkçe Excel için ayraç ';', başta UTF-8 BOM var (Türkçe karakterler bozulmasın)."""
    cikti = io.StringIO()
    yazici = csv.writer(cikti, delimiter=";", lineterminator="\r\n")
    yazici.writerow([baslik for _, baslik in kolonlar])
    for s in satirlar:
        yazici.writerow([_guvenli_hucre(s.get(anahtar)) for anahtar, _ in kolonlar])
    return "﻿" + cikti.getvalue()


ANOMALI_KOLONLARI = [
    ("olay_zamani", "Olay zamanı"), ("onem_adi", "Önem"), ("kural", "Kural"),
    ("ip_adresi", "IP adresi"), ("konum", "Konum"), ("aciklama", "Açıklama"),
    ("kanit_sayisi", "Kanıt log sayısı"), ("ai_ozeti", "Özet"),
]
LOG_KOLONLARI = [
    ("zaman", "Zaman"), ("kaynak", "Kaynak"), ("ip_adresi", "IP adresi"),
    ("kullanici_adi", "Kullanıcı"), ("durum", "Sonuç"),
]


def anomali_csv(anomaliler):
    satirlar = [{**a, "onem_adi": ONEM_ADI[a["onem"]], "konum": _konum(a)} for a in anomaliler]
    return csv_uret(satirlar, ANOMALI_KOLONLARI)


def log_csv(loglar):
    return csv_uret(loglar, LOG_KOLONLARI)
