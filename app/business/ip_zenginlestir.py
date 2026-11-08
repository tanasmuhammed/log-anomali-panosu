"""IP adresi zenginleştirme (Hafta 9).

Bir anomali bulunduğunda, saldıran IP adresinin hangi ülke / şehir / kuruma
ait olduğunu bulur. Sonuç ip_konum tablosunda saklanır (önbellek), böylece
aynı IP için dış servise tekrar sorgu atılmaz.

Dış servis: ipwho.is (anahtar gerektirmez, HTTPS). Servise SADECE IP adresi
gider; kullanıcı adı, şirket adı gibi bilgiler gönderilmez.

Önemli: Bu modül hiçbir zaman hata fırlatmaz. Servis kapalıysa ya da internet
yoksa None döner ve uygulama konumsuz devam eder.
"""
import ipaddress
import json
from urllib.request import Request, urlopen

from app.data import crud

SERVIS_ADRESI = "https://ipwho.is/{ip}"
ZAMAN_ASIMI_SN = 3


def ayrilmis_mi(ip):
    """IP internette gerçek bir yere ait değilse True.
    Örn: 192.168.x.x (ev/ofis ağı), 127.0.0.1, 192.0.2.x (dokümantasyon/test).
    Projedeki sentetik IP'lerin hepsi bu gruptadır."""
    try:
        return not ipaddress.ip_address(ip).is_global
    except ValueError:
        return True   # geçersiz adres: dışarı sorma


def servisten_sorgula(ip):
    """ipwho.is servisine sorar. Başarısızsa None döner."""
    try:
        istek = Request(SERVIS_ADRESI.format(ip=ip), headers={"User-Agent": "Gozcu-ogrenci-projesi"})
        with urlopen(istek, timeout=ZAMAN_ASIMI_SN) as yanit:
            veri = json.loads(yanit.read().decode("utf-8"))
    except Exception:
        return None
    if not veri.get("success"):
        return None
    baglanti = veri.get("connection") or {}
    return {
        "ip_adresi": ip,
        "ulke": veri.get("country"),
        "sehir": veri.get("city"),
        "kurulus": baglanti.get("isp") or baglanti.get("org"),
        "ayrilmis": False,
    }


def konum_bul(ip):
    """IP'nin konumunu döndürür. Önce önbelleğe bakar, yoksa servise sorar.
    Bulunamazsa None. Başarısız sorgular önbelleğe yazılmaz (sonra tekrar denenir)."""
    if not ip:
        return None
    try:
        kayitli = crud.ip_konum_getir(ip)
        if kayitli:
            return kayitli
        if ayrilmis_mi(ip):
            konum = {"ip_adresi": ip, "ulke": None, "sehir": None,
                     "kurulus": "Ayrılmış adres (test/dokümantasyon)", "ayrilmis": True}
        else:
            konum = servisten_sorgula(ip)
            if konum is None:
                return None
        crud.ip_konum_kaydet(konum)
        return konum
    except Exception:
        return None
