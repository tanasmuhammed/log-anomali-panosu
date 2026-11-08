"""Özet modülü testleri (Hafta 10). Veritabanı ve internet gerekmez:
yapay zekâ servisi sahte (mock) cevapla taklit edilir."""
import io
import json
from datetime import datetime

import pytest

from app.business import ai_ozet

D = datetime


@pytest.fixture
def anomali():
    kanitlar = [{"zaman": D(2026, 11, 5, 10, 20 + i), "ip_adresi": "198.51.100.23",
                 "kullanici_adi": "admin", "durum": "basarisiz"} for i in range(6)]
    kanitlar.append({"zaman": D(2026, 11, 5, 10, 27), "ip_adresi": "198.51.100.23",
                     "kullanici_adi": "admin", "durum": "basarili"})
    return {"id": 1, "ip_adresi": "198.51.100.23", "onem": "yuksek", "aciklama": "",
            "kural": "Başarısızlıktan sonra başarılı giriş",
            "kural_turu": "basarisizdan_basariya", "kanitlar": kanitlar}


class SahteYanit(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def sahte_model(metin):
    govde = json.dumps({"content": [{"type": "text", "text": metin}]}).encode("utf-8")
    return lambda istek, timeout=None: SahteYanit(govde)


def test_maskeleme():
    assert ai_ozet.kullanici_maskele("admin") == "a***"
    assert ai_ozet.ip_maskele("198.51.100.23") == "198.51.100.x"
    assert ai_ozet.ip_maskele("2001:db8:1:2::5") == "2001:db8:1:2::x"


def test_veri_hazirla_ham_veri_icermez(anomali):
    veri = ai_ozet.veri_hazirla(anomali)
    metin = json.dumps(veri, ensure_ascii=False)
    assert "admin" not in metin and "198.51.100.23" not in metin
    assert veri["basarisiz"] == 6 and veri["basarili"] == 1 and veri["sure_dk"] == 7


def test_anahtar_yoksa_kural_tabanli(anomali, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    metin, kaynak = ai_ozet.ozet_uret(anomali)
    assert kaynak == "kural"
    assert "Önerilen adım" in metin and "a***" in metin


def test_gecerli_model_cevabi_kullanilir(anomali, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anahtari")
    monkeypatch.setattr(ai_ozet, "urlopen", sahte_model(
        "198.51.100.x adresinden 6 başarısız denemeden sonra a*** hesabına girildi. "
        "Önerilen adım: Parolayı sıfırlayın."))
    metin, kaynak = ai_ozet.ozet_uret(anomali)
    assert kaynak == "ai" and metin.startswith("198.51.100.x")


@pytest.mark.parametrize("uydurma", [
    "198.51.100.x adresinden 40 başarısız deneme yapıldı.",          # veride 40 yok
    "198.51.100.23 adresinden 6 başarısız deneme yapıldı.",          # maskesiz IP
    "admin hesabına 6 denemeden sonra girildi.",                     # maskesiz kullanıcı
    "",                                                              # boş
])
def test_hatali_model_cevabi_reddedilir(anomali, monkeypatch, uydurma):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anahtari")
    monkeypatch.setattr(ai_ozet, "urlopen", sahte_model(uydurma))
    _, kaynak = ai_ozet.ozet_uret(anomali)
    assert kaynak == "kural"


def test_servis_hatasinda_kural_tabanli(anomali, monkeypatch):
    def hata(*a, **k):
        raise OSError("bağlantı yok")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anahtari")
    monkeypatch.setattr(ai_ozet, "urlopen", hata)
    assert ai_ozet.ozet_uret(anomali)[1] == "kural"
