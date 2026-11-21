"""Kural editörü ve rapor uçtan uca testleri (Hafta 11-12).
Gerçek veritabanını kullanır: geçici bir şirket kurar, sonunda siler."""
import uuid

import pytest

from app.data import crud
from app.presentation.web import app
from tests.test_entegrasyon import _sirketi_sil


@pytest.fixture
def yonetici():
    ek = uuid.uuid4().hex[:8]
    kadi = f"kural_test_{ek}"
    istemci = app.test_client()
    istemci.post("/kayit", data={"sirket": f"Kural Test {ek}", "kullanici_adi": kadi, "parola": "testparola123"})
    kullanici = crud.kullanici_getir(kadi)
    istemci.post("/giris", data={"kullanici_adi": kadi, "parola": "testparola123"})
    yield istemci, kullanici["sirket_id"]
    _sirketi_sil(kullanici["sirket_id"])


def test_kural_ekle_duzenle_pasif_yap_sil(yonetici):
    istemci, sirket_id = yonetici
    istemci.post("/yonetim", data={"ad": "Gece VPN", "kural_turu": "cok_basarisiz_giris",
                                   "esik": "3", "pencere_dk": "5", "islem": "kaydet"})
    kural = next(k for k in crud.kurallari_getir(sirket_id) if k["ad"] == "Gece VPN")
    assert (kural["esik"], kural["pencere_dk"], kural["aktif"]) == (3, 5, True)

    # Aynı adla ikinci kural eklenemez
    sayfa = istemci.post("/yonetim", data={"ad": "gece vpn", "kural_turu": "mesai_disi",
                                           "islem": "kaydet"}).get_data(as_text=True)
    assert "zaten var" in sayfa

    istemci.post(f"/kurallar/{kural['id']}/duzenle", data={"ad": "Gece VPN 2", "esik": "4", "pencere_dk": "20"})
    kural = crud.kural_getir(sirket_id, kural["id"])
    assert (kural["ad"], kural["esik"], kural["pencere_dk"]) == ("Gece VPN 2", 4, 20)

    istemci.post(f"/kurallar/{kural['id']}/durum", data={"aktif": "0"})
    assert crud.kural_getir(sirket_id, kural["id"])["aktif"] in (False, 0)

    istemci.post(f"/kurallar/{kural['id']}/sil")
    assert crud.kural_getir(sirket_id, kural["id"]) is None


def test_pasif_kural_taramada_calismaz(yonetici):
    istemci, sirket_id = yonetici
    for k in crud.kurallari_getir(sirket_id):
        crud.kural_aktiflik_degistir(sirket_id, k["id"], False)
    with open("sample_logs/saldiri_senaryosu.log", "rb") as f:
        sayfa = istemci.post("/log-yukle", data={"yeni_kaynak": "VPN", "dosya": (f, "s.log")},
                             content_type="multipart/form-data", follow_redirects=True).get_data(as_text=True)
    assert "0 yeni anomali" in sayfa


def test_rapor_ve_csv(yonetici):
    istemci, sirket_id = yonetici
    with open("sample_logs/saldiri_senaryosu.log", "rb") as f:
        istemci.post("/log-yukle", data={"yeni_kaynak": "VPN", "dosya": (f, "s.log")},
                     content_type="multipart/form-data")
    sorgu = "?bas=2026-11-01&bit=2026-11-30"
    sayfa = istemci.get("/rapor" + sorgu).get_data(as_text=True)
    assert "Güvenlik raporu" in sayfa and "198.51.100.23" in sayfa

    csv = istemci.get("/rapor/anomaliler.csv" + sorgu)
    assert csv.mimetype == "text/csv" and "attachment" in csv.headers["Content-Disposition"]
    satirlar = csv.get_data(as_text=True).lstrip("﻿").splitlines()
    assert satirlar[0].startswith("Olay zamanı;Önem;Kural") and len(satirlar) == 7   # başlık + 6 anomali

    bos = istemci.get("/rapor?bas=2020-01-01&bit=2020-01-31").get_data(as_text=True)
    assert "Bu aralıkta anomali yok" in bos
