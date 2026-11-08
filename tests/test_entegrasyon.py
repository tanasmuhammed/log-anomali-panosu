"""Uçtan uca test (Hafta 8): kayıt ol → giriş yap → log yükle → panoda uyarı gör.
Gerçek veritabanını kullanır; geçici bir şirket oluşturur ve sonunda siler.
Yapay zekâ ve e-posta kapatılır, böylece test internete çıkmaz."""
import uuid

import pytest

from app.data import crud
from app.data.db import get_connection
from app.presentation.web import app


def _sirketi_sil(sirket_id):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM uyari WHERE anomali_id IN "
                    "(SELECT id FROM anomali WHERE sirket_id = ?)", sirket_id)
        cur.execute("DELETE FROM anomali_log WHERE anomali_id IN "
                    "(SELECT id FROM anomali WHERE sirket_id = ?)", sirket_id)
        for tablo in ("anomali", "log_kaydi", "kural", "kaynak", "kullanici"):
            cur.execute(f"DELETE FROM {tablo} WHERE sirket_id = ?", sirket_id)
        cur.execute("DELETE FROM sirket WHERE id = ?", sirket_id)
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def istemci(monkeypatch):
    for ad in ("ANTHROPIC_API_KEY", "SMTP_HOST"):
        monkeypatch.delenv(ad, raising=False)
    app.config["TESTING"] = True
    return app.test_client()


def test_kayit_giris_yukleme_ve_pano(istemci):
    ek = uuid.uuid4().hex[:8]
    kadi, parola = f"uctan_uca_{ek}", "testparola123"
    istemci.post("/kayit", data={"sirket": f"Uçtan Uca {ek}", "kullanici_adi": kadi, "parola": parola})
    kullanici = crud.kullanici_getir(kadi)
    assert kullanici is not None
    try:
        cevap = istemci.post("/giris", data={"kullanici_adi": kadi, "parola": parola})
        assert cevap.status_code == 302

        with open("sample_logs/saldiri_senaryosu.log", "rb") as f:
            cevap = istemci.post("/log-yukle", data={"yeni_kaynak": "VPN", "dosya": (f, "saldiri.log")},
                                 content_type="multipart/form-data", follow_redirects=True)
        sayfa = cevap.get_data(as_text=True)
        assert "6 yeni anomali tespit edildi" in sayfa

        sayfa = istemci.get("/pano").get_data(as_text=True)
        assert "Başarısızlıktan sonra başarılı giriş" in sayfa
        assert "198.51.100.23" in sayfa
        assert "Önerilen adım" in sayfa                     # kural tabanlı özet yazıldı
        assert len(crud.ozetsiz_anomaliler(kullanici["sirket_id"])) == 0

        # Aynı dosya aynı kaynağa tekrar yüklenirse hiçbir kayıt eklenmez
        kaynak_id = crud.kaynaklari_getir(kullanici["sirket_id"])[0]["id"]
        with open("sample_logs/saldiri_senaryosu.log", "rb") as f:
            cevap = istemci.post("/log-yukle", data={"kaynak_id": str(kaynak_id), "dosya": (f, "saldiri.log")},
                                 content_type="multipart/form-data", follow_redirects=True)
        sayfa = cevap.get_data(as_text=True)
        assert "0 kayıt eklendi" in sayfa and "yeni anomali" not in sayfa
    finally:
        _sirketi_sil(kullanici["sirket_id"])
