"""Anomali servisi testleri (Hafta 13). Veritabanı sahte fonksiyonlarla
taklit edilir; servisin adımları doğru sırada çağırdığı ve bir yan adım
(konum, özet, e-posta) hata verse bile kaydın bozulmadığı kontrol edilir."""
from datetime import datetime, timedelta

import pytest

from app.business import anomali_servisi as s


@pytest.fixture
def sahte_vt(monkeypatch):
    t = datetime(2026, 11, 1, 10)
    loglar = [{"id": i, "zaman": t + timedelta(seconds=30 * i), "ip_adresi": "203.0.113.5",
               "kullanici_adi": "admin", "durum": "basarisiz"} for i in range(6)]
    kurallar = [{"id": 1, "ad": "Çok sayıda başarısız giriş", "kural_turu": "cok_basarisiz_giris",
                 "esik": 5, "pencere_dk": 10, "aktif": True}]
    kayit = {"ozet": [], "eposta": []}
    monkeypatch.setattr(s.crud, "loglari_getir", lambda sid: loglar)
    monkeypatch.setattr(s.crud, "kurallari_getir", lambda sid: kurallar)
    monkeypatch.setattr(s.crud, "anomalileri_kaydet", lambda sid, b: [101] if b else [])
    monkeypatch.setattr(s.crud, "anomali_kanitlari", lambda sid, aid: {
        "id": aid, "ip_adresi": "203.0.113.5", "onem": "orta", "aciklama": "6 başarısız giriş",
        "kural": "Çok sayıda başarısız giriş", "kural_turu": "cok_basarisiz_giris", "kanitlar": loglar})
    monkeypatch.setattr(s.crud, "anomali_ozet_kaydet", lambda sid, aid, m, k: kayit["ozet"].append((aid, k)))
    monkeypatch.setattr(s.ip_zenginlestir, "konum_bul", lambda ip: None)
    monkeypatch.setattr(s.bildirim, "anomali_bildir", lambda a: kayit["eposta"].append(a["id"]))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return kayit


def test_tarama_bulgu_ve_yeni_sayisini_doner(sahte_vt):
    assert s.anomali_taramasi(1) == (1, 1)
    assert sahte_vt["ozet"] == [(101, "kural")]       # API anahtarı yok: kural tabanlı özet


def test_orta_onemde_eposta_gitmez(sahte_vt):
    s.anomali_taramasi(1)
    assert sahte_vt["eposta"] == []


def test_yan_adim_hata_verse_de_tarama_bozulmaz(sahte_vt, monkeypatch):
    def patla(ip):
        raise RuntimeError("konum servisi çöktü")
    monkeypatch.setattr(s.ip_zenginlestir, "konum_bul", patla)
    assert s.anomali_taramasi(1) == (1, 1)              # hata yakalandı, sayılar doğru
