import re
import time

import cv2
import numpy as np


def masked(source):
    """RTSP manzildagi parolni yashiradi — konsol va loglar uchun."""
    return re.sub(r"//[^@/]+@", "//***@", str(source))


class ISAPIFrameSource:
    """Hikvision NVR'dan ISAPI JPEG snapshot orqali kadr oladi.

    RTSP dekod (H.265/H.264) o'rniga ishlatiladi — NVR o'zi tayyor JPEG beradi,
    kodek muammosi yo'q. Analitika uchun 2-3 fps yetarli.

    ip/user/pw: NVR ma'lumotlari; channel: kamera raqami (1..N).
    substream (x02) — 640x360, yengil.
    """

    RECONNECT_DELAY = 2.0

    def __init__(self, ip, user, pw, channel, target_fps=3):
        self.ip = ip
        self.channel = channel
        self.target_fps = target_fps
        self.is_file = False
        self.url = (f"http://{ip}/ISAPI/Streaming/channels/"
                    f"{channel}02/picture")
        import requests
        from requests.auth import HTTPDigestAuth
        self._sess = requests.Session()
        self._sess.auth = HTTPDigestAuth(user, pw)
        self._exc = requests.RequestException

    def frames(self):
        interval = 1.0 / self.target_fps
        fails = 0
        while True:
            t0 = time.time()
            try:
                r = self._sess.get(self.url, timeout=8)
                if r.status_code == 200 and r.content:
                    frame = cv2.imdecode(
                        np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR)
                    if frame is not None:
                        fails = 0
                        yield frame, time.time()
                    else:
                        fails += 1
                else:
                    fails += 1
            except self._exc:
                fails += 1
            if fails:
                if fails % 10 == 1:
                    print(f"[isapi] kanal {self.channel} javob bermayapti, "
                          f"qayta urinilmoqda...", flush=True)
                time.sleep(self.RECONNECT_DELAY)
                continue
            dt = time.time() - t0
            if dt < interval:
                time.sleep(interval - dt)


class FrameSource:
    """Kameradan yoki fayldan kadrlarni belgilangan tezlikda beradi.

    source: RTSP manzil (str), video fayl yo'li (str) yoki qurilma raqami (int).
    Jonli oqim uzilsa avtomatik qayta ulanadi; fayl tugasa to'xtaydi.
    """

    RECONNECT_DELAY = 2.0
    MAX_GRAB_FAILS = 25

    def __init__(self, source, target_fps=3):
        if isinstance(source, str) and source.isdigit():
            source = int(source)
        self.source = source
        self.target_fps = target_fps
        self.is_file = isinstance(source, str) and not source.lower().startswith("rtsp")
        self.cap = None

    def _open(self):
        self.cap = cv2.VideoCapture(self.source)
        if not self.is_file:
            # buferni minimal tutamiz — eski kadrlar emas, hozirgisi kerak
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return self.cap.isOpened()

    def frames(self):
        if self.is_file:
            yield from self._file_frames()
        else:
            yield from self._live_frames()

    def _file_frames(self):
        if not self._open():
            raise RuntimeError(f"Fayl ochilmadi: {self.source}")
        src_fps = self.cap.get(cv2.CAP_PROP_FPS) or 30
        step = max(1, round(src_fps / self.target_fps))
        idx = 0
        while True:
            ok, frame = self.cap.read()
            if not ok:
                break
            if idx % step == 0:
                yield frame, idx / src_fps
            idx += 1
        self.cap.release()

    def _live_frames(self):
        interval = 1.0 / self.target_fps
        last = 0.0
        fails = 0
        open_fails = 0
        while True:
            if self.cap is None or not self.cap.isOpened():
                if not self._open():
                    open_fails += 1
                    if open_fails % 15 == 1:
                        print(f"[stream] {masked(self.source)} ochilmadi, "
                              f"qayta urinilmoqda...", flush=True)
                    time.sleep(self.RECONNECT_DELAY)
                    continue
                open_fails = 0
            # grab() oqimni doim ichib turadi — bufer ortda qolmaydi,
            # retrieve() esa faqat kerakli paytda dekodlaydi
            if not self.cap.grab():
                fails += 1
                if fails >= self.MAX_GRAB_FAILS:
                    self.cap.release()
                    self.cap = None
                    fails = 0
                    time.sleep(self.RECONNECT_DELAY)
                continue
            fails = 0
            now = time.time()
            if now - last < interval:
                continue
            ok, frame = self.cap.retrieve()
            if ok:
                last = now
                yield frame, now
