# NIGOH AI — avtomatik o'rnatuvchi (Windows)
# Mijoz hech narsa bilishi shart emas: hammasi o'zi o'rnatiladi.
# Bajaradi: Python (bo'lmasa) -> dastur nusxasi -> kutubxonalar -> avtostart -> ULASH KODI

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
chcp 65001 > $null

$MANZIL   = "$env:LOCALAPPDATA\NigohAI"
$PY_VER   = "3.12.10"
$PY_URL   = "https://www.python.org/ftp/python/$PY_VER/python-$PY_VER-amd64.exe"

function Say($m, $c = "White") { Write-Host $m -ForegroundColor $c }
function Bosh($m) { Write-Host ""; Say ("=" * 52) Cyan; Say "  $m" Cyan; Say ("=" * 52) Cyan }

Bosh "NIGOH AI — o'rnatish boshlandi"
Say "Bu 10-20 daqiqa oladi (internet tezligiga qarab)." Gray
Say "Oynani YOPMANG. Kompyuter yoniq tursin." Gray

# ---------- 1. Python ----------
Bosh "1/5  Python tekshirilmoqda"
function Topib-Python {
    foreach ($p in @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:ProgramFiles\Python312\python.exe",
        "C:\Python312\python.exe")) {
        if (Test-Path $p) { return $p }
    }
    # Kutubxonalar Python 3.11/3.12 da sinalgan — boshqa versiya olinmaydi
    $c = Get-Command python -ErrorAction SilentlyContinue
    if ($c -and $c.Source -notlike "*WindowsApps*") {
        try {
            $v = & $c.Source -c "import sys; print('%d.%d' % sys.version_info[:2])"
            if ($v -eq "3.12" -or $v -eq "3.11") { return $c.Source }
        } catch {}
    }
    return $null
}

# Qaysi botga yozish kerakligi paket ichida keladi (dastur\bot.txt)
$BOT_MATN = "sizga berilgan botni"
$botFayl = Join-Path $PSScriptRoot "dastur\bot.txt"
if (Test-Path $botFayl) {
    $botNom = (Get-Content $botFayl -Raw).Trim().TrimStart("@")
    if ($botNom -match '^[A-Za-z0-9_]{4,40}$') { $BOT_MATN = "@$botNom botini" }
}

$py = Topib-Python
if ($py) {
    Say "Python topildi: $py" Green
} else {
    Say "Python yo'q — yuklab o'rnatilmoqda (~30 MB)..." Yellow
    $tmp = "$env:TEMP\python-setup.exe"
    Invoke-WebRequest $PY_URL -OutFile $tmp
    Say "O'rnatilmoqda (bir necha daqiqa)..." Gray
    Start-Process $tmp -ArgumentList "/quiet","InstallAllUsers=0","PrependPath=1","Include_test=0" -Wait
    Start-Sleep -Seconds 3
    $py = Topib-Python
    if (-not $py) { Say "XATO: Python o'rnatilmadi. Qo'lda o'rnating: python.org" Red; Read-Host "Enter"; exit 1 }
    Say "Python o'rnatildi." Green
}

# ---------- 2. Dastur nusxasi ----------
Bosh "2/5  Dastur ko'chirilmoqda"
# Ishlab turgan eski nusxani to'xtatamiz (aks holda yangi kod ishga tushmaydi)
try {
    Get-CimInstance Win32_Process -Filter "Name='cmd.exe'" |
        Where-Object { $_.CommandLine -like '*boshla_qurilma*' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like '*qurilma.py*' -or $_.CommandLine -like '*main.py*' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Get-Process timeout -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 5
    Say "Eski nusxa to'xtatildi." Gray
} catch {}
$manba = Join-Path $PSScriptRoot "dastur"
if (-not (Test-Path $manba)) { Say "XATO: 'dastur' papkasi topilmadi." Red; Read-Host "Enter"; exit 1 }
New-Item -ItemType Directory -Force -Path $MANZIL | Out-Null
robocopy $manba $MANZIL /E /NFL /NDL /NJH /NJS /XD .venv __pycache__ | Out-Null
Say "Joylashdi: $MANZIL" Green

# ---------- 3. Kutubxonalar ----------
Bosh "3/5  Kutubxonalar o'rnatilmoqda (eng uzun qism)"
Set-Location $MANZIL
if (-not (Test-Path "$MANZIL\.venv")) { & $py -m venv "$MANZIL\.venv" }
$vpy = "$MANZIL\.venv\Scripts\python.exe"
& $vpy -m pip install --upgrade pip --quiet
Say "Yuklanmoqda... (internet sekin bo'lsa uzoq davom etadi, kuting)" Gray
& $vpy -m pip install -r "$MANZIL\requirements.txt"
if ($LASTEXITCODE -ne 0) {
    Say "Bir urinish muvaffaqiyatsiz — qayta urinilmoqda..." Yellow
    & $vpy -m pip install -r "$MANZIL\requirements.txt"
    if ($LASTEXITCODE -ne 0) { Say "XATO: kutubxonalar o'rnatilmadi (internetni tekshiring)." Red; Read-Host "Enter"; exit 1 }
}
Say "Kutubxonalar tayyor." Green

# ---------- 4. Avtostart ----------
Bosh "4/5  Avtomatik ishga tushish sozlanmoqda"
$bat = "$MANZIL\boshla_qurilma.bat"
@"
@echo off
cd /d "$MANZIL"
:loop
".venv\Scripts\python.exe" qurilma.py >> "qurilma.log" 2>&1
timeout /t 10 /nobreak > nul
goto loop
"@ | Set-Content -Path $bat -Encoding ASCII

# Ish stolida yorliqlar — mijoz papka qidirmasin
$desktop = [Environment]::GetFolderPath('Desktop')
$sh = New-Object -ComObject WScript.Shell
$l1 = $sh.CreateShortcut((Join-Path $desktop "NigohAI - papka.lnk"))
$l1.TargetPath = $MANZIL; $l1.Save()
$l2 = $sh.CreateShortcut((Join-Path $desktop "NigohAI - ishga tushirish.lnk"))
$l2.TargetPath = $bat; $l2.WorkingDirectory = $MANZIL; $l2.Save()
$xizmat = Join-Path $MANZIL "XIZMAT-ORNATISH.bat"
if (Test-Path $xizmat) {
    $l3 = $sh.CreateShortcut((Join-Path $desktop "NigohAI - doimiy rejim (admin).lnk"))
    $l3.TargetPath = $xizmat; $l3.WorkingDirectory = $MANZIL; $l3.Save()
}
Say "Ish stolida yorliqlar yaratildi." Green

$startup = [Environment]::GetFolderPath('Startup')
$vbs = Join-Path $startup "NigohAI.vbs"
@"
Set s = CreateObject("WScript.Shell")
s.CurrentDirectory = "$MANZIL"
s.Run """$bat""", 0, False
"@ | Set-Content -Path $vbs -Encoding ASCII
Say "Kompyuter har yonganda o'zi ishga tushadi." Green

# ---------- 5. Ishga tushirish va ULASH KODI ----------
Bosh "5/5  Xizmatga ulanmoqda"
Start-Process wscript.exe -ArgumentList "`"$vbs`""
Say "Ulash kodi olinmoqda..." Gray

$kodFayl = "$MANZIL\ULASH_KODI.txt"
$holatFayl = "$MANZIL\qurilma.json"
$kod = $null
$allaqachon = $false
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Seconds 3
    if (Test-Path $kodFayl) {
        $m = (Get-Content $kodFayl -Raw) -match "([A-Z0-9]{3}-[A-Z0-9]{3})"
        if ($m) { $kod = $Matches[1]; break }
    }
    # Bu kompyuter avval ulangan bo'lsa — kod kerak emas
    if (Test-Path $holatFayl) {
        if ((Get-Content $holatFayl -Raw) -match '"token"') { $allaqachon = $true; break }
    }
}

Write-Host ""
if ($allaqachon) {
    Say ("#" * 52) Green
    Say "" Green
    Say "     BU KOMPYUTER ALLAQACHON ULANGAN" Green
    Say "" Green
    Say ("#" * 52) Green
    Write-Host ""
    Say "Xizmat ishlayapti. Telegramda $BOT_MATN ochib," Yellow
    Say "'Panelni ochish' tugmasini bosing." White
} elseif ($kod) {
    Say ("#" * 52) Green
    Say "" Green
    Say "        ULASH KODI:   $kod" Green
    Say "" Green
    Say ("#" * 52) Green
    Write-Host ""
    Say "KEYINGI QADAM:" Yellow
    Say "  1. Telegramda $BOT_MATN oching" White
    Say "  2. /start bosing va do'kon nomini yozing" White
    Say "  3. Ulash kodini yozing:  $kod" White
    Say "  4. Videoyozgich (NVR) parolini yozing" White
    Write-Host ""
    Say "Shundan keyin kameralar avtomatik topiladi va xizmat ishlaydi." Gray
    try { Start-Process notepad.exe $kodFayl } catch {}
} else {
    Say "Ulash kodi hali olinmadi." Yellow
    Say "SABABI ko'pincha ANTIVIRUS dasturni to'sadi." Yellow
    Write-Host ""
    Say "NIMA QILISH KERAK:" Yellow
    Say "  1. Antivirusda shu papkani 'ishonchli' ro'yxatga qo'shing:" White
    Say "     $MANZIL" Cyan
    Say "  2. Ish stolidagi 'NigohAI - ishga tushirish' yorlig'ini bosing" White
    Say "  3. 30 soniyadan keyin kod shu faylda chiqadi:" White
    Say "     $kodFayl" Cyan
    Write-Host ""
    Say "Xato bo'lsa shu faylga yoziladi: $MANZIL\qurilma.log" Gray
}

Write-Host ""
Say "TAVSIYA — DOIMIY ISHLASH REJIMI:" Yellow
Say "  Ish stolidagi 'NigohAI - doimiy rejim (admin)' yorlig'ini bosing." White
Say "  Shunda kompyuter yonishi bilan tizim o'zi ishga tushadi," Gray
Say "  Windows'ga kirish (login) shart bo'lmaydi, tok o'chsa ham tiklanadi." Gray
Write-Host ""
Say "O'rnatish tugadi. Bu oynani yopsangiz bo'ladi." Cyan
Read-Host "Yopish uchun Enter bosing"
