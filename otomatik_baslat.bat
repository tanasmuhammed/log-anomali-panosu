@echo off
rem ============================================================
rem  Bilgisayar her acildiginda canli linki kendiliginden baslatir.
rem  Bir kez cift tiklamak yeterli. Geri almak icin:
rem    Win+R -> shell:startup -> "Gozcu canli link.bat" dosyasini sil.
rem ============================================================
set "HEDEF=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Gozcu canli link.bat"
(
  echo @echo off
  echo timeout /t 30 /nobreak ^>nul
  echo start "Gozcu - sabit canli link" /min "%~dp0canli_link_sabit.bat"
) > "%HEDEF%"
echo Tamam. Bilgisayar her acildiginda link 30 saniye sonra kendiliginden baslayacak.
echo Link: https://nautical-tyke-latticed.ngrok-free.dev
pause
