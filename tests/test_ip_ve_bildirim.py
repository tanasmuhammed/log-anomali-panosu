"""IP zenginleştirme ve e-posta bildirimi testleri (Hafta 9).
Veritabanı, internet ve e-posta sunucusu gerekmez: hepsi sahte (mock)
fonksiyonlarla taklit edilir."""
import io
import json

import pytest

from app.business import bildirim, ip_zenginlestir


@pytest.fixture
def onbellek(monkeypatch):
    """crud'daki ip_konum fonksiyonlarını bellekteki bir sözlükle değiştirir."""
    tablo = {}
    monkeypatch.setattr(ip_zenginlestir.crud, "ip_konum_getir", lambda ip: tablo.get(ip))
    monkeypatch.setattr(ip_zenginlestir.crud, "ip_konum_kaydet", lambda k: tablo.__setitem__(k["ip_adresi"], k))
    return tablo


class SahteYanit(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_ayrilmis_adres_servise_sorulmaz(onbellek, monkeypatch):
    def sorma(*a, **k):
        raise AssertionError("ayrılmış adres için servise gidilmemeli")
    monkeypatch.setattr(ip_zenginlestir, "urlopen", sorma)
    konum = ip_zenginlestir.konum_bul("198.51.100.23")
    assert konum["ayrilmis"] is True
    assert "198.51.100.23" in onbellek


def test_genel_adres_servisten_gelir_ve_onbellege_yazilir(onbellek, monkeypatch):
    cevap = {"success": True, "country": "Almanya", "city": "Frankfurt",
             "connection": {"isp": "Örnek Barındırma"}}
    sayac = []

    def sahte(istek, timeout=None):
        sayac.append(istek.full_url)
        return SahteYanit(json.dumps(cevap).encode("utf-8"))
    monkeypatch.setattr(ip_zenginlestir, "urlopen", sahte)
    ip_zenginlestir.konum_bul("8.8.8.8")
    konum = ip_zenginlestir.konum_bul("8.8.8.8")          # ikinci kez: önbellekten
    assert konum["ulke"] == "Almanya" and konum["kurulus"] == "Örnek Barındırma"
    assert len(sayac) == 1


def test_servis_hatasinda_none_ve_onbellege_yazilmaz(onbellek, monkeypatch):
    def hata(*a, **k):
        raise OSError("internet yok")
    monkeypatch.setattr(ip_zenginlestir, "urlopen", hata)
    assert ip_zenginlestir.konum_bul("8.8.8.8") is None
    assert onbellek == {}


ANOMALI = {"id": 7, "onem": "yuksek", "kural": "Çok sayıda başarısız giriş",
           "ip_adresi": "203.0.113.45", "aciklama": "10 başarısız giriş",
           "kanitlar": [{"kullanici_adi": "admin"}] * 10}


def test_ayar_yoksa_eposta_gonderilmez(monkeypatch):
    for ad in ("SMTP_HOST", "SMTP_KULLANICI", "SMTP_PAROLA", "BILDIRIM_EPOSTA"):
        monkeypatch.delenv(ad, raising=False)
    assert bildirim.anomali_bildir(ANOMALI) is False


def test_eposta_gonderilir_ve_kaydedilir(monkeypatch):
    for ad, deger in {"SMTP_HOST": "smtp.ornek.test", "SMTP_KULLANICI": "gonderen@ornek.test",
                      "SMTP_PAROLA": "x", "BILDIRIM_EPOSTA": "alici@ornek.test"}.items():
        monkeypatch.setenv(ad, deger)
    giden, kayit = [], []

    class SahteSMTP:
        def __init__(self, host, port, timeout=None):
            assert host == "smtp.ornek.test" and port == 587
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def starttls(self):
            pass
        def login(self, k, p):
            pass
        def send_message(self, m):
            giden.append(m)

    monkeypatch.setattr(bildirim.smtplib, "SMTP", SahteSMTP)
    monkeypatch.setattr(bildirim.crud, "uyari_ekle", lambda a, k: kayit.append((a, k)))
    assert bildirim.anomali_bildir(ANOMALI) is True
    assert "Yüksek" in giden[0]["Subject"]
    assert "admin" not in giden[0].get_content()       # kullanıcı adı e-postaya yazılmaz
    assert kayit == [(7, "eposta")]
