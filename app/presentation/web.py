import os
import secrets
import time
from datetime import date
from functools import wraps

from dotenv import load_dotenv
from flask import (Flask, Response, abort, flash, redirect, render_template,
                   request, session, url_for)

from app.business import rapor_servisi
from app.business.anomali_servisi import anomali_taramasi, ozetleri_tamamla
from app.business.auth import parola_dogrula, parola_hashle
from app.business.kural_dogrulama import KURAL_TURLERI, kural_aciklamasi, kural_dogrula
from app.business.kural_motoru import kurallari_uygula
from app.business.log_parser import dosya_ayristir
from app.data import crud

load_dotenv()

app = Flask(__name__)
# Oturum çerezini imzalayan gizli anahtar .env'den gelir. Yoksa uygulama yine
# açılır ama her yeniden başlatmada oturumlar düşer (rastgele anahtar üretilir).
app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,     # en fazla 2 MB dosya
    SESSION_COOKIE_HTTPONLY=True,           # çerez JavaScript ile okunamaz
    SESSION_COOKIE_SAMESITE="Lax",          # başka siteden gelen isteklerde çerez gönderilmez
)


# ====================== GÜVENLİK (Hafta 13) ======================

def csrf_token():
    """Oturuma özel rastgele bir anahtar. Her POST formunda gizli alan olarak
    gönderilir; başka bir siteden hazırlanan sahte form bu anahtarı bilemez."""
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def csrf_kontrol():
    if request.method != "POST" or app.config.get("CSRF_KAPALI"):
        return
    gelen = request.form.get("csrf", "")
    if not gelen or not secrets.compare_digest(gelen, session.get("csrf", "")):
        abort(400, "Form süresi doldu veya geçersiz. Sayfayı yenileyip tekrar deneyin.")


@app.after_request
def guvenlik_basliklari(yanit):
    yanit.headers.setdefault("X-Content-Type-Options", "nosniff")   # dosya türü tahmini kapalı
    yanit.headers.setdefault("X-Frame-Options", "DENY")             # sayfa başka sitede çerçevelenemez
    yanit.headers.setdefault("Referrer-Policy", "same-origin")
    return yanit


# Kaba kuvvet koruması: aynı kullanıcı adına kısa sürede çok hatalı giriş
# yapılırsa o ad bir süre kilitlenir. Projenin tespit ettiği saldırıya karşı
# uygulamanın kendisi de korunmuş olur.
GIRIS_HATA_SINIRI = 5
GIRIS_KILIT_SN = 5 * 60
_giris_hatalari = {}   # kullanıcı adı -> [hata zamanları]


def _giris_kilitli_mi(kadi, simdi=None):
    simdi = simdi or time.time()
    son_hatalar = [t for t in _giris_hatalari.get(kadi.lower(), []) if simdi - t < GIRIS_KILIT_SN]
    _giris_hatalari[kadi.lower()] = son_hatalar
    return len(son_hatalar) >= GIRIS_HATA_SINIRI


def _giris_hatasi_kaydet(kadi):
    _giris_hatalari.setdefault(kadi.lower(), []).append(time.time())


# ====================== ERİŞİM KONTROLÜ ======================

def giris_gerekli(f):
    """Giriş yapılmadan açılmaması gereken sayfalar için."""
    @wraps(f)
    def sarmal(*args, **kwargs):
        if "kullanici_id" not in session:
            flash("Önce giriş yapın.")
            return redirect(url_for("giris"))
        return f(*args, **kwargs)
    return sarmal


def yonetici_gerekli(f):
    """Yalnızca yönetici rolünün açabileceği sayfalar için."""
    @wraps(f)
    @giris_gerekli
    def sarmal(*args, **kwargs):
        if session.get("rol") != "yonetici":
            flash("Yönetici yetkisi gerekiyor.")
            return redirect(url_for("pano"))
        return f(*args, **kwargs)
    return sarmal


@app.errorhandler(400)
def hatali_istek(hata):
    return render_template("hata.html", kod=400, mesaj=hata.description), 400


@app.errorhandler(404)
def bulunamadi(hata):
    return render_template("hata.html", kod=404, mesaj="Aradığınız sayfa bulunamadı."), 404


@app.errorhandler(413)
def dosya_buyuk(hata):
    flash("Dosya en fazla 2 MB olabilir.")
    return redirect(url_for("log_yukle"))


# ====================== GİRİŞ / KAYIT ======================

@app.route("/")
def ana_sayfa():
    if "kullanici_id" in session:
        return redirect(url_for("pano"))
    return render_template("ana.html")


@app.route("/kayit", methods=["GET", "POST"])
def kayit():
    if request.method == "POST":
        sirket = request.form.get("sirket", "").strip()
        kadi = request.form.get("kullanici_adi", "").strip()
        parola = request.form.get("parola", "")

        if not sirket or not kadi:
            flash("Şirket adı ve kullanıcı adı boş olamaz.")
        elif len(parola) < 8:
            flash("Parola en az 8 karakter olmalı.")
        else:
            try:
                crud.sirket_ve_yonetici_ekle(sirket, kadi, parola_hashle(parola))
                flash("Kayıt tamamlandı. Şimdi giriş yapabilirsiniz.")
                return redirect(url_for("giris"))
            except ValueError as hata:
                flash(str(hata))
    return render_template("kayit.html")


@app.route("/giris", methods=["GET", "POST"])
def giris():
    if request.method == "POST":
        kadi = request.form.get("kullanici_adi", "").strip()
        parola = request.form.get("parola", "")

        if _giris_kilitli_mi(kadi):
            flash("Çok fazla hatalı deneme. Birkaç dakika sonra tekrar deneyin.")
            return render_template("giris.html"), 429

        kullanici = crud.kullanici_getir(kadi)
        if kullanici and parola_dogrula(parola, kullanici["parola_hash"]):
            _giris_hatalari.pop(kadi.lower(), None)
            session.clear()
            session["kullanici_id"] = kullanici["id"]
            session["sirket_id"] = kullanici["sirket_id"]
            session["kullanici_adi"] = kullanici["kullanici_adi"]
            session["rol"] = kullanici["rol"]
            session["sirket_adi"] = kullanici["sirket_adi"]
            flash("Giriş başarılı.")
            return redirect(url_for("pano"))
        _giris_hatasi_kaydet(kadi)
        flash("Kullanıcı adı veya parola hatalı.")

    return render_template("giris.html")


@app.route("/cikis")
def cikis():
    session.clear()
    flash("Çıkış yapıldı.")
    return redirect(url_for("giris"))


# ====================== PANO ======================

@app.route("/pano")
@giris_gerekli
def pano():
    sirket_id = session["sirket_id"]
    return render_template(
        "pano.html",
        loglar=crud.son_loglar(sirket_id, adet=10),
        anomaliler=crud.anomalileri_getir(sirket_id, adet=20),
        ozet=crud.pano_ozeti(sirket_id),
        saatlik=crud.saatlik_dagilim(sirket_id),
        kural_dagilimi=crud.kural_dagilimi(sirket_id),
        ozetsiz=len(crud.ozetsiz_anomaliler(sirket_id)),
    )


@app.route("/tarama", methods=["POST"])
@giris_gerekli
def tarama():
    bulgu, yeni = anomali_taramasi(session["sirket_id"])
    flash(f"Tarama tamamlandı: {bulgu} bulgu, {yeni} yeni anomali.")
    if request.form.get("geri") == "yonetim":     # kural sayfasından basıldıysa oraya dön
        return redirect(url_for("yonetim"))
    return redirect(url_for("pano"))


@app.route("/ozetle", methods=["POST"])
@giris_gerekli
def ozetle():
    """Özeti olmayan anomaliler için özet üretir (Hafta 10)."""
    sayi = ozetleri_tamamla(session["sirket_id"])
    flash(f"{sayi} uyarı için özet oluşturuldu.")
    return redirect(url_for("pano"))


# ====================== LOG YÜKLEME ======================

@app.route("/log-yukle", methods=["GET", "POST"])
@giris_gerekli
def log_yukle():
    sirket_id = session["sirket_id"]
    hatalar = []

    if request.method == "POST":
        dosya = request.files.get("dosya")
        kaynak_id = request.form.get("kaynak_id", "")
        yeni_kaynak = request.form.get("yeni_kaynak", "").strip()

        if not dosya or not dosya.filename:
            flash("Bir log dosyası seçin.")
        elif not dosya.filename.lower().endswith((".log", ".txt")):
            flash("Yalnızca .log veya .txt dosyası yüklenebilir.")
        elif not kaynak_id and not yeni_kaynak:
            flash("Bir kaynak seçin veya yeni kaynak adı yazın.")
        else:
            try:
                icerik = dosya.read().decode("utf-8-sig")   # Not Defteri'nin eklediği BOM atlanır
                if yeni_kaynak:
                    kaynak_id = crud.kaynak_ekle(sirket_id, yeni_kaynak)
                kayitlar, hatalar = dosya_ayristir(icerik.splitlines())
                eklenen, tekrar = crud.loglar_toplu_ekle(sirket_id, int(kaynak_id), kayitlar)
                mesaj = (f"{eklenen} kayıt eklendi, {tekrar} tekrar kayıt atlandı, "
                         f"{len(hatalar)} hatalı satır atlandı.")
                if eklenen:
                    _, yeni_anomali = anomali_taramasi(sirket_id)
                    mesaj += f" {yeni_anomali} yeni anomali tespit edildi."
                flash(mesaj)
            except UnicodeDecodeError:
                flash("Dosya UTF-8 metin dosyası olmalı.")
            except ValueError as hata:
                flash(str(hata))

    kaynaklar = crud.kaynaklari_getir(sirket_id)
    return render_template("log_yukle.html", kaynaklar=kaynaklar, hatalar=hatalar)


# ====================== KURAL EDİTÖRÜ (Hafta 11) ======================

def _kural_formu():
    return {
        "ad": request.form.get("ad", ""),
        "kural_turu": request.form.get("kural_turu", ""),
        "esik": request.form.get("esik", ""),
        "pencere_dk": request.form.get("pencere_dk", ""),
    }


def _kural_onizle(sirket_id, kural):
    """Kuralı kaydetmeden mevcut loglarda dener: kaç olay yakalardı?"""
    deneme = {**kural, "id": 0, "aktif": True}
    bulgular = kurallari_uygula(crud.loglari_getir(sirket_id), [deneme])
    return len(bulgular), sum(1 for b in bulgular if b["onem"] == "yuksek")


@app.route("/yonetim", methods=["GET", "POST"])
@yonetici_gerekli
def yonetim():
    """Kural listesi ve yeni kural formu."""
    sirket_id = session["sirket_id"]
    form, hatalar, onizleme = {"kural_turu": "cok_basarisiz_giris", "esik": "5", "pencere_dk": "10"}, [], None

    if request.method == "POST":
        form = _kural_formu()
        mevcut = [k["ad"] for k in crud.kurallari_getir(sirket_id)]
        kural, hatalar = kural_dogrula(form["ad"], form["kural_turu"], form["esik"], form["pencere_dk"], mevcut)
        if kural and request.form.get("islem") == "dene":
            onizleme = _kural_onizle(sirket_id, kural)
        elif kural:
            crud.kural_ekle(sirket_id, kural["ad"], kural["kural_turu"], kural["esik"], kural["pencere_dk"])
            flash(f"“{kural['ad']}” kuralı eklendi. Mevcut loglara uygulamak için “Kuralları şimdi çalıştır”a basın.")
            return redirect(url_for("yonetim"))

    kurallar = crud.kurallar_ozetli(sirket_id)
    for k in kurallar:
        k["cumle"] = kural_aciklamasi(k)
        k["tur_adi"] = KURAL_TURLERI[k["kural_turu"]]["ad"]
    return render_template("yonetim.html", kurallar=kurallar, turler=KURAL_TURLERI,
                           form=form, hatalar=hatalar, onizleme=onizleme)


@app.route("/kurallar/<int:kural_id>/duzenle", methods=["GET", "POST"])
@yonetici_gerekli
def kural_duzenle(kural_id):
    sirket_id = session["sirket_id"]
    kural = crud.kural_getir(sirket_id, kural_id)
    if kural is None:                       # yok ya da başka şirketin kuralı
        abort(404)
    form = {"ad": kural["ad"], "kural_turu": kural["kural_turu"],
            "esik": kural["esik"] or "", "pencere_dk": kural["pencere_dk"] or ""}
    hatalar, onizleme = [], None

    if request.method == "POST":
        form = {**_kural_formu(), "kural_turu": kural["kural_turu"]}   # tür değiştirilemez
        diger_adlar = [k["ad"] for k in crud.kurallari_getir(sirket_id) if k["id"] != kural_id]
        temiz, hatalar = kural_dogrula(form["ad"], form["kural_turu"], form["esik"], form["pencere_dk"], diger_adlar)
        if temiz and request.form.get("islem") == "dene":
            onizleme = _kural_onizle(sirket_id, temiz)
        elif temiz:
            crud.kural_duzenle(sirket_id, kural_id, temiz["ad"], temiz["esik"], temiz["pencere_dk"])
            flash(f"“{temiz['ad']}” kuralı güncellendi.")
            return redirect(url_for("yonetim"))

    return render_template("kural_duzenle.html", kural=kural, form=form, hatalar=hatalar,
                           onizleme=onizleme, tur=KURAL_TURLERI[kural["kural_turu"]])


@app.route("/kurallar/<int:kural_id>/durum", methods=["POST"])
@yonetici_gerekli
def kural_durum(kural_id):
    aktif = request.form.get("aktif") == "1"
    if crud.kural_aktiflik_degistir(session["sirket_id"], kural_id, aktif) == 0:
        abort(404)
    flash("Kural etkinleştirildi." if aktif else "Kural pasif yapıldı; taramalarda çalışmayacak.")
    return redirect(url_for("yonetim"))


@app.route("/kurallar/<int:kural_id>/sil", methods=["POST"])
@yonetici_gerekli
def kural_sil(kural_id):
    try:
        if crud.kural_sil(session["sirket_id"], kural_id) == 0:
            abort(404)
        flash("Kural silindi.")
    except ValueError as hata:
        flash(str(hata))
    return redirect(url_for("yonetim"))


# ====================== RAPOR (Hafta 12) ======================

def _rapor_araligi():
    bas, bit, hata = rapor_servisi.tarih_araligi(request.args.get("bas"), request.args.get("bit"))
    if hata:
        flash(hata)
        bas, bit, _ = rapor_servisi.tarih_araligi(None, None)
    return bas, bit


@app.route("/rapor")
@giris_gerekli
def rapor():
    bas, bit = _rapor_araligi()
    veri = rapor_servisi.rapor_hazirla(session["sirket_id"], bas, bit)
    return render_template("rapor.html", r=veri, bugun=date.today(),
                           olusturma=date.today().strftime("%d.%m.%Y"))


def _csv_yaniti(metin, dosya_adi):
    return Response(metin, mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{dosya_adi}"'})


@app.route("/rapor/anomaliler.csv")
@giris_gerekli
def rapor_anomali_csv():
    bas, bit = _rapor_araligi()
    alt, ust = rapor_servisi.sorgu_sinirlari(bas, bit)
    anomaliler = crud.rapor_anomalileri(session["sirket_id"], alt, ust)
    return _csv_yaniti(rapor_servisi.anomali_csv(anomaliler), f"anomaliler_{bas}_{bit}.csv")


@app.route("/rapor/loglar.csv")
@giris_gerekli
def rapor_log_csv():
    bas, bit = _rapor_araligi()
    alt, ust = rapor_servisi.sorgu_sinirlari(bas, bit)
    loglar = crud.loglari_aralikta(session["sirket_id"], alt, ust)
    return _csv_yaniti(rapor_servisi.log_csv(loglar), f"giris_kayitlari_{bas}_{bit}.csv")


if __name__ == "__main__":
    # GÜVENLİK: debug modu sadece FLASK_DEBUG=1 ise açılır. Uygulama internete
    # açıldığında (canlı link) debug kapalı olmalı, yoksa hata sayfasından
    # sunucuda kod çalıştırılabilir.
    app.run(debug=os.getenv("FLASK_DEBUG") == "1")
