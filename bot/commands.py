"""Telegram buyruqlar boti — long polling (alohida ip).

Buyruqlar:
  /holat        — hozirgi ahvol (har kamerada nechta odam, kassada navbat)
  /bugun        — bugungi jami (kirdi, pik soat, eng katta navbat)
  /hafta        — 7 kunlik jami
  /kassa 14:30  — kassa videosini o'sha vaqt atrofida ko'rsatadi (NVR diskidan)
  /kassa 14:30 14:35 — aniq oraliq
  /kamchiqdi    — so'nggi 2 daqiqa kassa videosi (pul kam chiqqanda)

Faqat config'dagi chat_id ga javob beradi (xavfsizlik).
"""
import datetime as dt
import os
import re
import time

import requests

from storage import evidence

API = "https://api.telegram.org/bot{token}/{method}"
MAX_SEK = 600  # so'rov oralig'i eng ko'pi 10 daqiqa


class CommandBot:
    def __init__(self, token, chat_id, db, live, kassa_name, arxiv="kassa_arxiv"):
        self.token = token
        self.chat_id = str(chat_id)
        self.db = db
        self.live = live
        self.kassa_name = kassa_name
        self.arxiv = arxiv
        os.makedirs(arxiv, exist_ok=True)

    # --- Telegram yordamchilari ---
    def _api(self, method, **kw):
        try:
            return requests.post(API.format(token=self.token, method=method),
                                 timeout=30, **kw).json()
        except requests.RequestException:
            return {}

    def _send(self, text):
        self._api("sendMessage", data={"chat_id": self.chat_id, "text": text})

    def _send_video(self, path, caption):
        with open(path, "rb") as f:
            self._api("sendVideo", data={"chat_id": self.chat_id, "caption": caption},
                      files={"video": f})

    # --- Ishga tushirish (ip ichida) ---
    def run(self, stop):
        if not (self.token and self.chat_id):
            return
        offset = None
        # eski buyruqlarni tashlab yuboramiz
        r = self._api("getUpdates", data={"timeout": 0})
        if r.get("ok") and r["result"]:
            offset = r["result"][-1]["update_id"] + 1
        self._send("Bot tayyor. Buyruqlar: /holat /bugun /hafta /kassa /kamchiqdi")
        while not stop.is_set():
            r = self._api("getUpdates", data={"timeout": 20, "offset": offset})
            if not r.get("ok"):
                time.sleep(2)
                continue
            for upd in r["result"]:
                offset = upd["update_id"] + 1
                msg = upd.get("message") or {}
                if str(msg.get("chat", {}).get("id")) != self.chat_id:
                    continue
                text = (msg.get("text") or "").strip()
                try:
                    self.handle(text)
                except Exception as e:
                    self._send(f"Xatolik: {e}")

    # --- Buyruqlarni qayta ishlash ---
    def handle(self, text):
        low = text.lower()
        if low.startswith("/holat"):
            self.cmd_holat()
        elif low.startswith("/bugun"):
            self.cmd_hisobot("Bugun", self._bugun_start(), time.time())
        elif low.startswith("/hafta"):
            self.cmd_hisobot("7 kun", time.time() - 7 * 86400, time.time())
        elif low.startswith("/kassa"):
            self.cmd_kassa(text)
        elif low.startswith("/kamchiqdi") or "kam chiqdi" in low:
            self.cmd_kamchiqdi()
        elif low.startswith("/start") or low.startswith("/help"):
            self._send("Buyruqlar:\n/holat — hozirgi ahvol\n/bugun — bugungi hisobot\n"
                       "/hafta — 7 kunlik\n/kassa 14:30 — kassa videosi\n"
                       "/kamchiqdi — so'nggi 2 daqiqa kassa videosi")

    def cmd_holat(self):
        if not self.live:
            self._send("Hali ma'lumot yig'ilmadi.")
            return
        lines = ["📊 Hozirgi ahvol:"]
        for name, s in self.live.items():
            jim = time.time() - s.get("ts", 0)
            if jim > 30:
                lines.append(f"• {name}: ⚠️ signal yo'q ({int(jim)}s)")
                continue
            part = f"• {name}: {s.get('kadrda', 0)} odam"
            if s.get("line"):
                part += f" | kirdi {s.get('kirdi', 0)}, chiqdi {s.get('chiqdi', 0)}"
            if s.get("zone"):
                part += f" | navbat {s.get('navbat', 0)}, kutish {int(s.get('kutish', 0))}s"
            lines.append(part)
        self._send("\n".join(lines))

    def cmd_hisobot(self, sarlavha, start_ts, end_ts):
        rep = self.db.hisobot(start_ts, end_ts)
        if not rep:
            self._send(f"{sarlavha}: ma'lumot yo'q.")
            return
        lines = [f"📈 {sarlavha} hisoboti:"]
        for cam, d in rep.items():
            piks = f"{d['pik_soat']:02d}:00" if d["pik_soat"] is not None else "-"
            lines.append(f"• {cam}: kirdi {d['kirdi']}, chiqdi {d['chiqdi']}, "
                         f"eng katta navbat {d['navbat_max']}, "
                         f"eng uzoq kutish {int(d['kutish_max'])}s, pik {piks}")
        self._send("\n".join(lines))

    def cmd_kassa(self, text):
        times = re.findall(r"(\d{1,2}):(\d{2})", text)
        if not times:
            self._send("Vaqtni yozing, masalan: /kassa 14:30  yoki  /kassa 14:30 14:35")
            return
        today = dt.date.today()
        t1 = dt.datetime.combine(today, dt.time(int(times[0][0]), int(times[0][1])))
        if len(times) >= 2:
            t2 = dt.datetime.combine(today, dt.time(int(times[1][0]), int(times[1][1])))
        else:
            t1 = t1 - dt.timedelta(minutes=1)
            t2 = t1 + dt.timedelta(seconds=MAX_SEK)
        self._review(t1, t2, f"Kassa {times[0][0]}:{times[0][1]} atrofida")

    def cmd_kamchiqdi(self):
        end = dt.datetime.now()
        start = end - dt.timedelta(minutes=5)
        self._review(start, end, "So'nggi 5 daqiqa (pul kam chiqdi)")

    def _review(self, start, end, sarlavha):
        if (end - start).total_seconds() > MAX_SEK:
            end = start + dt.timedelta(seconds=MAX_SEK)
        # faoliyat xulosasi (bazadan)
        act = self.db.kassa_faoliyat(self.kassa_name, start.timestamp(), end.timestamp())
        if act:
            odam = max(a[1] for a in act)
            xul = f"Bu oraliqda kassada eng ko'p {odam} kishi bo'lgan ({len(act)} daqiqa faol)."
        else:
            xul = "Bu oraliqda kassa zonasida odam qayd etilmagan."
        self._send(f"🎥 {sarlavha}\n{xul}\nVideo tayyorlanmoqda, biroz kuting...")
        out = os.path.join(self.arxiv,
                           f"kassa_{start.strftime('%Y%m%d_%H%M')}.mp4")
        n, path = evidence.klip_yasa(self.arxiv, self.kassa_name, start, end, out)
        if path:
            cap = (f"Kassa: {start.strftime('%H:%M')}–{end.strftime('%H:%M')}  "
                   f"({n} kadr)\n{xul}")
            self._send_video(path, cap)
        else:
            self._send("Bu vaqt uchun arxivda kadr yo'q (tizim o'sha paytda "
                       "ishlamagan yoki kassada harakat bo'lmagan). Boshqa vaqtni sinang.")
