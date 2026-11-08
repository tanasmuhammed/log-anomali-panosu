"""Kural motorunu veritabanına bağlayan iş katmanı servisi.

Hafta 7 : tarama ve kayıt
Hafta 9 : yeni anomaliler için IP konumu ve e-posta bildirimi
Hafta 10: yeni anomaliler için özet (yapay zekâ veya kural tabanlı)
"""
from app.business import ai_ozet, bildirim, ip_zenginlestir
from app.business.kural_motoru import kurallari_uygula
from app.data import crud


def anomali_taramasi(sirket_id, ek_islemler=True):
    """Şirketin loglarını kurallarıyla tarar, yeni anomalileri kaydeder.

    ek_islemler=True ise yeni anomaliler için konum, özet ve e-posta yapılır.
    (seed.py ilk veriyi yüklerken e-posta göndermemek için False verir.)

    Dönen değer: (bulunan_bulgu_sayisi, yeni_kaydedilen_anomali_sayisi)
    """
    loglar = crud.loglari_getir(sirket_id)
    kurallar = crud.kurallari_getir(sirket_id)
    bulgular = kurallari_uygula(loglar, kurallar)
    yeni_idler = crud.anomalileri_kaydet(sirket_id, bulgular)
    for anomali_id in yeni_idler:
        yeni_anomaliyi_isle(sirket_id, anomali_id, eposta=ek_islemler)
    return len(bulgular), len(yeni_idler)


def yeni_anomaliyi_isle(sirket_id, anomali_id, eposta=True):
    """Tek bir yeni anomali için: konum bul, özet yaz, gerekirse e-posta at.
    Bu adımlardan biri başarısız olsa bile anomali kaydı yerinde kalır;
    bu yüzden hatalar burada yakalanır ve yükleme işlemi bozulmaz."""
    try:
        anomali = crud.anomali_kanitlari(sirket_id, anomali_id)
        if anomali is None:
            return
        ip_zenginlestir.konum_bul(anomali["ip_adresi"])
        metin, kaynak = ai_ozet.ozet_uret(anomali)
        crud.anomali_ozet_kaydet(sirket_id, anomali_id, metin, kaynak)
        anomali["ai_ozeti"] = metin
        if eposta and anomali["onem"] == "yuksek":
            bildirim.anomali_bildir(anomali)
    except Exception:
        pass


def ozetleri_tamamla(sirket_id):
    """Özeti olmayan eski anomaliler için özet üretir. Üretilen özet sayısını döndürür."""
    sayi = 0
    for anomali_id in crud.ozetsiz_anomaliler(sirket_id):
        anomali = crud.anomali_kanitlari(sirket_id, anomali_id)
        if anomali is None:
            continue
        ip_zenginlestir.konum_bul(anomali["ip_adresi"])
        metin, kaynak = ai_ozet.ozet_uret(anomali)
        crud.anomali_ozet_kaydet(sirket_id, anomali_id, metin, kaynak)
        sayi += 1
    return sayi
