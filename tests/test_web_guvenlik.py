"""Web katmanı güvenlik testleri (Hafta 13). Veritabanı gerekmez:
veritabanı fonksiyonları sahte (mock) fonksiyonlarla değiştirilir."""
import pytest

from app.presentation import web


@pytest.fixture
def istemci():
    with web.app.test_client() as c:
        yield c


def oturum_ac(istemci, rol="yonetici", sirket_id=1):
    with istemci.session_transaction() as s:
        s.update(kullanici_id=1, sirket_id=sirket_id, kullanici_adi="test", rol=rol, sirket_adi="Test A.Ş.")


def test_guvenlik_basliklari(istemci):
    yanit = istemci.get("/giris")
    assert yanit.headers["X-Frame-Options"] == "DENY"
    assert yanit.headers["X-Content-Type-Options"] == "nosniff"


def test_csrf_anahtari_olmayan_form_reddedilir(istemci):
    web.app.config["CSRF_KAPALI"] = False
    yanit = istemci.post("/giris", data={"kullanici_adi": "a", "parola": "b"})
    assert yanit.status_code == 400


def test_csrf_anahtari_dogruysa_form_kabul_edilir(istemci, monkeypatch):
    web.app.config["CSRF_KAPALI"] = False
    monkeypatch.setattr(web.crud, "kullanici_getir", lambda kadi: None)
    istemci.get("/giris")
    with istemci.session_transaction() as s:
        anahtar = s["csrf"]
    yanit = istemci.post("/giris", data={"kullanici_adi": "a", "parola": "b", "csrf": anahtar})
    assert yanit.status_code == 200 and "hatalı" in yanit.get_data(as_text=True)


def test_bes_hatali_giristen_sonra_kilit(istemci, monkeypatch):
    cagrilar = []
    monkeypatch.setattr(web.crud, "kullanici_getir", lambda kadi: cagrilar.append(kadi))
    for _ in range(5):
        istemci.post("/giris", data={"kullanici_adi": "admin", "parola": "yanlis"})
    yanit = istemci.post("/giris", data={"kullanici_adi": "admin", "parola": "yanlis"})
    assert yanit.status_code == 429
    assert len(cagrilar) == 5          # 6. denemede veritabanına bile gidilmez


def test_kilit_suresi_dolunca_acilir(monkeypatch):
    for _ in range(5):
        web._giris_hatasi_kaydet("admin")
    import time
    assert web._giris_kilitli_mi("admin")
    assert not web._giris_kilitli_mi("admin", simdi=time.time() + web.GIRIS_KILIT_SN + 1)


@pytest.mark.parametrize("adres", ["/pano", "/rapor", "/yonetim", "/log-yukle", "/rapor/loglar.csv"])
def test_oturumsuz_sayfalar_girise_yonlendirir(istemci, adres):
    yanit = istemci.get(adres)
    assert yanit.status_code == 302 and "/giris" in yanit.headers["Location"]


@pytest.mark.parametrize("adres, yontem", [("/yonetim", "get"), ("/kurallar/1/duzenle", "get"),
                                           ("/kurallar/1/durum", "post"), ("/kurallar/1/sil", "post")])
def test_analist_kural_editorune_giremez(istemci, adres, yontem):
    oturum_ac(istemci, rol="analist")
    yanit = getattr(istemci, yontem)(adres)
    assert yanit.status_code == 302 and yanit.headers["Location"].endswith("/pano")


def test_baska_sirketin_kurali_bulunamaz(istemci, monkeypatch):
    oturum_ac(istemci, sirket_id=2)
    istenen = []
    monkeypatch.setattr(web.crud, "kural_getir", lambda sirket_id, kural_id: istenen.append(sirket_id))
    assert istemci.get("/kurallar/1/duzenle").status_code == 404
    assert istenen == [2]              # sorgu oturumdaki şirketle yapılır, URL'deki id'ye güvenilmez


def test_hatali_kural_kaydedilmez(istemci, monkeypatch):
    oturum_ac(istemci)
    eklenen = []
    monkeypatch.setattr(web.crud, "kurallari_getir", lambda s: [])
    monkeypatch.setattr(web.crud, "kurallar_ozetli", lambda s: [])
    monkeypatch.setattr(web.crud, "kural_ekle", lambda *a: eklenen.append(a))
    yanit = istemci.post("/yonetim", data={"ad": "Kural", "kural_turu": "cok_basarisiz_giris",
                                           "esik": "0", "pencere_dk": "10", "islem": "kaydet"})
    assert yanit.status_code == 200 and "Eşik 2 ile 1000" in yanit.get_data(as_text=True)
    assert eklenen == []


def test_kural_kaydetmeden_denenir(istemci, monkeypatch):
    from datetime import datetime, timedelta
    oturum_ac(istemci)
    t = datetime(2026, 11, 1, 10)
    loglar = [{"id": i, "zaman": t + timedelta(seconds=30 * i), "ip_adresi": "203.0.113.5",
               "kullanici_adi": "admin", "durum": "basarisiz"} for i in range(6)]
    monkeypatch.setattr(web.crud, "kurallari_getir", lambda s: [])
    monkeypatch.setattr(web.crud, "kurallar_ozetli", lambda s: [])
    monkeypatch.setattr(web.crud, "loglari_getir", lambda s: loglar)
    monkeypatch.setattr(web.crud, "kural_ekle", lambda *a: pytest.fail("deneme kaydetmemeli"))
    yanit = istemci.post("/yonetim", data={"ad": "Deneme", "kural_turu": "cok_basarisiz_giris",
                                           "esik": "5", "pencere_dk": "10", "islem": "dene"})
    assert "1 olay" in yanit.get_data(as_text=True)


def test_olmayan_sayfa_404(istemci):
    yanit = istemci.get("/boyle-bir-sayfa-yok")
    assert yanit.status_code == 404 and "bulunamadı" in yanit.get_data(as_text=True)
