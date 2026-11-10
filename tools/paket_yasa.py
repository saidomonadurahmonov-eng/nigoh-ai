"""O'rnatuvchi paketini (zip) yig'adi — obyekt kompyuteriga olib boriladigan fayl.

Paket ichida: o'rnatuvchi skriptlar + dastur kodi + qaysi bulutga va qaysi
botga ulanishi + (bor bo'lsa) model fayllari. Mijoz zipni ochib ORNATISH.bat
ni bosadi, xolos.

    python tools/paket_yasa.py --bulut https://mening-serverim.example \
        --bot Mening_bot --chiqish Nigoh-ornatuvchi.zip

--bulut   qurilma ulanadigan bulut manzili (MAJBURIY — standart manzil yo'q)
--bot     mijoz yozadigan Telegram bot nomi (@ belgisisiz ham bo'ladi)
--modelsiz  model fayllarini qo'shmaslik (paket ~50 MB kichrayadi, lekin
            obyektda birinchi ishga tushishda internetdan yuklanadi)

Modellar oldindan yuklangan bo'lishi kerak: python tools/modellar_yukla.py
"""
import argparse
import glob
import os
import re
import shutil
import sys
import tempfile
import zipfile

ILDIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORN = os.path.join(ILDIZ, "ornatuvchi")

KOD_PAPKALAR = ["analysis", "bot", "events", "nvr", "report", "storage",
                "vision", "webapp"]
KOD_FAYLLAR = ["main.py", "qurilma.py", "requirements.txt", "LICENSE"]
ORN_FAYLLAR = ["ORNATISH.bat", "ornat.ps1", "OQING.txt", "ESKINI-TOXTATISH.bat"]
ORN_DASTUR = ["XIZMAT-ORNATISH.bat", "xizmat.ps1"]
BOM = b"\xef\xbb\xbf"


def _nusxa(manba, manzil):
    os.makedirs(os.path.dirname(manzil), exist_ok=True)
    shutil.copy2(manba, manzil)


def _kod_papka(nom, dastur):
    for ildiz, papkalar, fayllar in os.walk(os.path.join(ILDIZ, nom)):
        papkalar[:] = [p for p in papkalar if p != "__pycache__"]
        for f in fayllar:
            if f.endswith((".pyc", ".pyo")):
                continue
            to_liq = os.path.join(ildiz, f)
            _nusxa(to_liq, os.path.join(dastur, os.path.relpath(to_liq, ILDIZ)))


def _modellar(dastur):
    """Bor model fayllarini paketga qo'shadi. Qo'shilganlar ro'yxatini qaytaradi."""
    qoshildi = []
    yolo = os.path.join(ILDIZ, "yolo11n.pt")
    if os.path.exists(yolo):
        _nusxa(yolo, os.path.join(dastur, "yolo11n.pt"))
        qoshildi.append("yolo11n.pt")
    for f in glob.glob(os.path.join(ILDIZ, "models", "*.onnx")):
        _nusxa(f, os.path.join(dastur, "models", os.path.basename(f)))
        qoshildi.append(os.path.basename(f))
    # mobilenet: avval dastur yonidan, bo'lmasa foydalanuvchi keshidan
    nomzod = glob.glob(os.path.join(ILDIZ, "models", "torch", "hub",
                                    "checkpoints", "mobilenet_v3_small-*.pth"))
    nomzod += glob.glob(os.path.join(os.path.expanduser("~"), ".cache", "torch",
                                     "hub", "checkpoints",
                                     "mobilenet_v3_small-*.pth"))
    if nomzod:
        _nusxa(nomzod[0], os.path.join(dastur, "models", "torch", "hub",
                                       "checkpoints", os.path.basename(nomzod[0])))
        qoshildi.append(os.path.basename(nomzod[0]))
    return qoshildi


def main():
    ap = argparse.ArgumentParser(description="O'rnatuvchi paketini yig'ish")
    ap.add_argument("--bulut", required=True, help="bulut manzili (https://...)")
    ap.add_argument("--bot", default="", help="Telegram bot nomi")
    ap.add_argument("--chiqish", default="Nigoh-ornatuvchi.zip")
    ap.add_argument("--modelsiz", action="store_true")
    a = ap.parse_args()

    bulut = a.bulut.strip().rstrip("/")
    if not re.match(r"^https://[A-Za-z0-9.-]+(:\d+)?(/.*)?$", bulut):
        sys.exit("XATO: --bulut https:// bilan boshlanadigan manzil bo'lishi kerak")
    bot = a.bot.strip().lstrip("@")
    if bot and not re.fullmatch(r"[A-Za-z0-9_]{4,40}", bot):
        sys.exit("XATO: --bot noto'g'ri (faqat harf, raqam, _)")

    # PowerShell 5.1 BOM'siz UTF-8 faylni buzib o'qiydi — o'rnatuvchi ishlamay qoladi
    with open(os.path.join(ORN, "ornat.ps1"), "rb") as f:
        if f.read(3) != BOM:
            sys.exit("XATO: ornatuvchi/ornat.ps1 UTF-8 BOM bilan saqlanmagan")

    vaqtincha = tempfile.mkdtemp(prefix="nigoh_paket_")
    try:
        dastur = os.path.join(vaqtincha, "dastur")
        for f in ORN_FAYLLAR:
            _nusxa(os.path.join(ORN, f), os.path.join(vaqtincha, f))
        for f in ORN_DASTUR:
            _nusxa(os.path.join(ORN, "dastur", f), os.path.join(dastur, f))
        for f in KOD_FAYLLAR:
            manba = os.path.join(ILDIZ, f)
            if os.path.exists(manba):
                _nusxa(manba, os.path.join(dastur, f))
        for p in KOD_PAPKALAR:
            _kod_papka(p, dastur)
        with open(os.path.join(dastur, "bulut.txt"), "w", encoding="utf-8") as f:
            f.write(bulut + "\n")
        if bot:
            with open(os.path.join(dastur, "bot.txt"), "w", encoding="utf-8") as f:
                f.write(bot + "\n")
        modellar = [] if a.modelsiz else _modellar(dastur)

        chiqish = os.path.abspath(a.chiqish)
        os.makedirs(os.path.dirname(chiqish), exist_ok=True)
        soni = 0
        with zipfile.ZipFile(chiqish, "w", zipfile.ZIP_DEFLATED) as z:
            for ildiz, _, fayllar in os.walk(vaqtincha):
                for f in fayllar:
                    to_liq = os.path.join(ildiz, f)
                    z.write(to_liq, os.path.relpath(to_liq, vaqtincha))
                    soni += 1
    finally:
        shutil.rmtree(vaqtincha, ignore_errors=True)

    mb = os.path.getsize(chiqish) / 1048576
    print(f"TAYYOR: {chiqish}")
    print(f"  {soni} fayl, {mb:.1f} MB")
    print(f"  bulut: {bulut}")
    print(f"  bot:   {'@' + bot if bot else '(berilmagan — bulut o`zi aytadi)'}")
    print(f"  modellar: {', '.join(modellar) if modellar else 'YO`Q (obyektda yuklanadi)'}")


if __name__ == "__main__":
    main()
