"""NVR arxivi — o'tgan kunlarning yozuvidan kadr va klip olish.

MUHIM texnik faktlar (jonli NVR'da o'lchangan, DS-7616NI-Q2):
  * ISAPI /ContentMgmt/search YOLG'ON "NO MATCHES" qaytaradi — yozuvlar bor
    bo'lsa ham. Shuning uchun qidiruvga TAYANMAYMIZ, to'g'ridan-to'g'ri
    RTSP playback bilan vaqt bo'yicha olamiz.
  * RTSP: /Streaming/tracks/<ch>01?starttime=...&endtime=... — asosiy oqim,
    toza dekodlanadi (jonli oqimdagi yashil kadr muammosi bu yerda yo'q).
  * Vaqt tamg'asi NVR'ning LOKAL vaqti (formatda Z bo'lsa ham). PC va NVR
    bir mintaqada (+05:00) — shuning uchun oddiy lokal vaqt beriladi.
  * Oyna 10 soniyadan qisqa bo'lsa NVR kadr BERMAYDI (sinovda tasdiqlangan).
  * Ketma-ket oqitish ~0.8x tezlikda — bir kunni oqitib bo'lmaydi.
    Yechim: nuqtali "sakrash" (bitta kadr ~5.6s, 4 ip bilan ~1.5s).
"""
import datetime as dt
import os
import subprocess

import cv2
import imageio_ffmpeg
import numpy as np
from concurrent.futures import ThreadPoolExecutor

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
MIN_OYNA = 10          # soniya — bundan qisqasida NVR kadr bermaydi


class Arxiv:
    """NVR arxividan kadr/klip oluvchi. Bir nusxa barcha kanallarga xizmat qiladi."""

    def __init__(self, ip, user, parol, port=554):
        self.ip, self.user, self.parol, self.port = ip, user, parol, port

    def _url(self, channel, start, end):
        s = start.strftime("%Y%m%dT%H%M%SZ")
        e = end.strftime("%Y%m%dT%H%M%SZ")
        return (f"rtsp://{self.user}:{self.parol}@{self.ip}:{self.port}"
                f"/Streaming/tracks/{channel}01?starttime={s}&endtime={e}")

    def kadr(self, channel, when, scale=960, timeout=30):
        """Berilgan vaqtdagi bitta kadr (numpy BGR) yoki None."""
        url = self._url(channel, when, when + dt.timedelta(seconds=MIN_OYNA))
        cmd = [FFMPEG, "-nostdin", "-loglevel", "error", "-rtsp_transport", "tcp",
               "-i", url, "-frames:v", "1", "-vf", f"scale={scale}:-1",
               "-q:v", "5", "-f", "image2pipe", "-vcodec", "mjpeg", "-"]
        try:
            p = subprocess.run(cmd, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return None
        if len(p.stdout) < 1000 or p.stdout[:2] != b"\xff\xd8":
            return None
        return cv2.imdecode(np.frombuffer(p.stdout, np.uint8), cv2.IMREAD_COLOR)

    def kadrlar(self, channel, start, end, qadam, ishchi=4, scale=960, holat=None):
        """[start, end] oralig'ini qadam soniya bilan namuna oladi.

        Parallel (ishchi ip) — NVR bir vaqtda bir nechta playback sessiyasini
        ko'taradi. Qaytaradi: [(vaqt, kadr), ...] vaqt bo'yicha tartibda.
        holat(bajarildi, jami) — jarayonni ko'rsatish uchun chaqiriladi.
        """
        nuqtalar = []
        t = start
        while t < end:
            nuqtalar.append(t)
            t += dt.timedelta(seconds=qadam)
        natija, bajarildi = [], 0
        with ThreadPoolExecutor(max_workers=ishchi) as ex:
            for when, kadr in zip(nuqtalar, ex.map(
                    lambda w: self.kadr(channel, w, scale=scale), nuqtalar)):
                bajarildi += 1
                if kadr is not None:
                    natija.append((when, kadr))
                if holat and bajarildi % 10 == 0:
                    holat(bajarildi, len(nuqtalar))
        if holat:
            holat(len(nuqtalar), len(nuqtalar))
        return natija

    def bormi(self, channel, kun):
        """Shu kunda arxivda yozuv bormi? (tush payti bitta kadr bilan tekshiradi)"""
        for soat in (12, 9, 15, 18, 6):
            if self.kadr(channel, dt.datetime.combine(kun, dt.time(soat, 0))) is not None:
                return True
        return False

    def klip(self, channel, start, end, out_path, scale=960, timeout=300):
        """Arxivdan haqiqiy video kesib oladi (H.264, telefon o'ynaydigan)."""
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        url = self._url(channel, start, end + dt.timedelta(seconds=2))
        cmd = [FFMPEG, "-y", "-nostdin", "-loglevel", "error",
               "-rtsp_transport", "tcp", "-i", url,
               "-t", str(max(1, int((end - start).total_seconds()))),
               "-vf", f"scale={scale}:-1",
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
               "-movflags", "+faststart", "-an", out_path]
        try:
            subprocess.run(cmd, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return None
        if os.path.exists(out_path) and os.path.getsize(out_path) > 5000:
            return out_path
        return None
