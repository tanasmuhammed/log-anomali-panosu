"""Rapor hesaplama testleri (Hafta 12). Veritabanı gerekmez."""
from datetime import date, datetime

from app.business import rapor_servisi as r

D = datetime


def anomali(gun, onem="orta", ip="203.0.113.45", kural="Çok sayıda başarısız giriş"):
    return {"olay_zamani": D(2026, 11, gun, 10, 0), "onem": onem, "ip_adresi": ip, "kural": kural,
            "aciklama": "", "ai_ozeti": None, "kanit_sayisi": 5, "ulke": None, "sehir": None, "ayrilmis": True}


def test_tarih_araligi_varsayilan_son_14_gun():
    bas, bit, hata = r.tarih_araligi(None, None, bugun=date(2026, 11, 21))
    assert hata is None and bit == date(2026, 11, 21) and bas == date(2026, 11, 8)


def test_tarih_araligi_hatalari():
    assert r.tarih_araligi("2026-11-10", "2026-11-01")[2] == "Başlangıç tarihi bitiş tarihinden sonra olamaz."
    assert r.tarih_araligi("21.11.2026", None)[2] == "Tarih biçimi geçersiz."
    assert "en fazla" in r.tarih_araligi("2024-01-01", "2026-01-01")[2]


def test_bitis_gunu_dahil_edilir():
    alt, ust = r.sorgu_sinirlari(date(2026, 11, 1), date(2026, 11, 7))
    assert alt == D(2026, 11, 1) and ust == D(2026, 11, 8)    # 7 Kasım 23:59 da dahil


def test_oran_sifira_bolme_yapmaz():
    assert r.oran(0, 0) == 0.0
    assert r.oran(1, 3) == 33.3


def test_eksik_gunler_sifirla_doldurulur():
    log_gunleri = [{"gun": date(2026, 11, 1), "basarili": 5, "basarisiz": 1},
                   {"gun": "2026-11-03", "basarili": 2, "basarisiz": 4}]     # sürücü metin döndürebilir
    seri = r.gunluk_seri(log_gunleri, [anomali(3), anomali(3)], date(2026, 11, 1), date(2026, 11, 3))
    assert [g["gun"] for g in seri] == ["2026-11-01", "2026-11-02", "2026-11-03"]
    assert seri[1] == {"gun": "2026-11-02", "basarili": 0, "basarisiz": 0, "anomali": 0}
    assert seri[2]["anomali"] == 2


def test_egilim():
    seri = [{"x": v} for v in [1, 1, 3, 3]]
    assert r.egilim(seri, "x") == {"onceki": 2, "sonraki": 6, "degisim": 200, "yon": "artis"}
    assert r.egilim([{"x": 4}, {"x": 2}], "x")["yon"] == "azalis"
    assert r.egilim([{"x": 0}, {"x": 5}], "x") == {"onceki": 0, "sonraki": 5, "degisim": None, "yon": "artis"}
    assert r.egilim([{"x": 5}], "x")["yon"] == "yok"           # tek gün: karşılaştırma yok


def test_en_cok_ip_sayiya_sonra_oneme_gore():
    liste = [anomali(1, "dusuk", "192.0.2.1"), anomali(2, "dusuk", "192.0.2.1"),
             anomali(3, "yuksek", "198.51.100.9"), anomali(4, "orta", "198.51.100.8")]
    ipler = r.en_cok_ip(liste)
    assert [i["ip_adresi"] for i in ipler] == ["192.0.2.1", "198.51.100.9", "198.51.100.8"]
    assert ipler[0]["anomali"] == 2 and ipler[1]["en_yuksek"] == "yuksek"


def test_kural_ve_onem_dagilimi():
    liste = [anomali(1, "yuksek"), anomali(1, "orta"), anomali(2, "dusuk", kural="Mesai dışı giriş")]
    assert r.onem_dagilimi(liste) == {"yuksek": 1, "orta": 1, "dusuk": 1}
    k = r.kural_dagilimi(liste)
    assert k[0]["kural"] == "Çok sayıda başarısız giriş" and k[0]["toplam"] == 2


def test_csv_turkce_excel_uyumlu():
    metin = r.log_csv([{"zaman": D(2026, 11, 1, 9, 5), "kaynak": "VPN", "ip_adresi": "192.0.2.1",
                        "kullanici_adi": "ayşe", "durum": "basarili"}])
    assert metin.startswith("﻿")                        # BOM: Türkçe karakter bozulmaz
    satirlar = metin.lstrip("﻿").splitlines()
    assert satirlar[0] == "Zaman;Kaynak;IP adresi;Kullanıcı;Sonuç"
    assert satirlar[1] == "2026-11-01 09:05:00;VPN;192.0.2.1;ayşe;basarili"


def test_csv_formul_enjeksiyonu_engellenir():
    metin = r.log_csv([{"zaman": None, "kaynak": "VPN", "ip_adresi": "1.1.1.1",
                        "kullanici_adi": "=HYPERLINK(\"http://kotu.site\")", "durum": "basarisiz"}])
    assert "'=HYPERLINK" in metin and ";=HYPERLINK" not in metin and '"=HYPERLINK' not in metin
