"""Kunlik avtomatik hisobot — matn + soatlik oqim grafigi, Telegram'ga."""
import datetime as dt
import time

import matplotlib
import requests

matplotlib.use("Agg")
import matplotlib.pyplot as plt

API = "https://api.telegram.org/bot{token}/{method}"


def _kun_chegara(day):
    start = dt.datetime.combine(day, dt.time(0, 0))
    return start.timestamp(), (start + dt.timedelta(days=1)).timestamp()


def grafik_yasa(db, camera, start_ts, end_ts, path):
    soatlik = db.soatlik(camera, start_ts, end_ts)
    soats = list(range(7, 23))  # ish soatlari 07-22
    qiy = [soatlik.get(h, 0) for h in soats]
    fig, ax = plt.subplots(figsize=(8, 3.2))
    ax.bar([f"{h}" for h in soats], qiy, color="#4C78A8")
    ax.set_title("Soatlik kirganlar")
    ax.set_xlabel("soat")
    ax.set_ylabel("odam")
    fig.tight_layout()
    fig.savefig(path, dpi=90)
    plt.close(fig)
    return path


def matn_yasa(db, sana, start_ts, end_ts):
    rep = db.hisobot(start_ts, end_ts)
    lines = [f"📅 Kunlik hisobot — {sana:%d.%m.%Y}"]
    if not rep:
        lines.append("Bugun ma'lumot yig'ilmadi.")
    for cam, d in rep.items():
        piks = f"{d['pik_soat']:02d}:00" if d["pik_soat"] is not None else "-"
        lines.append(f"\n• {cam}:")
        lines.append(f"   kirdi: {d['kirdi']}, chiqdi: {d['chiqdi']}")
        lines.append(f"   eng katta navbat: {d['navbat_max']}, "
                     f"eng uzoq kutish: {int(d['kutish_max'])}s")
        lines.append(f"   eng gavjum soat: {piks}")
    return "\n".join(lines)


def yubor(db, token, chat_id, kirish_kamera, day=None):
    if not (token and chat_id):
        print("[hisobot] token yo'q - hisobot yuborilmadi", flush=True)
        return
    day = day or dt.date.today()
    start_ts, end_ts = _kun_chegara(day)
    matn = matn_yasa(db, day, start_ts, end_ts)
    png = grafik_yasa(db, kirish_kamera, start_ts, end_ts, "hisobot.png")
    try:
        with open(png, "rb") as f:
            requests.post(API.format(token=token, method="sendPhoto"),
                          data={"chat_id": chat_id, "caption": matn},
                          files={"photo": f}, timeout=30)
        print("[hisobot] kunlik hisobot yuborildi", flush=True)
    except (requests.RequestException, OSError) as e:
        print(f"[hisobot] yuborilmadi: {e}", flush=True)
