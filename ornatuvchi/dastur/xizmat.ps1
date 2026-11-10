# NIGOH AI — doimiy ishlash rejimi (Windows vazifasi, tizim hisobidan).
# Administrator huquqi bilan ishga tushiriladi (XIZMAT-ORNATISH.bat orqali).
# Natija: kompyuter yonishi bilan tizim ishlaydi, login SHART EMAS.

$ErrorActionPreference = "Stop"
chcp 65001 > $null
$PAPKA = $PSScriptRoot
$BAT = Join-Path $PAPKA "boshla_qurilma.bat"

function Say($m, $c = "White") { Write-Host $m -ForegroundColor $c }

Say ""
Say "====================================================" Cyan
Say "   NIGOH AI - DOIMIY ISHLASH REJIMI" Cyan
Say "====================================================" Cyan
Say ""
Say "Kompyuter yonishi bilan tizim ishga tushadi." Gray
Say "Windows'ga kirish (login) SHART EMAS." Gray
Say "Tok o'chib yonsa o'zi tiklanadi." Gray
Say ""
Say "Papka: $PAPKA" Gray
Say ""

if (-not (Test-Path $BAT)) { Say "XATO: boshla_qurilma.bat topilmadi." Red; Read-Host "Enter"; exit 1 }

# --- 1. Vazifa ---
Say "[1/4] Windows vazifasi yaratilmoqda..." White
try {
    $action = New-ScheduledTaskAction -Execute $BAT -WorkingDirectory $PAPKA
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $trigger.Delay = "PT1M"          # tarmoq ko'tarilishi uchun 1 daqiqa kutadi
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries -StartWhenAvailable `
        -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit ([TimeSpan]::Zero)
    Register-ScheduledTask -TaskName "NigohAI" -Action $action -Trigger $trigger `
        -Principal $principal -Settings $settings -Force | Out-Null
    Say "      yaratildi (tizim hisobidan, yonishda 1 daqiqa kechikish)" Green
} catch {
    Say "      XATO: $($_.Exception.Message)" Red
    Say "      Administrator huquqi bilan ishga tushiring." Yellow
    Read-Host "Enter"
    exit 1
}

# --- 2. Eski avtostart (login orqali) endi kerak emas ---
Say "[2/4] Eski avtostart olib tashlanmoqda..." White
$topildi = 0
foreach ($prof in (Get-ChildItem "C:\Users" -Directory -ErrorAction SilentlyContinue)) {
    $p = Join-Path $prof.FullName "AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\NigohAI.vbs"
    if (Test-Path $p) { Remove-Item $p -Force -ErrorAction SilentlyContinue; $topildi++ }
}
Say "      $topildi ta olib tashlandi (endi vazifa boshqaradi)" Green

# --- 3. Ishlab turgan nusxani to'xtatamiz ---
Say "[3/4] Eski nusxa to'xtatilmoqda..." White
Get-CimInstance Win32_Process -Filter "Name='cmd.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like '*boshla_qurilma*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like '*qurilma.py*' -or $_.CommandLine -like '*main.py*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Get-Process timeout -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 6
Say "      to'xtatildi" Green

# --- 4. Ishga tushiramiz ---
Say "[4/4] Xizmat ishga tushirilmoqda..." White
Start-ScheduledTask -TaskName "NigohAI"
Start-Sleep -Seconds 15
$n = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
       Where-Object { $_.CommandLine -like '*qurilma.py*' }).Count
if ($n -gt 0) { Say "      ISHLAYAPTI" Green } else { Say "      ko'tarilmoqda (1-2 daqiqa)" Yellow }

Say ""
Say "====================================================" Green
Say "   TAYYOR" Green
Say "====================================================" Green
Say ""
Say "Endi kompyuterni o'chirib yoqsangiz ham tizim o'zi ishlaydi." White
Say "Login qilish shart emas." White
Say ""
Say "Tekshirish:  Telegramda botni ochib 'Panelni ochish'" Gray
Say "O'chirish:   Unregister-ScheduledTask -TaskName NigohAI -Confirm:`$false" Gray
Say ""
Read-Host "Yopish uchun Enter bosing"
