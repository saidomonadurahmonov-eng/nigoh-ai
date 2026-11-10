"""Tuzatishlar sinovi — tarmoqsiz, kamerasiz ishlaydi.

    python tests/test_tuzatishlar.py            # tez sinovlar
    python tests/test_tuzatishlar.py --video    # + sinov videosida to'liq yurgizish
                                                #   (avval: python tools/make_test_video.py)
"""
import datetime as dt
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse

ILDIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ILDIZ)
os.chdir(ILDIZ)
for _oqim in (sys.stdout, sys.stderr):      # Windows konsolida harflar buzilmasin
    try:
        _oqim.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

OTDI, YIQILDI = [], []


def tekshir(nom, shart, izoh=""):
    (OTDI if shart else YIQILDI).append(nom)
    print(f"  [{'ok' if shart else 'XATO'}] {nom}" + (f" — {izoh}" if izoh and not shart else ""))


def init_data(token, user_id, buz=False):
    """Telegram WebApp initData — berilgan token bilan imzolangan."""
    juft = {"auth_date": "1", "user": json.dumps({"id": user_id})}
    qator = "\n".join(f"{k}={juft[k]}" for k in sorted(juft))
    sir = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    h = hmac.new(sir, qator.encode(), hashlib.sha256).hexdigest()
    if buz:
        h = "0" * len(h)
    return urllib.parse.urlencode({**juft, "hash": h})


# ---------------------------------------------------------------- 1. lokal server
print("1. Lokal Mini App serveri — ruxsat tekshiruvi")
from webapp import server as ws  # noqa: E402

ws.CTX.update(token="", owner="", dev=False)
tekshir("bo'sh token: soxta imzo RAD etiladi", ws._check(init_data("", "")) is False)
tekshir("bo'sh token: bo'sh so'rov rad etiladi", ws._check("") is False)
ws.CTX.update(token="111:AAA", owner="", dev=False)
tekshir("egasi yo'q: rad etiladi", ws._check(init_data("111:AAA", "")) is False)
ws.CTX.update(token="111:AAA", owner="42", dev=False)
tekshir("to'g'ri imzo + egasi: qabul qilinadi", ws._check(init_data("111:AAA", 42)) is True)
tekshir("begona foydalanuvchi: rad etiladi", ws._check(init_data("111:AAA", 43)) is False)
tekshir("buzilgan imzo: rad etiladi", ws._check(init_data("111:AAA", 42, buz=True)) is False)
tekshir("boshqa token bilan imzo: rad etiladi", ws._check(init_data("222:BBB", 42)) is False)

# ---------------------------------------------------------------- 2. koordinata
print("2. Chiziq/zona koordinatasi (nisbiy va piksel)")
import main as asosiy  # noqa: E402

nis = {"line": [[0.5, 0.0], [0.5, 1.0]],
       "zone": [[0.25, 0.5], [0.75, 0.5], [0.75, 1.0], [0.25, 1.0]]}
p1 = asosiy.koord_piksel(nis, 704, 576)
p2 = asosiy.koord_piksel(nis, 1920, 1080)
tekshir("nisbiy -> 704x576", p1["line"] == [[352, 0], [352, 576]], str(p1))
tekshir("nisbiy -> 1920x1080", p2["line"] == [[960, 0], [960, 1080]], str(p2))
tekshir("zona ham o'tkaziladi", p2["zone"][1] == [1440, 540], str(p2))
eski = {"line": [[85, 255], [515, 218]], "zone": [[180, 250], [470, 235], [600, 480]]}
tekshir("piksel sozlama o'zgarmaydi", asosiy.koord_piksel(eski, 1920, 1080) == eski)
tekshir("chiziqsiz kamera", asosiy.koord_piksel({"channel": 3}, 704, 576) == {})

# ---------------------------------------------------------------- 3. alert profillari
print("3. Alert profillari")
import qurilma  # noqa: E402

soz = [{"kanal": 1, "nom": "kirish", "vazifa": "kirish"},
       {"kanal": 2, "nom": "kassa", "vazifa": "kassa"},
       {"kanal": 3, "nom": "zal", "vazifa": None},
       {"kanal": 4, "nom": "ombor", "vazifa": ""},
       {"kanal": 5, "nom": "kocha", "vazifa": "kocha"},
       {"kanal": 6, "nom": "yolak", "vazifa": "tahlilsiz"}]


def nomlar(q):
    return sorted(r["name"] for r in q)


eski_q = qurilma.qoidalar_yasa(soz[:4])
tekshir("profilsiz = avvalgi to'plam",
        nomlar(eski_q) == sorted(["navbat_uzun", "kassada_odam", "kirishda_odam",
                                  "kassada_notanish", "tunda_kirish", "tunda_kassa",
                                  "tunda_zal", "tunda_ombor", "harakat_zal",
                                  "harakat_ombor"]), str(nomlar(eski_q)))
tun = next(r for r in eski_q if r["name"] == "tunda_zal")
kun = next(r for r in eski_q if r["name"] == "harakat_zal")
tekshir("profilsiz: tun 22-07, kun 07-22",
        (tun["soat_dan"], tun["soat_gacha"], kun["soat_dan"], kun["soat_gacha"])
        == (22, 7, 7, 22))

dq = qurilma.qoidalar_yasa(soz, profil={"nom": "dokon", "ish_dan": 9, "ish_gacha": 20})
tekshir("dokon: faqat navbat + ishdan tashqari harakat",
        nomlar(dq) == sorted(["navbat_uzun", "tunda_kirish", "tunda_kassa",
                              "tunda_zal", "tunda_ombor"]), str(nomlar(dq)))
t = next(r for r in dq if r["name"] == "tunda_zal")
tekshir("dokon: ish soati profildan (20 -> 09)", (t["soat_dan"], t["soat_gacha"]) == (20, 9))
tekshir("dokon: ko'cha kamerasida tungi alert yo'q",
        not any(r["kamera"] == "kocha" for r in dq))
tekshir("tahlilsiz kameraga qoida yo'q",
        not any(r["kamera"] == "yolak" for r in dq + qurilma.qoidalar_yasa(soz)))
tekshir("ombor: ko'cha kamerasida harakat alerti yo'q",
        not any(r["kamera"] == "kocha" for r in qurilma.qoidalar_yasa(soz)))
tekshir("jim: qoida yo'q", qurilma.qoidalar_yasa(soz, profil={"nom": "jim"}) == [])
aniq = [{"name": "x", "kamera": "zal", "metrika": "kadrda"}]
tekshir("bulut bergan qoidalar o'zgarmaydi",
        qurilma.qoidalar_yasa(soz, qoidalar=aniq, profil={"nom": "jim"}) is aniq)

from events.engine import RuleEngine  # noqa: E402

eng = RuleEngine([dict(t, davomiylik=0, cooldown=0)])


def soat(kun, s):
    return dt.datetime(2026, 11, kun, s, 30).timestamp()


tekshir("dokon tungi qoida 22:30 da ishlaydi",
        len(eng.update("zal", {"kadrda": 1}, soat(10, 22))) == 1)
tekshir("dokon tungi qoida 03:30 da ishlaydi (yarim tundan keyin)",
        len(eng.update("zal", {"kadrda": 1}, soat(11, 3))) == 1)
tekshir("dokon tungi qoida 12:30 da JIM",
        eng.update("zal", {"kadrda": 5}, soat(11, 12)) == [])

# ---------------------------------------------------------------- 4. config yozish
print("4. config.yaml yozish")
import yaml  # noqa: E402

with tempfile.TemporaryDirectory() as vaqt:
    os.chdir(vaqt)
    try:
        qurilma.BULUT = "https://sinov.example"
        qurilma.holat_yoz({"nvr": {"ip": "10.0.0.5", "user": "admin", "pass": "p"},
                           "token": "tok"})
        soz2 = [dict(k) for k in soz]
        soz2[0]["line"] = [[0.1, 0.4], [0.7, 0.4]]
        ozgardi = qurilma.config_yoz(soz2, None, {"nom": "dokon"})
        conf = yaml.safe_load(open("config.yaml", encoding="utf-8"))
        tekshir("config yozildi", ozgardi is True)
        tekshir("tahlilsiz kamera tahlilga qo'shilmadi",
                sorted(conf["cameras"]) == ["kassa", "kirish", "kocha", "ombor", "zal"],
                str(sorted(conf["cameras"])))
        tekshir("nisbiy chiziq o'zgarishsiz o'tdi",
                conf["cameras"]["kirish"]["line"] == [[0.1, 0.4], [0.7, 0.4]])
        tekshir("bulut manzili sozlamaga yozildi", conf["railway_url"] == "https://sinov.example")
        tekshir("lokal bot tokeni bo'sh (bulut rejimi)", conf["telegram"]["token"] == "")
        tekshir("qoidalar profil bo'yicha", nomlar(conf["rules"]) == nomlar(dq))
        tekshir("o'zgarmasa qayta yozilmaydi",
                qurilma.config_yoz(soz2, None, {"nom": "dokon"}) is False)
        tekshir("profil o'zgarsa qayta yoziladi",
                qurilma.config_yoz(soz2, None, {"nom": "jim"}) is True)
    finally:
        os.chdir(ILDIZ)

# ---------------------------------------------------------------- 5. bulut va bot
print("5. Bulut manzili va bot nomi")
with tempfile.TemporaryDirectory() as vaqt:
    asl_papka, asl_env = qurilma.PAPKA, os.environ.pop("BULUT_URL", None)
    qurilma.PAPKA = vaqt
    try:
        tekshir("standart bulut manzili YO'Q", qurilma._bulut_manzil() == "")
        tekshir("bot.txt yo'q: bot nomi bo'sh", qurilma.bot_nomi({}) == "")
        open(os.path.join(vaqt, "bulut.txt"), "w", encoding="utf-8").write(
            "https://meniki.example/\n")
        tekshir("bulut.txt o'qiladi", qurilma._bulut_manzil() == "https://meniki.example")
        open(os.path.join(vaqt, "bulut.txt"), "w", encoding="utf-8").write("ftp://x\n")
        tekshir("https bo'lmagan manzil olinmaydi", qurilma._bulut_manzil() == "")
        open(os.path.join(vaqt, "bot.txt"), "w", encoding="utf-8-sig").write("@Mening_bot\n")
        tekshir("bot.txt o'qiladi (BOM bilan ham)", qurilma.bot_nomi({}) == "@Mening_bot")
        tekshir("bulut aytgan bot ustun", qurilma.bot_nomi({"bot": "Bulut_bot"}) == "@Bulut_bot")
        tekshir("noto'g'ri bot nomi olinmaydi", qurilma.bot_nomi({"bot": "a b<script>"}) == "@Mening_bot"
                or qurilma.bot_nomi({"bot": "a b<script>"}) == "")
        os.environ["BULUT_URL"] = "https://env.example/"
        tekshir("BULUT_URL ustun", qurilma._bulut_manzil() == "https://env.example")
    finally:
        qurilma.PAPKA = asl_papka
        os.environ.pop("BULUT_URL", None)
        if asl_env:
            os.environ["BULUT_URL"] = asl_env

# ---------------------------------------------------------------- 6. video (ixtiyoriy)
if "--video" in sys.argv:
    print("6. Sinov videosi: piksel va nisbiy chiziq bir xil sanaydimi")
    video = os.path.join(ILDIZ, "sinov_video.mp4")
    if not os.path.exists(video):
        tekshir("sinov_video.mp4 bor", False, "avval tools/make_test_video.py")
    else:
        natija = {}
        with tempfile.TemporaryDirectory() as vaqt:
            for nom, chiziq in (("piksel", [[480, 0], [480, 540]]),
                                ("nisbiy", [[0.5, 0.0], [0.5, 1.0]])):
                yol = os.path.join(vaqt, f"{nom}.yaml")
                yaml.safe_dump({
                    "cameras": {"sinov": {"source": video, "fps": 5, "line": chiziq}},
                    "telegram": {"token": "", "chat_id": ""},
                    "db": os.path.join(vaqt, f"{nom}.db"),
                    "arxiv": os.path.join(vaqt, "arxiv"),
                    "odam_indeks": False, "rules": []}, open(yol, "w", encoding="utf-8"))
                chiq = subprocess.run([sys.executable, "main.py", "--config", yol],
                                      capture_output=True, text=True, encoding="utf-8",
                                      errors="replace", timeout=600, cwd=ILDIZ)
                m = re.search(r"YAKUN: kirdi=(\d+) chiqdi=(\d+)", chiq.stdout)
                natija[nom] = (int(m.group(1)), int(m.group(2))) if m else None
                tekshir(f"{nom}: yurgizildi", m is not None,
                        (chiq.stdout + chiq.stderr)[-400:])
                tekshir(f"{nom}: lokal server ochilmadi",
                        "Lokal Mini App serveri o'chiq" in chiq.stdout)
        print(f"     natija: {natija}")
        tekshir("odam sanaldi (0 emas)", bool(natija.get("piksel")) and sum(natija["piksel"]) > 0)
        tekshir("piksel = nisbiy", natija.get("piksel") == natija.get("nisbiy"), str(natija))

print(f"\nNATIJA: {len(OTDI)}/{len(OTDI) + len(YIQILDI)} o'tdi")
if YIQILDI:
    print("YIQILGANLAR:", "; ".join(YIQILDI))
sys.exit(1 if YIQILDI else 0)
