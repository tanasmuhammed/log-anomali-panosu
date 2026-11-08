/* =====================================================
   Hafta 10 – Özetin kaynağı
   anomali.ai_ozeti kolonu Hafta 2'den beri vardı ama boştu.
   Artık doluyor. Bu kolon özetin nereden geldiğini söyler:
     'ai'    → yapay zekâ modeli yazdı ve doğrulamadan geçti
     'kural' → yapay zekâ kullanılamadı, hazır şablonla yazıldı
   SSMS'te bir kez çalıştırın. Tekrar çalıştırmak zararsızdır.
   ===================================================== */
USE LogAnomali;
GO

IF COL_LENGTH('anomali', 'ai_ozet_kaynagi') IS NULL
    ALTER TABLE anomali ADD ai_ozet_kaynagi NVARCHAR(10) NULL;
GO

SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'anomali' ORDER BY ORDINAL_POSITION;
