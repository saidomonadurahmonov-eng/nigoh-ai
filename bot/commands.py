"""Telegram buyruqlar boti — long polling (alohida ip).

Buyruqlar:
  /holat        — hozirgi ahvol (har kamerada nechta odam, kassada navbat)
  /bugun        — bugungi jami (kirdi, pik soat, eng katta navbat)
  /hafta        — 7 kunlik jami
  /kassa 14:30  — kassa videosini o'sha vaqt atrofida ko'rsatadi (NVR diskidan)
  /kassa 14:30 14:35 — aniq oraliq
  /kamchiqdi    — so'nggi 2 daqiqa kassa videosi (pul kam chiqqanda)
  /kun 2026-07-31 — o'sha kunning NVR arxivini AVTOMATIK ko'rib chiqib,
                    nima bo'lganini aytadi (kadr + rasm bilan)

Faqat config'dagi chat_id ga javob beradi (xavfsizlik).
"""
import datetime as dt
import os
import re
import threading
import time

import cv2
import requests

from storage import evidence

API = "https://api.telegram.org/bot{token}/{method}"
MAX_SEK = 600  # so'rov oralig'i eng ko'pi 10 daqiqa


class CommandBot:
    def __init__(self, token, chat_id, db, live, kassa_name, arxiv="kassa_arxiv",
                 nvr_arxiv=None, kanallar=None, model_yol="yolo11n.pt"):
        self.token = token
        self.chat_id = str(chat_id)
        self.db = db
        self.live = live
        self.kassa_name = kassa_name
        self.arxiv = arxiv
        self.nvr_arxiv = nvr_arxiv        # nvr.arxiv.Arxiv — kun tahlili uchun
        self.kanallar = kanallar or {}    # {"kirish": 1, "kassa": 6, ...}
        self.model_yol = model_yol
        self._kun_band = False
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

    def _send_html(self, text):
        return self._api("sendMessage", data={"chat_id": self.chat_id, "text": text,
                                              "parse_mode": "HTML"})

    def _send_photo(self, path, caption):
        with open(path, "rb") as f:
            return self._api("sendPhoto",
                             data={"chat_id": self.chat_id, "caption": caption},
                             files={"photo": f})

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
        elif low.startswith("/kun"):
            self.cmd_kun(text)
        elif low.startswith("/start") or low.startswith("/help"):
            self._send("Buyruqlar:\n/holat — hozirgi ahvol\n/bugun — bugungi hisobot\n"
                       "/hafta — 7 kunlik\n/kassa 14:30 — kassa videosi\n"
                       "/kamchiqdi — so'nggi 2 daqiqa kassa videosi\n"
                       "/kun 2026-07-31 — o'sha kun arxivini AI ko'rib chiqadi")

    # --- Kun tahlili (NVR arxivi) ---
    def cmd_kun(self, text):
        if not self.nvr_arxiv:
            self._send("Kun tahlili yoqilmagan (config'da nvr bloki kerak).")
            return
        if self._kun_band:
            self._send("Avvalgi kun tahlili hali tugamadi, biroz kuting.")
            return
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
        if m:
            sana = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        elif "kecha" in text.lower():
            sana = dt.date.today() - dt.timedelta(days=1)
        else:
            sana = dt.date.today()
        # kanal: nom bo'yicha (masalan "/kun 2026-07-31 kassa") yoki birinchi kamera
        kanal, nomi = None, ""
        for nom, ch in self.kanallar.items():
            if nom.lower() in text.lower():
                kanal, nomi = ch, nom
                break
        if kanal is None and self.kanallar:
            nomi, kanal = next(iter(self.kanallar.items()))
        if kanal is None:
            self._send("Kamera topilmadi (config'da cameras bo'sh).")
            return
        threading.Thread(target=self._kun_ishla, args=(sana, kanal, nomi),
                         daemon=True).start()

    def _kun_ishla(self, sana, kanal, nomi):
        self._kun_band = True
        try:
            from ultralytics import YOLO
            from analysis import kun as K
            self._send(f"🔎 {sana:%d.%m.%Y} — «{nomi}» arxivi tekshirilmoqda.\n"
                       f"Bu 5–15 daqiqa oladi, tayyor bo'lganda yuboraman.")
            model = YOLO(self.model_yol)
            n = K.tahlil(self.nvr_arxiv, model, kanal, sana)
            self._send_html(K.matn(n, nomi))
            out = os.path.join(self.arxiv, "kun")
            os.makedirs(out, exist_ok=True)
            for i, (teg, blok) in enumerate(K.eng_muhim(n, 3), 1):
                p = os.path.join(out, f"{sana:%Y%m%d}_{kanal}_{i}.jpg")
                cv2.imwrite(p, blok["kadr"])
                self._send_photo(p, f"{teg}: {blok['boshlandi']:%H:%M}–"
                                    f"{blok['tugadi']:%H:%M}, {blok['max_odam']} odam")
        except Exception as e:
            self._send(f"Kun tahlilida xatolik: {e}")
        finally:
            self._kun_band = False

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
