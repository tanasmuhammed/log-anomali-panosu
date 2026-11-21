"""Tüm testler için ortak ayarlar (Hafta 13).

Formlardaki CSRF anahtarı testlerde kapatılır; böylece test istemcisi formu
doğrudan gönderebilir. CSRF korumasının kendisi test_web_guvenlik.py içinde
ayrıca, açık hâliyle test edilir. Giriş kilidi sayacı her testten önce
sıfırlanır ki bir testteki hatalı girişler diğerini etkilemesin.
"""
import pytest

from app.presentation import web


@pytest.fixture(autouse=True)
def test_ayarlari():
    web.app.config["TESTING"] = True
    web.app.config["CSRF_KAPALI"] = True
    web._giris_hatalari.clear()
    yield
    web._giris_hatalari.clear()
