"""Odamlar indeksi — kim, qachon, qaysi kamerada ko'ringan.

Har bir odam (track) uchun bir nechta "namuna" saqlanadi: barmoq izi
(embedding) + kichik rasm + vaqt + kamera. Kadrlar emas — namunalar,
shuning uchun ombor kichik va qidiruv tez.

Qidiruv: rasm beriladi -> barmoq izi hisoblanadi -> indeksdan eng
o'xshashlari topiladi -> "bu odam falon vaqtda falon kamerada" ro'yxati.

Papka: <indeks>/thumbs/<YYYYMMDD>/<id>.jpg
"""
import datetime as dt
import os
import shutil
import sqlite3
import threading

import cv2
import numpy as np


class PersonIndex:
    def __init__(self, path="odamlar.db", thumbs="odamlar_thumbs"):
        self.thumbs = thumbs
        os.makedirs(thumbs, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS persons ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " ts INTEGER NOT NULL,"
            " camera TEXT NOT NULL,"
            " track INTEGER,"
            " emb BLOB NOT NULL,"
            " thumb TEXT,"
            " area INTEGER)")
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_persons_ts ON persons(ts)")
        # hodim ustuni (eski bazalarga ham qo'shiladi)
        cols = [r[1] for r in self._conn.execute("PRAGMA table_info(persons)")]
        if "hodim" not in cols:
            self._conn.execute("ALTER TABLE persons ADD COLUMN hodim TEXT")
        self._conn.commit()

    # ---------- yozish ----------
    def qosh(self, ts, camera, track, emb, crop, area, hodim=None):
        """Bitta namunani indeksga qo'shadi (barmoq izi + kichik rasm).
        hodim: yuz tanilgan bo'lsa hodim ismi, aks holda None."""
        when = dt.datetime.fromtimestamp(ts)
        d = os.path.join(self.thumbs, when.strftime("%Y%m%d"))
        os.makedirs(d, exist_ok=True)
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO persons (ts,camera,track,emb,thumb,area,hodim) "
                "VALUES (?,?,?,?,?,?,?)",
                (int(ts), camera, int(track) if track is not None else None,
                 emb.astype(np.float32).tobytes(), "", int(area), hodim))
            pid = cur.lastrowid
            self._conn.commit()
        thumb = os.path.join(d, f"{pid}.jpg")
        if crop is not None and crop.size:
            h = 160
            w = max(1, int(crop.shape[1] * h / crop.shape[0]))
            cv2.imwrite(thumb, cv2.resize(crop, (w, h)),
                        [cv2.IMWRITE_JPEG_QUALITY, 78])
            with self._lock:
                self._conn.execute("UPDATE persons SET thumb=? WHERE id=?",
                                   (thumb, pid))
                self._conn.commit()
        return pid

    # ---------- qidirish ----------
    def _yukla(self, start_ts, end_ts):
        with self._lock:
            rows = self._conn.execute(
                "SELECT id,ts,camera,track,emb,thumb FROM persons "
                "WHERE ts>=? AND ts<=? ORDER BY ts",
                (int(start_ts), int(end_ts))).fetchall()
        if not rows:
            return [], None
        M = np.stack([np.frombuffer(r[4], np.float32) for r in rows])
        return rows, M

    def qidir(self, emb, start_ts, end_ts, chegara=0.80, top=40, gap=120):
        """Barmoq izi bo'yicha qidiradi.

        chegara: o'xshashlik chegarasi (0.80 — ehtiyotkor, 0.72 — kengroq)
        gap: shu soniyadan yaqin natijalar bitta "uchrashuv" ga birlashadi.
        Qaytaradi: [{start,end,camera,score,thumb,soni}, ...] eng yaxshisi birinchi.
        """
        rows, M = self._yukla(start_ts, end_ts)
        if not rows:
            return []
        q = np.asarray(emb, np.float32)
        if M.shape[1] != q.shape[0]:
            return []
        scores = M @ q
        idx = [i for i in range(len(rows)) if scores[i] >= chegara]
        if not idx:
            return []
        idx.sort(key=lambda i: rows[i][1])          # vaqt bo'yicha
        guruh = []
        for i in idx:
            _id, ts, cam, _tr, _e, thumb = rows[i]
            s = float(scores[i])
            if guruh and guruh[-1]["camera"] == cam and ts - guruh[-1]["end"] <= gap:
                g = guruh[-1]
                g["end"] = ts
                g["soni"] += 1
                if s > g["score"]:
                    g["score"], g["thumb"] = s, thumb
            else:
                guruh.append({"start": ts, "end": ts, "camera": cam,
                              "score": s, "thumb": thumb, "soni": 1})
        guruh.sort(key=lambda g: -g["score"])
        return guruh[:top]

    def statistika(self, start_ts, end_ts):
        with self._lock:
            n = self._conn.execute(
                "SELECT COUNT(*) FROM persons WHERE ts>=? AND ts<=?",
                (int(start_ts), int(end_ts))).fetchone()[0]
            cams = self._conn.execute(
                "SELECT camera, COUNT(*) FROM persons WHERE ts>=? AND ts<=? "
                "GROUP BY camera ORDER BY 2 DESC",
                (int(start_ts), int(end_ts))).fetchall()
            hod = self._conn.execute(
                "SELECT hodim, COUNT(DISTINCT camera||'_'||track) FROM persons "
                "WHERE ts>=? AND ts<=? AND hodim IS NOT NULL GROUP BY hodim",
                (int(start_ts), int(end_ts))).fetchall()
            # yuzi tanilmagan (noma'lum) tashriflar
            noma = self._conn.execute(
                "SELECT COUNT(DISTINCT camera||'_'||track) FROM persons "
                "WHERE ts>=? AND ts<=? AND hodim IS NULL",
                (int(start_ts), int(end_ts))).fetchone()[0]
        return {"namunalar": n, "kameralar": dict(cams),
                "hodimlar": dict(hod), "nomalum": noma}

    def davomat(self, start_ts, end_ts):
        """Hodimlar davomati: kim qachon birinchi va oxirgi marta ko'rindi.

        Yuz tanilgan namunalar asosida. Qaytaradi:
        [{ism, keldi, ketdi, soat, kameralar, korinishlar}, ...]
        """
        with self._lock:
            rows = self._conn.execute(
                "SELECT hodim, MIN(ts), MAX(ts), COUNT(*), "
                "GROUP_CONCAT(DISTINCT camera) FROM persons "
                "WHERE ts>=? AND ts<=? AND hodim IS NOT NULL "
                "GROUP BY hodim ORDER BY 2",
                (int(start_ts), int(end_ts))).fetchall()
        out = []
        for ism, birinchi, oxirgi, soni, kams in rows:
            out.append({
                "ism": ism,
                "keldi": int(birinchi),
                "ketdi": int(oxirgi),
                "soat": round((oxirgi - birinchi) / 3600.0, 1),
                "korinishlar": soni,
                "kameralar": (kams or "").split(","),
            })
        return out

    def tozala(self, kun=14):
        """kun kundan eski namunalar va rasmlarni o'chiradi."""
        chegara = (dt.datetime.now() - dt.timedelta(days=kun)).timestamp()
        with self._lock:
            self._conn.execute("DELETE FROM persons WHERE ts<?", (int(chegara),))
            self._conn.commit()
        eski = (dt.date.today() - dt.timedelta(days=kun)).strftime("%Y%m%d")
        for d in os.listdir(self.thumbs) if os.path.isdir(self.thumbs) else []:
            if d.isdigit() and d < eski:
                shutil.rmtree(os.path.join(self.thumbs, d), ignore_errors=True)


class TrackBuffer:
    """Kuzatilayotgan odamlar uchun vaqtinchalik xotira.

    Har bir track uchun eng sifatli (eng katta) kesma tanlanadi va har
    `oraliq` soniyada indeksga bitta namuna yoziladi. Shu tufayli bir odam
    100 ta kadr emas, bir necha namuna bo'lib tushadi — CPU va joy tejaladi.
    """

    def __init__(self, index, camera, oraliq=8.0, eskir=6.0, hodimlar=None):
        self.index = index
        self.camera = camera
        self.oraliq = oraliq
        self.eskir = eskir
        self.hodimlar = hodimlar     # Employees (yuz bo'yicha tanish) yoki None
        self._t = {}     # track -> {emb, crop, area, yozildi, korildi, hodim}

    def yangila(self, track, emb, crop, area, now):
        st = self._t.get(track)
        if st is None:
            st = {"emb": emb, "crop": crop, "area": area,
                  "yozildi": 0.0, "korildi": now, "hodim": None}
            self._t[track] = st
        else:
            st["korildi"] = now
            if area > st["area"]:     # sifatliroq kesma
                st["emb"], st["crop"], st["area"] = emb, crop, area
        if now - st["yozildi"] >= self.oraliq:
            st["yozildi"] = now
            # Yuz bo'yicha hodimni aniqlash (bir marta tanilsa, shu track uchun eslab qolamiz)
            if self.hodimlar is not None and st["hodim"] is None and st["crop"] is not None:
                try:
                    ism, _ = self.hodimlar.tani(st["crop"])
                    if ism:
                        st["hodim"] = ism
                except Exception:
                    pass
            self.index.qosh(now, self.camera, track, st["emb"], st["crop"],
                            st["area"], st["hodim"])
            st["area"] = 0            # keyingi oraliq uchun qayta tanlanadi
            return True
        return False

    def tozala(self, now):
        """Ko'rinmay qolgan tracklarni xotiradan chiqaradi."""
        for k in [k for k, v in self._t.items() if now - v["korildi"] > self.eskir]:
            self._t.pop(k, None)
