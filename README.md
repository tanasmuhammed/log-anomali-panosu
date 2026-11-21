# Gözcü: Günlük (Log) Anomali İzleme Panosu

Şirketlerin sistemlerine yapılan giriş denemelerini (log kayıtlarını) analiz edip
**şüpheli, hatalı ve alışılmadık girişleri** yakalayan, bunları bir pano üzerinden
gösteren ve uyarı üreten çok şirketli bir web uygulamasıdır.

> **Ders:** Bilgisayar Uygulamaları I (Proje Tabanlı Ders)
> **Proje:** P27, Günlük (Log) Anomali İzleme Panosu
> **Geliştirici:** Muhammed Berkin Tanas
> **Durum:** Tamamlandı (v1.0.0). Tüm modüller çalışıyor: çok şirketli yapı, giriş ve roller, log içe aktarma, anomali kuralları, kural editörü, IP konumu, e-posta bildirimi, yapay zekâ özeti, güvenlik raporu ve dışa aktarma. 101 otomatik test.
>
> **Canlı demo:** https://nautical-tyke-latticed.ngrok-free.dev (geliştiricinin bilgisayarı açıkken çalışır; ilk açılışta ngrok uyarısında *Visit Site* denir) · Demo hesap: `yonetici_mavi` / `demo12345`

---

## 1. Proje amacı

Bir şirketin sunucu, VPN veya uygulamalarına her gün yüzlerce giriş denemesi yapılır.
Bunların arasında saldırı belirtisi olan davranışları elle ayıklamak zordur.
Gözcü bu logları toplar, belirlenen kurallara göre inceler ve şüpheli durumları
şirket yöneticisine tek ekranda gösterir.

**Temel fikir:** Her şirket kendi hesabıyla giriş yapar ve **yalnızca kendi şirketinin**
giriş loglarını görür.

## 2. Özellikler

| Özellik | Açıklama |
|---|---|
| Çok şirketli yapı | Her şirketin verisi ayrıdır, şirketler birbirinin verisini göremez |
| Log içe aktarma ve ayrıştırma | Log dosyaları okunur, alanlara ayrılır ve veritabanına kaydedilir |
| Anomali kuralları | Şüpheli davranışları yakalayan kural motoru |
| Pano | Saatlik giriş grafiği, uyarı listesi, son giriş kayıtları |
| Uyarılar | Kurala takılan olaylar için önem dereceli uyarı |
| Kural editörü | Yönetici kural ekler, düzenler, pasif yapar, siler; kaydetmeden önce mevcut loglarda dener |
| Rol tabanlı erişim | Yönetici ve analist rolleri |
| Yapay zekâ özeti | Anomalilerin kısa ve anlaşılır özeti |
| IP konumu | Saldıran IP'nin ülke / şehir / kuruluş bilgisi (önbellekli) |
| E-posta bildirimi | Yüksek önemli uyarıda yöneticiye e-posta (isteğe bağlı) |
| Güvenlik raporu | Tarih aralığı, günlük eğilim, en çok saldıran IP'ler, hedeflenen hesaplar; CSV ve yazdırılabilir/PDF çıktı |
| Uygulama güvenliği | CSRF koruması, giriş deneme sınırı, güvenlik başlıkları, parametreli sorgular |

### Anomali kuralları (başlangıç seti)

1. **Çok sayıda başarısız giriş:** Aynı IP'den kısa sürede belirli sayıda hatalı giriş.
2. **Çok sayıda kullanıcı adı denemesi:** Aynı IP'nin birçok farklı kullanıcıyı denemesi.
3. **Başarısızlıktan sonra başarılı giriş:** Art arda hatadan sonra gelen başarılı giriş.
4. **Mesai dışı giriş:** Alışılmadık saatlerde yapılan giriş.

## 3. Mimari

Uygulama üç katmanlı olarak tasarlanmıştır:

- **Sunum katmanı** (`app/presentation`): Web sayfaları, giriş ekranı, pano.
- **İş katmanı** (`app/business`): Log ayrıştırma, anomali kural motoru, uyarı üretimi.
- **Veri katmanı** (`app/data`): Veritabanı bağlantısı ve sorgular.

![Mimari şema](docs/mimari_sema.svg)

Katmanları ayırmak her parçanın tek bir işi yapmasını sağlar. Örneğin veritabanı
değişirse yalnızca veri katmanı etkilenir.

## 4. Veritabanı

Veritabanı **Microsoft SQL Server** üzerinde `LogAnomali` adıyla kurulur.
Toplam 9 tablo vardır (8 ana tablo + `ip_konum` önbelleği):

| Tablo | Açıklama |
|---|---|
| `sirket` | Sisteme kayıtlı şirketler |
| `kullanici` | Panele giren kişiler (bir şirkete bağlı, rolü vardır) |
| `kaynak` | Şirketin log gönderen sistemi (web sunucusu, VPN vb.) |
| `log_kaydi` | Tek bir giriş denemesi (zaman, IP, kullanıcı, başarılı/başarısız) |
| `kural` | Şirkete özel anomali kuralları ve eşikleri |
| `anomali` | Bir kuralın yakaladığı şüpheli durum |
| `anomali_log` | Anomali ile log kaydı arasındaki çoktan-çoğa ilişki (ara tablo) |
| `uyari` | Gösterilen veya gönderilen bildirim (kanal: panel / eposta) |
| `ip_konum` | IP konum önbelleği (şirkete özel değil, kişisel veri tutmaz) |

**İlişkiler:** Bir şirketin çok kullanıcısı, kaynağı, kuralı ve logu vardır (1-N).
Bir anomali birden çok log kaydından oluşabilir ve bir log birden çok anomaliye
ait olabilir (N-N), bu yüzden `anomali_log` ara tablosu kullanılmıştır.

**Veri izolasyonu:** `log_kaydi`, `kural` ve `anomali` tabloları doğrudan `sirket_id`
taşır. Her sorguda bu alana göre filtre uygulanır.

![ER diyagramı](docs/er_diyagrami.svg)

## 5. Klasör yapısı

```
.
├── app/
│   ├── presentation/     # Sunum katmanı (web sayfaları)
│   ├── business/         # İş katmanı (ayrıştırma, kurallar)
│   └── data/             # Veri katmanı (veritabanı erişimi)
├── docs/
│   ├── er_diyagrami.svg        # ER diyagramı
│   ├── mimari_sema.svg         # Mimari şema
│   ├── pano_demo.html          # İlk tasarım prototipi (sentetik veri)
│   ├── Teknik_Dokumantasyon.docx # Final teknik dokümantasyonu
│   └── Savunma_Hazirligi.docx  # Demo senaryosu ve olası sorular
├── raporlar/
│   └── Hafta-N/                # Haftalık ilerleme raporu ve AI kullanım günlüğü (Word)
├── sample_logs/                # Sentetik örnek log dosyaları
├── sql/
│   ├── 01_tablolar.sql         # Tabloları oluşturan script
│   ├── 02_anomali_aciklama.sql # Migration: anomali açıklama kolonu
│   ├── 03_ip_konum.sql         # Migration: IP konum önbelleği (Hafta 9)
│   └── 04_ai_ozet.sql          # Migration: özet kaynağı kolonu (Hafta 10)
├── tests/                      # pytest testleri
├── canli_link_sabit.bat        # Sabit canlı link (ngrok)
├── otomatik_baslat.bat         # Linki bilgisayar açılışında başlatır
├── .env.example                # Ortam değişkenleri şablonu
├── .gitignore
├── requirements.txt
└── README.md
```

## 6. Kullanılan teknolojiler

- **Python 3.13**: uygulama dili
- **Flask**: web çerçevesi
- **Microsoft SQL Server (Express)**: veritabanı
- **pyodbc**: Python ile SQL Server bağlantısı
- **python-dotenv**: ayarları `.env` dosyasından okuma
- **pytest**: testler
- **HTML, CSS, JavaScript, Chart.js**: arayüz ve grafikler
- **ipwho.is**: IP konum servisi (anahtarsız)
- **Anthropic Messages API**: yapay zekâ özeti (isteğe bağlı)

## 7. Kurulum

### Gereksinimler
- Python 3.11 veya üzeri
- SQL Server 2022 Express ve SQL Server Management Studio (SSMS)
- ODBC Driver 18 for SQL Server
- Git

### Adımlar

**1. Depoyu indirin**
```bash
git clone https://github.com/tanasmuhammed/log-anomali-panosu.git
cd log-anomali-panosu
```

**2. Sanal ortam oluşturun ve paketleri kurun**
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

**3. Veritabanını oluşturun**

SSMS'te yeni bir sorgu penceresi açıp şunu çalıştırın:
```sql
CREATE DATABASE LogAnomali;
```
Ardından `sql` klasöründeki dosyaları **sırayla** SSMS'te açıp çalıştırın:
`01_tablolar.sql`, `02_anomali_aciklama.sql`, `03_ip_konum.sql`, `04_ai_ozet.sql`.
02-04 tekrar çalıştırılırsa zarar vermez.

**4. Ayar dosyasını hazırlayın**

`.env.example` dosyasını `.env` adıyla kopyalayın ve kendi bilgisayarınıza göre düzenleyin:
```
DB_SERVER=localhost\SQLEXPRESS
DB_NAME=LogAnomali
DB_DRIVER=ODBC Driver 18 for SQL Server
DB_TRUSTED=yes
```
`.env` dosyası GitHub'a yüklenmez, parola ve bağlantı bilgisi içerebilir.
E-posta (`SMTP_...`) ve yapay zekâ (`ANTHROPIC_API_KEY`) ayarları isteğe bağlıdır;
boş bırakılırsa e-posta gönderilmez ve özetler kural tabanlı şablonla yazılır.

**5. Bağlantıyı test edin**
```bash
python -m app.data.db
```

**6. Demo verisini yükleyin ve çalıştırın**
```bash
python -m app.data.seed
python -m app.presentation.web
```
`seed` tüm tabloları silip sentetik veriyle baştan doldurur. Tarayıcıda
`http://127.0.0.1:5000` adresini açın. Demo hesaplar (parola: `demo12345`):
`yonetici_mavi`, `analist_mavi`, `yonetici_yesil`, `analist_yesil`.

**7. Testler**
```bash
python -m pytest tests -v
```

**8. Canlı link (isteğe bağlı)**

`canli_link_sabit.bat` dosyasına çift tıklayın. İlk seferde ngrok'u indirir ve
ngrok anahtarınızı (authtoken) bir kez sorar; sonra siteyi ve tüneli başlatır.
Adres sabittir. Bilgisayar her açıldığında otomatik başlaması için
`otomatik_baslat.bat` bir kez çalıştırılır. Betik debug modunu her zaman kapatır.
Başka bir ngrok hesabı kullanılacaksa betikteki `ADRES` satırı o hesabın alan adıyla değiştirilir.

**9. Kullanım**

- **Pano:** tehdit seviyesi, uyarılar (açılınca konum ve özet), grafikler, son girişler.
- **Log yükle:** `.log`/`.txt`, en fazla 2 MB. Örnekler `sample_logs` klasöründe.
- **Kurallar** (yalnızca yönetici): ekle, düzenle, pasif yap, sil; “Kaydetmeden dene”.
- **Rapor:** tarih aralığı seçin; CSV indirin veya “Yazdır / PDF kaydet”.

## 8. Arayüz

Arayüz koyu bir güvenlik paneli tarzındadır: tehdit seviyesi şeridi, ölçümler,
açılır uyarı listesi (konum ve özetle), Chart.js grafikleri, kural editörü ve
yazdırılabilir güvenlik raporu. Telefon ekranına uyumludur.
`docs/pano_demo.html` Hafta 3'teki ilk tasarım prototipidir (koda gömülü sentetik veri).

## 9. Geliştirme planı

| Hafta | Konu | Durum |
|---|---|---|
| 3 | Kurulum, mimari, ER diyagramı | Tamamlandı |
| 4 | Veritabanı ve veri erişim katmanı (CRUD, sentetik veri) | Tamamlandı |
| 5 | Kullanıcı yönetimi ve kimlik doğrulama | Tamamlandı |
| 6 | Log içe aktarma ve ayrıştırma | Tamamlandı |
| 7 | Anomali tespit kuralları | Tamamlandı |
| 8 | Vize: ara sürüm, uçtan uca test, arayüz yenileme | Tamamlandı |
| 9 | IP konumu ve e-posta bildirimi | Tamamlandı |
| 10 | Yapay zekâ özeti (maskeleme, doğrulama, yedek özet) | Tamamlandı |
| 11 | Kural editörü (doğrulama, kaydetmeden dene) | Tamamlandı |
| 12 | Güvenlik raporu ve dışa aktarma (CSV, PDF) | Tamamlandı |
| 13 | Test ve hata ayıklama (101 test, güvenlik iyileştirmeleri) | Tamamlandı |
| 14 | Dokümantasyon, arayüz iyileştirme, sabit canlı link | Tamamlandı |
| 15 | Final entegrasyon ve savunma hazırlığı (v1.0.0) | Tamamlandı |

## 10. Güvenlik ve veri gizliliği

- **Gerçek kişisel veri kullanılmaz.** Tüm log verileri sentetik olarak üretilir (KVKK uyumu).
- Parolalar düz metin saklanmaz, bcrypt ile tuzlanıp hash'lenir.
- Gizli bilgiler (`.env`, API anahtarları) depoya yüklenmez.
- Şirketler arası veri izolasyonu her sorguda `sirket_id` filtresiyle sağlanır.
- Tüm formlarda CSRF anahtarı; aynı kullanıcı adına 5 hatalı girişten sonra 5 dakika kilit.
- Güvenlik başlıkları (X-Frame-Options, X-Content-Type-Options), HttpOnly ve SameSite oturum çerezi.
- CSV dışa aktarmada formül enjeksiyonu engellenir.
- IP konum servisine yalnızca IP adresi gider.
- Yapay zekâ modeline ham log gönderilmez: kullanıcı adları (`a***`) ve IP'nin son
  bölümü (`198.51.100.x`) maskelenir, şirket adı gönderilmez. Modelin cevabı
  doğrulanır; veride olmayan sayı içeren özet reddedilir.

## 11. Yapay zekâ kullanım beyanı

Bu projede yapay zekâ araçlarından yararlanılmıştır. Her kullanımın tarihi, aracı,
istemi, çıktısı ve geliştiricinin kendi katkısı
[`raporlar/`](raporlar) klasöründeki haftalık AI Kullanım Günlüğü (Word) dosyalarında kayıtlıdır.
Projedeki kodlar geliştirici tarafından incelenmiş, çalıştırılmış ve anlaşılmıştır.

## 12. Lisans ve kullanım

Bu proje ders kapsamında eğitim amaçlı geliştirilmiştir.
