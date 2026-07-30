"""Do'kon agenti — Railway'ga faqat TASHQARIGA ulanadi (gibrid arxitektura).

 - holat + so'nggi hodisalarni Railway'ga yuboradi (heartbeat)
 - Railway'dagi video so'rovlarini so'rab oladi, arxivdan lokal kesib, yuklaydi

Kompyuter internetga OCHILMAYDI — xuddi Telegram boti kabi faqat chiqadi.
"""
import datetime as dt
import os
import time

import requests

from storage import evidence

KLIP = "agent_klip"


class Agent:
    def __init__(self, url, secret, db, live, kassa_name, arxiv):
        self.url = url.rstrip("/")
        self.secret = secret
        self.db = db
        self.live = live
        self.kassa = kassa_name
        self.arxiv = arxiv
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

    def _heartbeat(self):
        try:
            requests.post(f"{self.url}/agent/heartbeat", headers=self.hdr,
                          json={"status": self._status(), "events": self._events(),
                                "sessions": self._sessions()},
                          timeout=15)
        except requests.RequestException:
            pass

    def _do_clip(self, rid, start, end):
        s = dt.datetime.fromtimestamp(start)
        e = dt.datetime.fromtimestamp(end)
        out = os.path.join(KLIP, f"{rid}.mp4")
        n, path = evidence.klip_yasa(self.arxiv, self.kassa, s, e, out, fps=4)
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

    def _do_delete(self, rid, start, end):
        n = evidence.ochir_oralik(self.arxiv, self.kassa, start, end)
        try:
            requests.post(f"{self.url}/agent/deleted/{rid}", headers=self.hdr,
                          json={"kadr": n}, timeout=15)
        except requests.RequestException:
            pass

    def run(self, stop):
        if not (self.url and self.secret):
            return
        print(f"Agent Railway'ga ulandi: {self.url}", flush=True)
        while not stop.is_set():
            now = time.time()
            if now - self._last_hb >= 10:
                self._last_hb = now
                self._heartbeat()
            try:
                r = requests.get(f"{self.url}/agent/next", headers=self.hdr, timeout=15)
                job = r.json() if r.status_code == 200 else {}
            except (requests.RequestException, ValueError):
                job = {}
            if job.get("id"):
                if job.get("type") == "delete":
                    self._do_delete(job["id"], job["start"], job["end"])
                else:
                    self._do_clip(job["id"], job["start"], job["end"])
            else:
                time.sleep(2)
