"""Do'kon qurilmasi (quti yoki mijoz kompyuteri) — xizmatga ulanish boshqaruvchisi.

Nima qiladi:
  1. O'zini bulutda ro'yxatga oladi -> ULASH KODI ni ekranga chiqaradi
  2. Mijoz kodni botga yozgach — doimiy token oladi
  3. Bulutdan topshiriq oladi: NVR parolini sinab, kameralarni topadi
  4. Bulutdan sozlamani olib config.yaml yozadi va tahlilni (main.py) ishga tushiradi

Bulutga faqat TASHQARIGA ulanadi — kompyuter internetga ochilmaydi.
Ishga tushirish:  python qurilma.py
"""
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import requests
import yaml
from requests.auth import HTTPDigestAuth

# Windows konsolida o'zbekcha/belgilar buzilmasin
for _oqim in (sys.stdout, sys.stderr):
    try:
        _oqim.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

PAPKA = os.path.dirname(os.path.abspath(__file__))
VERSIYA = 8


def _yonidagi(nom) -> str:
    """Dastur yonidagi kichik matn faylini o'qiydi (bulut.txt, bot.txt)."""
    try:
        with open(os.path.join(PAPKA, nom), encoding="utf-8-sig") as f:
            return f.read().strip()
    except OSError:
        return ""


def _bulut_manzil() -> str:
    """Bulut manzili: BULUT_URL muhit o'zgaruvchisi > yonidagi bulut.txt.
    Standart manzil YO'Q — har o'rnatma qaysi serverga ulanishini aniq biladi
    (o'rnatuvchi paketi bulut.txt ni o'zi qo'yadi)."""
    if os.environ.get("BULUT_URL"):
        return os.environ["BULUT_URL"].rstrip("/")
    m = _yonidagi("bulut.txt")
    return m.rstrip("/") if m.startswith("http") else ""


BULUT = _bulut_manzil()
BOT = ""                      # bulut aytadi; aytmasa yonidagi bot.txt
HOLAT_FAYL = "qurilma.json"
KOD_FAYL = "ULASH_KODI.txt"
CONFIG = "config.yaml"
TAHLILSIZ = "tahlilsiz"       # kamera vazifasi: faqat jonli ko'rish, tahlil yo'q
KOCHA = "kocha"               # ko'cha kamerasi: harakat alertlari berilmaydi


# ---------------- qurilma kimligi ----------------
def device_id():
    """Shu kompyuter uchun barqaror identifikator."""
    h = json.load(open(HOLAT_FAYL, encoding="utf-8")) if os.path.exists(HOLAT_FAYL) else {}
    if h.get("device_id"):
        return h["device_id"]
    xom = f"{uuid.getnode()}-{socket.gethostname()}"
    did = "uc" + hashlib.sha256(xom.encode()).hexdigest()[:22]
    holat_yoz({"device_id": did})
    return did


def holat_ol():
    if os.path.exists(HOLAT_FAYL):
        try:
            return json.load(open(HOLAT_FAYL, encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return {}


def holat_yoz(yangi):
    h = holat_ol()
    h.update(yangi)
    with open(HOLAT_FAYL, "w", encoding="utf-8") as f:
        json.dump(h, f, ensure_ascii=False, indent=2)
    return h


# ---------------- tarmoqdan NVR topish ----------------
def lokal_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


def _port_ochiq(ip, port=80, timeout=0.4):
    s = socket.socket()
    s.settimeout(timeout)
    try:
        return s.connect_ex((ip, port)) == 0
    finally:
        s.close()


def nomzodlar():
    """Tarmoqda 80- yoki 554-porti ochiq qurilmalar (NVR/kamera bo'lishi mumkin)."""
    baza = ".".join(lokal_ip().split(".")[:3])
    ips = [f"{baza}.{i}" for i in range(1, 255)]
    with ThreadPoolExecutor(64) as ex:
        p80 = list(ex.map(lambda i: _port_ochiq(i, 80), ips))
        p554 = list(ex.map(lambda i: _port_ochiq(i, 554), ips))
    return [ip for ip, a, b in zip(ips, p80, p554) if a or b]


def kanallarni_ol(ip, login, parol):
    """ISAPI orqali kameralar ro'yxati. Muvaffaqiyatsiz bo'lsa None."""
    try:
        r = requests.get(f"http://{ip}/ISAPI/Streaming/channels",
                         auth=HTTPDigestAuth(login, parol), timeout=8)
        if r.status_code != 200 or "StreamingChannel" not in r.text:
            return None
        idlar = {int(m) // 100 for m in re.findall(r"<id>(\d+)</id>", r.text)}
        return sorted(k for k in idlar if k > 0)
    except requests.RequestException:
        return None


def nvr_top(login, parol):
    """Tarmoqdan NVR/kamerani topib, kanallar ro'yxatini qaytaradi."""
    for ip in nomzodlar():
        kanallar = kanallarni_ol(ip, login, parol)
        if kanallar:
            return ip, kanallar
    return None, []


# ---------------- topshiriqlar ----------------
def job_nvr_sozlash(payload):
    login = payload.get("login", "admin")
    parol = payload.get("parol", "")
    print("[qurilma] tarmoq skanerlanmoqda...", flush=True)
    ip, kanallar = nvr_top(login, parol)
    if not ip:
        return {"ok": False, "xabar": "NVR topilmadi yoki parol xato"}
    holat_yoz({"nvr": {"ip": ip, "user": login, "pass": parol}})
    print(f"[qurilma] NVR topildi: {ip}, {len(kanallar)} kamera", flush=True)
    return {"ok": True, "ip": ip,
            "kameralar": [{"kanal": k, "nom": f"kamera{k}"} for k in kanallar]}


def job_surat(payload):
    """Kameradan bitta surat olib bulutga yuklaydi (panelda chizish uchun)."""
    h = holat_ol()
    nvr = h.get("nvr")
    if not nvr:
        return {"ok": False, "xabar": "NVR sozlanmagan"}
    kanal = int(payload.get("kanal", 1))
    try:
        r = requests.get(
            f"http://{nvr['ip']}/ISAPI/Streaming/channels/{kanal}01/picture",
            auth=HTTPDigestAuth(nvr["user"], nvr["pass"]), timeout=20)
        if r.status_code != 200 or not r.content:
            return {"ok": False, "xabar": f"kamera javob bermadi ({r.status_code})"}
        requests.post(f"{BULUT}/device/snapshot/{payload['_job_id']}?kanal={kanal}",
                      headers={"X-Device-Token": h.get("token", ""),
                               "Content-Type": "image/jpeg"},
                      data=r.content, timeout=60)
        return None            # natija yuklash bilan birga yuborildi
    except requests.RequestException as e:
        return {"ok": False, "xabar": str(e)}


JOBLAR = {"nvr_sozlash": job_nvr_sozlash, "surat": job_surat}


# ---------------- sozlamani yozish ----------------
def _soat(qiymat, standart):
    try:
        return int(qiymat) % 24
    except (TypeError, ValueError):
        return standart


def qoidalar_yasa(sozlama, qoidalar=None, profil=None):
    """Alert qoidalari: bulutdan kelgani yoki profil bo'yicha standart to'plam.

    profil = {"nom": "ombor" | "dokon" | "jim", "ish_dan": 8, "ish_gacha": 21}
      ombor — sokin joy (ombor, ofis): har harakat haqida xabar (eski to'plam)
      dokon — gavjum savdo zali: faqat ishdan tashqari harakat va uzun navbat
      jim   — hech qanday qoida (faqat "kamera uzildi" xabari qoladi)
    """
    if qoidalar:
        return qoidalar
    p = profil or {}
    nom_p = str(p.get("nom") or "ombor").lower()
    sozlama = [k for k in sozlama if k.get("vazifa") != TAHLILSIZ]
    kirish = next((k["nom"] for k in sozlama if k.get("vazifa") == "kirish"), None)
    kassa = next((k["nom"] for k in sozlama if k.get("vazifa") == "kassa"), None)
    if nom_p == "jim":
        return []
    if nom_p == "dokon":
        ish_dan, ish_gacha = _soat(p.get("ish_dan"), 8), _soat(p.get("ish_gacha"), 21)
        q = []
        if kassa:
            q.append({"name": "navbat_uzun", "kamera": kassa, "metrika": "navbat",
                      "chegara": 3, "davomiylik": 45, "cooldown": 900,
                      "xabar": "Kassada navbat: {navbat} kishi, kutish {kutish}s"})
        for k in sozlama:
            if k.get("vazifa") == KOCHA:
                continue          # ko'chadan o'tgan odam — hodisa emas
            nom = k.get("nom") or f"kamera{k['kanal']}"
            q.append({"name": f"tunda_{nom}", "kamera": nom, "metrika": "kadrda",
                      "chegara": 1, "davomiylik": 5, "cooldown": 900,
                      "soat_dan": ish_gacha, "soat_gacha": ish_dan,
                      "xabar": "🚨 ISHDAN TASHQARI HARAKAT! " + nom
                               + ": {kadrda} kishi"})
        return q
    # --- "ombor": avvalgi to'plam (mavjud o'rnatmalar shu bilan ishlaydi) ---
    tun_dan, tun_gacha = _soat(p.get("ish_gacha"), 22), _soat(p.get("ish_dan"), 7)
    q = []
    if kassa:
        q.append({"name": "navbat_uzun", "kamera": kassa, "metrika": "navbat",
                  "chegara": 3, "davomiylik": 45, "cooldown": 600,
                  "xabar": "Kassada navbat: {navbat} kishi, kutish {kutish}s"})
        q.append({"name": "kassada_odam", "kamera": kassa, "metrika": "kadrda",
                  "chegara": 1, "davomiylik": 5, "cooldown": 900,
                  "xabar": "Kassada harakat: {kadrda} kishi"})
    if kirish:
        q.append({"name": "kirishda_odam", "kamera": kirish, "metrika": "kadrda",
                  "chegara": 1, "davomiylik": 3, "cooldown": 600,
                  "xabar": "Kirishda odam ko'rindi ({kadrda} kishi)"})
    if kassa:
        # Kassada yuzi tanilmagan odam uzoq turса — xavfsizlik ogohlantirishi
        q.append({"name": "kassada_notanish", "kamera": kassa,
                  "metrika": "notanish", "chegara": 1, "davomiylik": 40,
                  "cooldown": 1200,
                  "xabar": "DIQQAT: kassada notanish odam ({notanish} kishi) "
                           "40 soniyadan beri turibdi"})
    # TUNGI HARAKAT — eng muhim xavfsizlik qoidasi (do'kon yopiq payt)
    for k in sozlama:
        if k.get("vazifa") == KOCHA:
            continue
        nom = k.get("nom") or f"kamera{k['kanal']}"
        q.append({"name": f"tunda_{nom}", "kamera": nom, "metrika": "kadrda",
                  "chegara": 1, "davomiylik": 5, "cooldown": 600,
                  "soat_dan": tun_dan, "soat_gacha": tun_gacha,
                  "xabar": "🚨 TUNDA HARAKAT! " + nom + ": {kadrda} kishi "
                           "(do'kon yopiq payt)"})
    # Kunduzi har kamerada harakat (kam-kam xabar bersin)
    for k in sozlama:
        nom = k.get("nom") or f"kamera{k['kanal']}"
        if nom in (kirish, kassa) or k.get("vazifa") == KOCHA:
            continue
        q.append({"name": f"harakat_{nom}", "kamera": nom, "metrika": "kadrda",
                  "chegara": 1, "davomiylik": 10, "cooldown": 1800,
                  "soat_dan": tun_gacha, "soat_gacha": tun_dan,
                  "xabar": nom + ": harakat ({kadrda} kishi)"})
    return q


def config_yoz(sozlama, qoidalar=None, profil=None):
    """Bulutdagi sozlamadan config.yaml yasaydi. O'zgargan bo'lsa True."""
    h = holat_ol()
    nvr = h.get("nvr")
    if not nvr or not sozlama:
        return False
    cams = {}
    for k in sozlama:
        if k.get("vazifa") == TAHLILSIZ:
            continue              # faqat jonli ko'rish — tahlilga qo'shilmaydi
        c = {"channel": k["kanal"], "fps": 3}
        if k.get("line"):
            c["line"] = k["line"]
        if k.get("zone"):
            c["zone"] = k["zone"]
        cams[k.get("nom") or f"kamera{k['kanal']}"] = c
    kirish = next((k["nom"] for k in sozlama if k.get("vazifa") == "kirish"), None)
    kassa = next((k["nom"] for k in sozlama if k.get("vazifa") == "kassa"), None)
    yangi = {
        "nvr": {"ip": nvr["ip"], "user": nvr["user"], "pass": nvr["pass"]},
        "cameras": cams,
        "telegram": {"token": "", "chat_id": "", "rasm": True},
        "db": "analitika.db", "arxiv": "kassa_arxiv", "arxiv_kun": 14,
        "odam_indeks": True, "hodim_yuz": True,
        "railway_url": BULUT, "agent_secret": h.get("token", ""),
        "rules": qoidalar_yasa(sozlama, qoidalar, profil),
    }
    if kirish:
        yangi["kirish_kamera"] = kirish
    if kassa:
        yangi["kassa_kamera"] = kassa
    eski = None
    if os.path.exists(CONFIG):
        try:
            eski = yaml.safe_load(open(CONFIG, encoding="utf-8"))
        except Exception:
            pass
    if eski == yangi:
        return False
    with open(CONFIG, "w", encoding="utf-8") as f:
        yaml.safe_dump(yangi, f, allow_unicode=True, sort_keys=False)
    print("[qurilma] config.yaml yangilandi", flush=True)
    return True


# ---------------- tahlilni boshqarish ----------------
class Tahlil:
    def __init__(self):
        self.p = None

    def ishlayaptimi(self):
        return self.p is not None and self.p.poll() is None

    def boshla(self):
        if self.ishlayaptimi():
            return
        py = os.path.join(".venv", "Scripts", "python.exe")
        if not os.path.exists(py):
            py = sys.executable
        self.p = subprocess.Popen([py, "main.py"])
        print("[qurilma] tahlil ishga tushdi", flush=True)

    def toxtat(self):
        if self.ishlayaptimi():
            self.p.terminate()
            try:
                self.p.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.p.kill()
        self.p = None


# ---------------- kodni ko'rsatish ----------------
def bot_nomi(javob=None):
    """Qaysi botga yozish kerakligi: bulut aytgani > yonidagi bot.txt > bo'sh."""
    nom = ((javob or {}).get("bot") or _yonidagi("bot.txt") or "").strip()
    nom = nom.lstrip("@")
    return f"@{nom}" if re.fullmatch(r"[A-Za-z0-9_]{4,40}", nom) else ""


def kod_korsat(kod, bot=""):
    chiziq = "=" * 46
    bot_qator = (f"   Bot: {bot}\n" if bot else
                 "   (bot nomini o'rnatgan mutaxassis beradi)\n")
    matn = (f"\n{chiziq}\n"
            f"   ULASH KODI:   {kod}\n"
            f"{chiziq}\n"
            f"   Telegram botni oching va shu kodni yozing.\n"
            f"{bot_qator}"
            f"{chiziq}\n")
    print(matn, flush=True)
    try:
        with open(KOD_FAYL, "w", encoding="utf-8") as f:
            f.write(matn)
    except OSError:
        pass


# ---------------- asosiy sikl ----------------
def yagona_nusxa(port=47654):
    """Ikki nusxa bir vaqtda ishlamasin (avtostart + xizmat to'qnashmasin).
    Lokal portni band qilamiz — eng ishonchli usul, qotib qolgan qulf bo'lmaydi."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        s.listen(1)
        return s              # ochiq qoladi = qulf
    except OSError:
        print("[qurilma] boshqa nusxa allaqachon ishlayapti — chiqildi", flush=True)
        return None


def main():
    global BULUT, BOT
    qulf = yagona_nusxa()
    if qulf is None:
        return
    while not BULUT:
        print("[qurilma] bulut manzili yo'q: dastur yoniga bulut.txt qo'ying "
              "(ichida https://... manzil) yoki BULUT_URL ni bering. "
              "Kutilmoqda...", flush=True)
        time.sleep(30)
        BULUT = _bulut_manzil()
    did = device_id()
    print(f"[qurilma] ID: {did}\n[qurilma] bulut: {BULUT}", flush=True)
    h = holat_ol()
    token = h.get("token")
    tahlil = Tahlil()
    oxirgi_kod = None
    oxirgi_hb = 0.0

    while True:
        # 1) Ulanmagan bo'lsa — ro'yxatdan o'tib kodni ko'rsatamiz
        if not token:
            try:
                r = requests.post(f"{BULUT}/device/register", timeout=20,
                                  json={"device_id": did,
                                        "info": {"host": socket.gethostname(),
                                                 "ip": lokal_ip()}}).json()
            except (requests.RequestException, ValueError):
                time.sleep(5)
                continue
            if r.get("ulangan") and r.get("token"):
                token = r["token"]
                holat_yoz({"token": token})
                print("[qurilma] TAYYOR: do'konga ulandi!", flush=True)
                if os.path.exists(KOD_FAYL):
                    try:
                        os.remove(KOD_FAYL)
                    except OSError:
                        pass
            else:
                yangi_bot = bot_nomi(r)
                if r.get("kod") != oxirgi_kod or yangi_bot != BOT:
                    oxirgi_kod, BOT = r.get("kod"), yangi_bot
                    kod_korsat(oxirgi_kod, BOT)
                time.sleep(5)
                continue

        hdr = {"X-Device-Token": token}
        # 2) Sozlama va topshiriq
        try:
            r = requests.get(f"{BULUT}/device/poll", headers=hdr, timeout=30).json()
        except (requests.RequestException, ValueError):
            time.sleep(5)
            continue
        if r.get("sozlama") is not None:
            if config_yoz(r["sozlama"], r.get("qoidalar"), r.get("profil")) \
                    and tahlil.ishlayaptimi():
                tahlil.toxtat()          # sozlama o'zgardi -> qayta ishga tushadi
        job = r.get("job")
        if job:
            fn = JOBLAR.get(job["turi"])
            payload = dict(job["payload"] or {})
            payload["_job_id"] = job["id"]
            natija = fn(payload) if fn else {"ok": False,
                                             "xabar": "noma'lum topshiriq"}
            if natija is not None:      # None = natija allaqachon yuborilgan
                try:
                    requests.post(f"{BULUT}/device/job/{job['id']}", headers=hdr,
                                  json=natija, timeout=30)
                except requests.RequestException:
                    pass

        # 3) Tahlil ishlayaptimi (sozlama tayyor bo'lsa)
        if os.path.exists(CONFIG) and holat_ol().get("nvr"):
            tahlil.boshla()

        # 4) Heartbeat
        if time.time() - oxirgi_hb > 30:
            oxirgi_hb = time.time()
            try:
                res = requests.post(f"{BULUT}/device/heartbeat", headers=hdr,
                                    json={"tahlil": tahlil.ishlayaptimi(),
                                          "versiya": VERSIYA}, timeout=20).json()
                if res.get("faol") is False and tahlil.ishlayaptimi():
                    print("[qurilma] obuna faol emas - tahlil to'xtatildi", flush=True)
                    tahlil.toxtat()
            except (requests.RequestException, ValueError):
                pass
        time.sleep(3)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[qurilma] to'xtatildi")
