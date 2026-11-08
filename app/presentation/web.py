import os

from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, session, url_for

from app.business.anomali_servisi import anomali_taramasi, ozetleri_tamamla
from app.business.auth import parola_dogrula, parola_hashle
from app.business.log_parser import dosya_ayristir
from app.data import crud

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024  # en fazla 2 MB dosya


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

        kullanici = crud.kullanici_getir(kadi)
        if kullanici and parola_dogrula(parola, kullanici["parola_hash"]):
            session.clear()
            session["kullanici_id"] = kullanici["id"]
            session["sirket_id"] = kullanici["sirket_id"]
            session["kullanici_adi"] = kullanici["kullanici_adi"]
            session["rol"] = kullanici["rol"]
            session["sirket_adi"] = kullanici["sirket_adi"]
            flash("Giriş başarılı.")
            return redirect(url_for("pano"))
        else:
            flash("Kullanıcı adı veya parola hatalı.")

    return render_template("giris.html")


@app.route("/pano")
def pano():
    if "kullanici_id" not in session:
        flash("Önce giriş yapın.")
        return redirect(url_for("giris"))
    sirket_id = session["sirket_id"]
    loglar = crud.son_loglar(sirket_id, adet=10)
    anomaliler = crud.anomalileri_getir(sirket_id, adet=20)
    ozet = crud.pano_ozeti(sirket_id)
    saatlik = crud.saatlik_dagilim(sirket_id)
    kural_dagilimi = crud.kural_dagilimi(sirket_id)
    ozetsiz = len(crud.ozetsiz_anomaliler(sirket_id))
    return render_template(
        "pano.html", loglar=loglar, anomaliler=anomaliler, ozet=ozet,
        saatlik=saatlik, kural_dagilimi=kural_dagilimi, ozetsiz=ozetsiz,
    )


@app.route("/tarama", methods=["POST"])
def tarama():
    if "kullanici_id" not in session:
        flash("Önce giriş yapın.")
        return redirect(url_for("giris"))
    bulgu, yeni = anomali_taramasi(session["sirket_id"])
    flash(f"Tarama tamamlandı: {bulgu} bulgu, {yeni} yeni anomali.")
    return redirect(url_for("pano"))


@app.route("/ozetle", methods=["POST"])
def ozetle():
    """Özeti olmayan anomaliler için özet üretir (Hafta 10)."""
    if "kullanici_id" not in session:
        flash("Önce giriş yapın.")
        return redirect(url_for("giris"))
    sayi = ozetleri_tamamla(session["sirket_id"])
    flash(f"{sayi} uyarı için özet oluşturuldu.")
    return redirect(url_for("pano"))


@app.route("/yonetim")
def yonetim():
    if "kullanici_id" not in session:
        flash("Önce giriş yapın.")
        return redirect(url_for("giris"))
    if session.get("rol") != "yonetici":
        flash("Yönetici yetkisi gerekiyor.")
        return redirect(url_for("pano"))
    kurallar = crud.kurallari_getir(session["sirket_id"])
    return render_template("yonetim.html", kurallar=kurallar)


@app.route("/log-yukle", methods=["GET", "POST"])
def log_yukle():
    if "kullanici_id" not in session:
        flash("Önce giriş yapın.")
        return redirect(url_for("giris"))

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
                icerik = dosya.read().decode("utf-8")
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


@app.route("/cikis")
def cikis():
    session.clear()
    flash("Çıkış yapıldı.")
    return redirect(url_for("giris"))


if __name__ == "__main__":
    # GÜVENLİK: debug modu sadece FLASK_DEBUG=1 ise açılır. Uygulama internete
    # açıldığında (canlı link) debug kapalı olmalı, yoksa hata sayfasından
    # sunucuda kod çalıştırılabilir.
    app.run(debug=os.getenv("FLASK_DEBUG") == "1")