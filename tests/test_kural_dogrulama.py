"""Kural editörü doğrulama testleri (Hafta 11). Veritabanı gerekmez."""
import pytest

from app.business.kural_dogrulama import kural_aciklamasi, kural_dogrula


def test_gecerli_kural_temizlenir():
    kural, hatalar = kural_dogrula("  VPN kaba kuvvet ", "cok_basarisiz_giris", "8", "15")
    assert hatalar == []
    assert kural == {"ad": "VPN kaba kuvvet", "kural_turu": "cok_basarisiz_giris", "esik": 8, "pencere_dk": 15}


def test_mesai_disi_esik_ve_sureyi_yok_sayar():
    kural, hatalar = kural_dogrula("Gece girişleri", "mesai_disi", "abc", "-5")
    assert hatalar == [] and kural["esik"] is None and kural["pencere_dk"] is None


@pytest.mark.parametrize("ad, tur, esik, pencere, beklenen", [
    ("ab", "cok_basarisiz_giris", "5", "10", "en az 3 karakter"),
    ("x" * 101, "cok_basarisiz_giris", "5", "10", "en fazla 100"),
    ("Kural", "olmayan_tur", "5", "10", "Geçerli bir kural türü"),
    ("Kural", "cok_basarisiz_giris", "", "10", "Eşik bir tam sayı"),
    ("Kural", "cok_basarisiz_giris", "5.5", "10", "Eşik bir tam sayı"),
    ("Kural", "cok_basarisiz_giris", "1", "10", "Eşik 2 ile 1000"),        # sınır: 1 her hatayı alarm yapar
    ("Kural", "cok_basarisiz_giris", "1001", "10", "Eşik 2 ile 1000"),
    ("Kural", "cok_basarisiz_giris", "5", "0", "Süre 1 ile 1440"),
    ("Kural", "cok_basarisiz_giris", "5", "1441", "Süre 1 ile 1440"),       # sınır: 1 günden uzun
])
def test_hatali_kural_engellenir(ad, tur, esik, pencere, beklenen):
    kural, hatalar = kural_dogrula(ad, tur, esik, pencere)
    assert kural is None
    assert any(beklenen in h for h in hatalar)


def test_sinir_degerler_kabul_edilir():
    assert kural_dogrula("Alt sınır", "cok_basarisiz_giris", "2", "1")[1] == []
    assert kural_dogrula("Üst sınır", "cok_basarisiz_giris", "1000", "1440")[1] == []


def test_ayni_ad_buyuk_kucuk_harf_farki_gozetmeden_engellenir():
    _, hatalar = kural_dogrula("vpn KURALI", "mesai_disi", None, None, mevcut_adlar=["VPN kuralı"])
    assert hatalar and "zaten var" in hatalar[0]


def test_birden_fazla_hata_birlikte_gosterilir():
    _, hatalar = kural_dogrula("Kural", "cok_basarisiz_giris", "0", "0")
    assert len(hatalar) == 2


def test_aciklama_cumlesi():
    assert "10 dakika içinde en az 5 hatalı" in kural_aciklamasi(
        {"kural_turu": "cok_basarisiz_giris", "esik": 5, "pencere_dk": 10})
    assert "Mesai dışında" in kural_aciklamasi({"kural_turu": "mesai_disi"})
