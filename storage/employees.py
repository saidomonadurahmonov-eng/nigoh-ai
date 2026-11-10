"""Hodimlar ro'yxati — yuz bo'yicha "o'ziniki / begona" ni ajratish uchun.

Hodim bir marta ro'yxatga olinadi (aniq rasm bilan, telefonda olingan bo'lsa
ham bo'ladi). Keyin tizim kameralarda yuzni ko'rsa — hodimmi yoki begonami
deb belgilaydi. Bitta hodimga bir nechta rasm qo'shsa aniqlik oshadi.

Eslatma: yuz kamerada aniq ko'rinishi kerak (~30x30 pikseldan katta).
Uzoqdagi odamda yuz ko'rinmaydi — u "noma'lum" bo'lib qoladi (begona emas).
"""
import datetime as dt
import os
import sqlite3
import threading

import cv2
import numpy as np

from vision import face


class Employees:
    def __init__(self, path="hodimlar.db", rasmlar="hodim_rasm"):
        self.rasmlar = rasmlar
        os.makedirs(rasmlar, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS hodimlar ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " ism TEXT NOT NULL,"
            " emb BLOB NOT NULL,"
            " rasm TEXT,"
            " qoshildi INTEGER NOT NULL)")
        self._conn.commit()
        self._kesh = None       # (ismlar, matritsa)

    def _kesh_tozala(self):
        self._kesh = None

    def _yukla(self):
        if self._kesh is not None:
            return self._kesh
        with self._lock:
            rows = self._conn.execute(
                "SELECT ism, emb FROM hodimlar").fetchall()
        if not rows:
            self._kesh = ([], None)
        else:
            ismlar = [r[0] for r in rows]
            M = np.stack([np.frombuffer(r[1], np.float32) for r in rows])
            self._kesh = (ismlar, M)
        return self._kesh

    def qosh(self, ism, img):
        """Hodim rasmidan yuz barmoq izini olib saqlaydi.
        Qaytaradi: (ok, xabar)."""
        if not face.mavjudmi():
            return False, "Yuz modeli yo'q (internet kerak edi)"
        emb = face.barmoq_izi(img)
        if emb is None:
            return False, "Rasmda yuz topilmadi. Yuz aniq va yaqin bo'lsin."
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO hodimlar (ism,emb,rasm,qoshildi) VALUES (?,?,?,?)",
                (ism.strip(), emb.tobytes(), "", int(dt.datetime.now().timestamp())))
            hid = cur.lastrowid
            self._conn.commit()
        yol = os.path.join(self.rasmlar, f"{hid}.jpg")
        h = 200
        w = max(1, int(img.shape[1] * h / img.shape[0]))
        cv2.imwrite(yol, cv2.resize(img, (w, h)), [cv2.IMWRITE_JPEG_QUALITY, 80])
        with self._lock:
            self._conn.execute("UPDATE hodimlar SET rasm=? WHERE id=?", (yol, hid))
            self._conn.commit()
        self._kesh_tozala()
        return True, f"{ism} qo'shildi"

    def ochir(self, hid):
        with self._lock:
            self._conn.execute("DELETE FROM hodimlar WHERE id=?", (int(hid),))
            self._conn.commit()
        self._kesh_tozala()

    def royxat(self):
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, ism, rasm, qoshildi FROM hodimlar ORDER BY ism").fetchall()
        return [{"id": r[0], "ism": r[1], "rasm": r[2], "qoshildi": r[3]}
                for r in rows]

    def tani(self, img, chegara=None):
        """Rasmdagi yuz kimga tegishli? -> (ism, o'xshashlik) yoki (None, 0).
        None = yuz topilmadi yoki hech kimga to'g'ri kelmadi."""
        ismlar, M = self._yukla()
        if M is None:
            return None, 0.0
        emb = face.barmoq_izi(img)
        if emb is None:
            return None, 0.0
        if M.shape[1] != emb.shape[0]:
            return None, 0.0
        s = M @ emb
        i = int(np.argmax(s))
        ball = float(s[i])
        if ball >= (chegara if chegara is not None else face.CHEGARA):
            return ismlar[i], ball
        return None, ball
