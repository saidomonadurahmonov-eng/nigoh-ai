@echo off
title Eski tizimni to'xtatish
chcp 65001 > nul
echo.
echo ====================================================
echo   ESKI TIZIMNI TO'XTATISH
echo ====================================================
echo.
echo Bu skript eski video analitika tizimini to'xtatadi
echo va uning avtomatik ishga tushishini o'chiradi.
echo Fayllar va ma'lumotlar O'CHIRILMAYDI.
echo.
pause

echo.
echo [1/3] Avtostart o'chirilmoqda...
if exist "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\video-analitika.vbs" (
    del /f /q "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\video-analitika.vbs"
    echo       o'chirildi
) else (
    echo       topilmadi ^(allaqachon o'chirilgan^)
)

echo [2/3] Ishlab turgan jarayonlar to'xtatilmoqda...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='cmd.exe'\" | Where-Object { $_.CommandLine -like '*boshla.bat*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*main.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
powershell -NoProfile -Command "Get-Process timeout -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue"
timeout /t 4 /nobreak > nul
echo       to'xtatildi

echo [3/3] Tekshirilmoqda...
powershell -NoProfile -Command "$n = @(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*main.py*' }).Count; if ($n -eq 0) { Write-Host '      TOZA - eski tizim to''xtadi' -ForegroundColor Green } else { Write-Host \"      DIQQAT: $n jarayon hali ishlayapti\" -ForegroundColor Yellow }"

echo.
echo ====================================================
echo   TAYYOR
echo ====================================================
echo.
echo Endi yangi xizmatni o'rnating:
echo   ORNATISH.bat  faylini ikki marta bosing
echo.
pause
