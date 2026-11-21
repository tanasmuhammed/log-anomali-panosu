@echo off
rem ============================================================
rem  Gozcu - SABIT canli link (ngrok)
rem  Adres hic degismez:  https://nautical-tyke-latticed.ngrok-free.dev
rem  Cift tikla. Iki pencere acilir:
rem    1) "Gozcu sunucu" : Flask uygulamasi
rem    2) bu pencere     : ngrok tuneli
rem  Link, bu iki pencere acik ve bilgisayar uyanik oldugu surece calisir.
rem ============================================================
title Gozcu - sabit canli link
cd /d "%~dp0"
set "ADRES=nautical-tyke-latticed.ngrok-free.dev"

rem --- Sanal ortami bul ---
set "PY=venv\Scripts\python.exe"
if not exist "%PY%" set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" goto venv_yok

rem --- Guvenlik: canli linkte debug her zaman kapali ---
set "FLASK_DEBUG=0"

rem --- ngrok'u bul, yoksa kur ---
call :ng_bul
if defined NG goto ng_hazir
echo ngrok bulunamadi, indiriliyor (tek seferlik, 1-2 dakika)...
if not exist "araclar" mkdir "araclar"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol='Tls12'; Invoke-WebRequest -Uri 'https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip' -OutFile 'araclar\ngrok.zip'; Expand-Archive -Force 'araclar\ngrok.zip' 'araclar'; Remove-Item 'araclar\ngrok.zip'"
call :ng_bul
if not defined NG goto ng_yok

:ng_hazir
rem --- Anahtar (authtoken) daha once girilmediyse bir kez sor ---
findstr /c:"authtoken" "%LOCALAPPDATA%\ngrok\ngrok.yml" >nul 2>&1
if errorlevel 1 (
  echo.
  echo ngrok anahtari bir kez girilmeli.
  echo dashboard.ngrok.com sitesinde "Your Authtoken" sayfasindaki
  echo anahtari kopyalayip buraya yapistir ve Enter'a bas:
  set /p TOKEN=Authtoken: 
  call "%NG%" config add-authtoken %%TOKEN%%
)

rem --- Sunucu zaten calisiyorsa ikinci kez baslatma ---
netstat -ano | findstr ":5000 " | findstr "LISTENING" >nul
if errorlevel 1 (
  echo [1/2] Site ayri pencerede baslatiliyor...
  start "Gozcu sunucu" /min cmd /k %PY% -m app.presentation.web
  timeout /t 5 /nobreak >nul
) else (
  echo [1/2] Site zaten calisiyor.
)

echo [2/2] Tunel aciliyor...
echo.
echo ============================================================
echo  Link:   https://%ADRES%
echo  Giris:  yonetici_mavi / demo12345
echo  Ilk acilista ngrok bir uyari sayfasi gosterir: "Visit Site" denir.
echo  Kapatmak icin bu pencerede Ctrl+C, sonra sunucu penceresini kapat.
echo ============================================================
echo.
"%NG%" http --url=%ADRES% 5000
pause
exit /b 0

:ng_bul
set "NG="
if exist "%~dp0araclar\ngrok.exe" set "NG=%~dp0araclar\ngrok.exe"
if defined NG exit /b 0
for %%P in (ngrok.exe) do set "NG=%%~$PATH:P"
if not defined NG if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\ngrok.exe" set "NG=%LOCALAPPDATA%\Microsoft\WinGet\Links\ngrok.exe"
exit /b 0

:venv_yok
echo [HATA] Sanal ortam bulunamadi. Proje klasorunde venv klasoru olmali.
pause
exit /b 1

:ng_yok
echo [HATA] ngrok indirilemedi. Internet baglantisini kontrol edip tekrar calistir.
echo Olmazsa: ngrok.com/download adresinden Windows zip dosyasini indir,
echo icindeki ngrok.exe dosyasini proje klasorundeki "araclar" klasorune koy.
pause
exit /b 1
