/* =====================================================
   Hafta 9 – IP konum önbelleği
   Bir IP adresinin hangi ülke / şehir / kuruma ait olduğunu saklar.
   Aynı IP için dış servise tekrar tekrar sorgu atılmasın diye
   sonuç burada tutulur (önbellek).
   Şirkete özel DEĞİLDİR: bir IP'nin konumu herkes için aynıdır.
   SSMS'te LogAnomali veritabanı seçiliyken bir kez çalıştırın.
   Tekrar çalıştırmak zararsızdır.
   ===================================================== */
USE LogAnomali;
GO

IF OBJECT_ID('ip_konum', 'U') IS NULL
BEGIN
    CREATE TABLE ip_konum (
        ip_adresi   NVARCHAR(45)  NOT NULL PRIMARY KEY,
        ulke        NVARCHAR(80)  NULL,
        sehir       NVARCHAR(80)  NULL,
        kurulus     NVARCHAR(150) NULL,   -- internet servis sağlayıcısı / kurum
        ayrilmis    BIT           NOT NULL DEFAULT 0,  -- 1: test/özel ağ adresi, internette yeri yok
        guncelleme  DATETIME2     NOT NULL DEFAULT SYSDATETIME()
    );
END
GO

SELECT COUNT(*) AS ip_konum_satir_sayisi FROM ip_konum;
