"""Do'kon agenti — Railway'ga faqat TASHQARIGA ulanadi (gibrid arxitektura).

 - holat + so'nggi hodisalarni Railway'ga yuboradi (heartbeat)
 - Railway'dagi video so'rovlarini so'rab oladi, arxivdan lokal kesib, yuklaydi

Kompyuter internetga OCHILMAYDI — xuddi Telegram boti kabi faqat chiqadi.
"""
import datetime as dt
import os
import threading
import time

import requests

from storage import evidence

KLIP = "agent_klip"


class Agent:
    def __init__(self, url, secret, db, live, kassa_name, arxiv, pindex=None,
                 nvr_arxiv=None, kanallar=None, hodimlar=None):
        self.url = url.rstrip("/")
        self.secret = secret
        self.db = db
        self.live = live
        self.kassa = kassa_name
        self.arxiv = arxiv
        self.pindex = pindex
        self.nvr_arxiv = nvr_arxiv        # nvr.arxiv.Arxiv — kun tahlili uchun
        self.kanallar = kanallar or {}
        self.hodimlar = hodimlar          # storage.employees.Employees (yuz ID)
        self.hdr = {"X-Agent-Secret": secret}
        os.makedirs(KLIP, exist_ok=True)
        self._last_hb = 0.0

    def _status(self):
        out = []
        for name, s in self.live.items():
            out.append({
                "kamera": name, "kadrda": s.get("kadrda", 0),
                "kirdi": s.get("kirdi", 0), "chiqdi": s.get("chiqdi", 0),
                "navbat": s.get("navbat", 0), "kutish": int(s.get("kutish", 0)),
                "line": s.get("line", False), "zone": s.get("zone", False),
            })
        return {"kameralar": out}

    def _events(self):
        rows = self.db._q(
            "SELECT ts,camera,rule,message FROM events ORDER BY ts DESC LIMIT 50")
        out = []
        for ts, cam, rule, msg in rows:
            d = dt.datetime.fromtimestamp(ts)
            out.append({"ts": int(ts), "kamera": cam, "qoida": rule,
                        "xabar": msg, "vaqt": d.strftime("%d.%m %H:%M:%S")})
        return {"hodisalar": out}

    def _sessions(self):
        if not self.kassa:            # kassa kamerasi yo'q (hamma kamera tahlilsiz)
            return []
        bugun = dt.datetime.combine(dt.date.today(), dt.time(0, 0)).timestamp()
        out = []
        for s in evidence.sessiyalar(self.arxiv, self.kassa, bugun):
            a = dt.datetime.fromtimestamp(s["start"])
            b = dt.datetime.fromtimestamp(s["end"])
            out.append({"start": int(s["start"]), "end": int(s["end"]),
                        "kadr": s["kadr"],
                        "vaqt": a.strftime("%H:%M:%S") + "–" + b.strftime("%H:%M:%S"),
                        "davomiylik": int(s["end"] - s["start"]) + 1})
        return out

    def _employees(self):
        if self.hodimlar is None:
            return []
        try:
            return [{"id": h["id"], "ism": h["ism"]} for h in self.hodimlar.royxat()]
        except Exception:
            return []

    def _index_stat(self):
        if self.pindex is None:
            return {}
        try:
            bugun = dt.datetime.combine(dt.date.today(), dt.time(0, 0)).timestamp()
            return self.pindex.statistika(bugun, time.time())
        except Exception:
            return {}

    def _hb_sikli(self, stop):
        """Har 10 soniyada heartbeat — mustaqil ip, hech qachon to'xtamaydi."""
        while not stop.is_set():
            try:
                self._heartbeat()
            except Exception as e:
                print(f"[agent] heartbeat ipida xato (davom etamiz): {e}", flush=True)
            stop.wait(10)

    def _heartbeat(self):
        """Railway'ga "tirikman" signali. HAR QANDAY xato ushlanadi — aks holda
        ip o'lib qoladi va Mini App'da PC "oflayn" ko'rinadi (tizim ishlab tursa ham)."""
        try:
            payload = {"status": self._status(), "events": self._events(),
                       "sessions": self._sessions(),
                       "employees": self._employees(),
                       "index_stat": self._index_stat(),
                       "kanallar": self.kanallar}
        except Exception as e:                       # baza band, fayl yo'q va h.k.
            print(f"[agent] holat yig'ishda xato: {e}", flush=True)
            payload = {"status": {"kameralar": []}, "events": {"hodisalar": []},
                       "sessions": [], "employees": [], "index_stat": {},
                       "kanallar": self.kanallar}
        try:
            requests.post(f"{self.url}/agent/heartbeat", headers=self.hdr,
                          json=payload, timeout=15)
            self._hb_xato = 0
        except requests.RequestException as e:
            self._hb_xato = getattr(self, "_hb_xato", 0) + 1
            if self._hb_xato in (1, 5, 30) or self._hb_xato % 60 == 0:
                print(f"[agent] Railway'ga ulanmadi ({self._hb_xato}-marta): {e}",
                      flush=True)

    def _do_employee_add(self, eid, ism):
        """Hodim qo'shish: rasmni olib, yuz barmoq izini saqlaydi."""
        import cv2
        import numpy as np
        xabar = None
        try:
            if self.hodimlar is None:
                raise RuntimeError("hodim bazasi o'chirilgan")
            r = requests.get(f"{self.url}/agent/search_photo/{eid}",
                             headers=self.hdr, timeout=60)
            img = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                raise RuntimeError("rasm o'qilmadi")
            ok, xabar = self.hodimlar.qosh(ism or "Hodim", img)
        except Exception as e:
            xabar = f"Xato: {e}"
        try:
            requests.post(f"{self.url}/agent/search_result/{eid}", headers=self.hdr,
                          json={"natija": [], "xabar": xabar}, timeout=30)
        except requests.RequestException:
            pass

    def _do_employee_del(self, rid, hid):
        try:
            if self.hodimlar is not None:
                self.hodimlar.ochir(int(hid))
        except Exception:
            pass
        try:
            requests.post(f"{self.url}/agent/deleted/{rid}", headers=self.hdr,
                          json={"kadr": 0}, timeout=15)
        except requests.RequestException:
            pass

    def _do_clip(self, rid, start, end, kanal=None):
        """Video klip: avval o'z kadr arxividan, bo'lmasa NVR yozuvidan."""
        s = dt.datetime.fromtimestamp(start)
        e = dt.datetime.fromtimestamp(end)
        out = os.path.join(KLIP, f"{rid}.mp4")
        n, path = 0, None
        kassa_kanal = self.kanallar.get(self.kassa) if self.kanallar else None
        # Qaysi kamera so'ralganini aniq bilamiz: kassa bo'lsa — o'z kadr arxivimiz
        # (tez), boshqa kamera bo'lsa — TO'G'RIDAN-TO'G'RI NVR yozuvidan.
        # Aks holda har doim kassa videosi chiqib qolardi.
        kassa_soralgan = (kanal is None or
                          (kassa_kanal is not None and int(kanal) == int(kassa_kanal)))
        if kassa_soralgan:
            n, path = evidence.klip_yasa(self.arxiv, self.kassa, s, e, out, fps=4)
        if not path and kanal and self.nvr_arxiv is not None:
            try:
                if e - s < dt.timedelta(seconds=15):      # NVR qisqa oynada kadr bermaydi
                    e = s + dt.timedelta(seconds=20)
                print(f"[agent] NVR yozuvidan olinmoqda: kanal {kanal}, "
                      f"{s:%H:%M:%S}–{e:%H:%M:%S}", flush=True)
                path = self.nvr_arxiv.klip(int(kanal), s, e, out)
                n = 1 if path else 0
            except Exception as ex:
                print(f"[agent] NVR klip xatosi: {ex}", flush=True)
        try:
            if path:
                with open(path, "rb") as f:
                    requests.post(f"{self.url}/agent/upload/{rid}", headers=self.hdr,
                                  files={"video": (f"{rid}.mp4", f, "video/mp4")},
                                  timeout=120)
            else:
                requests.post(f"{self.url}/agent/failed/{rid}", headers=self.hdr,
                              json={"xabar": "Bu vaqt uchun arxivda kadr yo'q."},
                              timeout=15)
        except requests.RequestException:
            pass
        finally:
            if os.path.exists(out):
                try:
                    os.remove(out)
                except OSError:
                    pass

    def _do_search(self, sid, start, end):
        """Rasm bo'yicha odam qidirish: rasmni olib, indeksdan topadi."""
        import base64

        import cv2
        import numpy as np

        from vision import reid
        natija, xabar = [], None
        try:
            if self.pindex is None:
                raise RuntimeError("odamlar indeksi o'chirilgan")
            r = requests.get(f"{self.url}/agent/search_photo/{sid}",
                             headers=self.hdr, timeout=60)
            img = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                raise RuntimeError("rasm o'qilmadi")
            # Rasmda odam bor bo'lsa — o'shani kesib olamiz (aniqroq bo'ladi)
            crop = img
            try:
                from ultralytics import YOLO
                if not hasattr(self, "_yolo"):
                    self._yolo = YOLO("yolo11n.pt")
                res = self._yolo(img, classes=[0], conf=0.3, verbose=False)[0]
                if len(res.boxes):
                    b = max(res.boxes.xyxy.tolist(),
                            key=lambda x: (x[2] - x[0]) * (x[3] - x[1]))
                    c = reid.kesma(img, b)
                    if c is not None:
                        crop = c
            except Exception:
                pass
            emb = reid.embed(crop)
            if emb is None:
                raise RuntimeError("rasmdan barmoq izi olinmadi (rasm kichik?)")
            topilgan = self.pindex.qidir(emb, start, end)
            for g in topilgan[:20]:
                b64 = None
                if g.get("thumb") and os.path.exists(g["thumb"]):
                    with open(g["thumb"], "rb") as f:
                        b64 = base64.b64encode(f.read()).decode()
                a = dt.datetime.fromtimestamp(g["start"])
                bb = dt.datetime.fromtimestamp(g["end"])
                natija.append({
                    "kamera": g["camera"], "score": round(g["score"], 3),
                    "start": int(g["start"]), "end": int(g["end"]),
                    "vaqt": a.strftime("%d.%m %H:%M:%S") +
                            ("–" + bb.strftime("%H:%M:%S") if g["end"] > g["start"] else ""),
                    "soni": g["soni"], "rasm": b64})
            if not natija:
                xabar = "Bu odam indeksda topilmadi (boshqa kun/rasmni sinang)."
        except Exception as e:
            xabar = f"Qidiruv xatosi: {e}"
        try:
            requests.post(f"{self.url}/agent/search_result/{sid}", headers=self.hdr,
                          json={"natija": natija, "xabar": xabar}, timeout=120)
        except requests.RequestException:
            pass

    def _do_kun(self, rid, sana_str, kanal, nomi):
        """Kun tahlili: NVR arxividagi bir sanani ko'rib chiqib xulosa qaytaradi."""
        import base64

        import cv2

        from analysis import kun as K
        xulosa, lahzalar, xabar = "", [], None
        try:
            if self.nvr_arxiv is None:
                raise RuntimeError("NVR arxivi sozlanmagan")
            from ultralytics import YOLO
            if not hasattr(self, "_yolo"):
                self._yolo = YOLO("yolo11n.pt")
            sana = dt.datetime.strptime(sana_str, "%Y-%m-%d").date()
            n = K.tahlil(self.nvr_arxiv, self._yolo, int(kanal), sana)
            xulosa = K.matn(n, nomi)
            for teg, blok in K.eng_muhim(n, 3):
                ok, buf = cv2.imencode(".jpg", blok["kadr"],
                                       [cv2.IMWRITE_JPEG_QUALITY, 78])
                lahzalar.append({
                    "teg": teg,
                    "start": int(blok["boshlandi"].timestamp()),
                    "end": int(blok["tugadi"].timestamp()),
                    "vaqt": f"{blok['boshlandi']:%H:%M}–{blok['tugadi']:%H:%M}",
                    "odam": blok["max_odam"],
                    "rasm": base64.b64encode(buf).decode() if ok else None,
                })
            if not lahzalar:
                xabar = "Bu kunda arxivda harakat topilmadi."
        except Exception as e:
            xabar = f"Kun tahlili xatosi: {e}"
        try:
            requests.post(f"{self.url}/agent/kun_result/{rid}", headers=self.hdr,
                          json={"xulosa": xulosa, "lahzalar": lahzalar, "xabar": xabar},
                          timeout=120)
        except requests.RequestException:
            pass


    def _do_hisobot(self, rid, start, end):
        """Kunlik hisobot: sonlar, hodisalar xulosasi, hodimlar davomati."""
        natija = {}
        try:
            rep = self.db.hisobot(start, end)
            kunlik = []
            for cam, d in rep.items():
                kunlik.append({"kamera": cam, "kirdi": d["kirdi"],
                               "chiqdi": d["chiqdi"],
                               "navbat_max": d["navbat_max"],
                               "kutish_max": int(d["kutish_max"]),
                               "pik_soat": d["pik_soat"]})
            rows = self.db._q(
                "SELECT rule, COUNT(*) FROM events WHERE ts>=? AND ts<=? "
                "GROUP BY rule ORDER BY 2 DESC", (int(start), int(end)))
            hodisalar = [{"qoida": r, "soni": n} for r, n in rows]
            davomat = self.pindex.davomat(start, end) if self.pindex else []
            for d in davomat:
                d["keldi_vaqt"] = dt.datetime.fromtimestamp(d["keldi"]).strftime("%H:%M")
                d["ketdi_vaqt"] = dt.datetime.fromtimestamp(d["ketdi"]).strftime("%H:%M")
            stat = self.pindex.statistika(start, end) if self.pindex else {}
            natija = {"ok": True, "kunlik": kunlik, "hodisalar": hodisalar,
                      "davomat": davomat, "stat": stat}
        except Exception as e:
            natija = {"ok": False, "xabar": str(e)}
        try:
            requests.post(f"{self.url}/agent/hisobot_result/{rid}", headers=self.hdr,
                          json=natija, timeout=60)
        except requests.RequestException:
            pass

    def _do_delete(self, rid, start, end):
        n = evidence.ochir_oralik(self.arxiv, self.kassa, start, end)
        try:
            requests.post(f"{self.url}/agent/deleted/{rid}", headers=self.hdr,
                          json={"kadr": n}, timeout=15)
        except requests.RequestException:
            pass

    def run(self, stop):
        """Agent sikli. TO'LIQ himoyalangan: ichkaridagi har qanday xato ushlanadi,
        chunki bu ip o'lsa PC Mini App'da butunlay "oflayn" ko'rinadi."""
        if not (self.url and self.secret):
            return
        print(f"Agent Railway'ga ulandi: {self.url}", flush=True)
        # Heartbeat ALOHIDA ipda: uzoq ish (kun tahlili 5–15 daq) siklni bloklaganda
        # ham "tirikman" signali uzilmasin — aks holda PC oflayn ko'rinadi.
        threading.Thread(target=self._hb_sikli, args=(stop,), daemon=True).start()
        while not stop.is_set():
            try:
                try:
                    r = requests.get(f"{self.url}/agent/next", headers=self.hdr,
                                     timeout=15)
                    job = r.json() if r.status_code == 200 else {}
                except (requests.RequestException, ValueError):
                    job = {}
                if job.get("id"):
                    jt = job.get("type")
                    if jt == "delete":
                        self._do_delete(job["id"], job["start"], job["end"])
                    elif jt == "search":
                        self._do_search(job["id"], job["start"], job["end"])
                    elif jt == "employee_add":
                        self._do_employee_add(job["id"], job.get("ism"))
                    elif jt == "employee_del":
                        self._do_employee_del(job["id"], job["start"])
                    elif jt == "hisobot":
                        self._do_hisobot(job["id"], job["start"], job["end"])
                    elif jt == "kun":
                        self._do_kun(job["id"], job.get("sana"), job.get("kanal"),
                                     job.get("nomi", ""))
                    else:
                        self._do_clip(job["id"], job["start"], job["end"],
                                      job.get("kanal"))
                else:
                    time.sleep(2)
            except Exception as e:                   # ip HECH QACHON o'lmasin
                print(f"[agent] kutilmagan xato (davom etamiz): {e}", flush=True)
                time.sleep(5)
