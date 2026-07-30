"""Kassa dalil arxivi — kadrlarni JPEG qilib saqlaydi va so'rovga ko'ra
ulardan video yasaydi. NVR playback ishonchsiz bo'lgani uchun (sekin,
H.265), biz ISAPI JPEG (100% ishlaydi) kadrlarini o'zimiz yozib boramiz.

Papka tuzilishi: arxiv/<kamera>/<YYYYMMDD>/<HHMMSS_fff>.jpg
"""
import datetime as dt
import glob
import os
import shutil
import subprocess

import cv2
import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def _kun_papka(arxiv, camera, when):
    d = os.path.join(arxiv, camera, when.strftime("%Y%m%d"))
    os.makedirs(d, exist_ok=True)
    return d


def saqla(arxiv, camera, frame, ts):
    """Bitta kadrni JPEG qilib arxivga yozadi (vaqt tamg'asi bilan)."""
    when = dt.datetime.fromtimestamp(ts)
    path = os.path.join(_kun_papka(arxiv, camera, when),
                        when.strftime("%H%M%S_") + f"{when.microsecond//1000:03d}.jpg")
    cv2.imwrite(path, frame, [cv2.IMWRITE_JPEG_QUALITY, 80])


def _kadrlar(arxiv, camera, start, end):
    """[start,end] mahalliy vaqt oralig'idagi kadr fayllarини tartibda qaytaradi."""
    res = []
    day = start.date()
    while day <= end.date():
        d = os.path.join(arxiv, camera, day.strftime("%Y%m%d"))
        for f in sorted(glob.glob(os.path.join(d, "*.jpg"))):
            hhmmss = os.path.basename(f)[:6]
            try:
                t = dt.datetime.combine(day, dt.datetime.strptime(hhmmss, "%H%M%S").time())
            except ValueError:
                continue
            if start <= t <= end:
                res.append(f)
        day += dt.timedelta(days=1)
    return res


def klip_yasa(arxiv, camera, start, end, out_path, fps=4):
    """Oraliqdagi JPEG kadrlardan H.264 mp4 video yasaydi (ffmpeg orqali).
    H.264 + yuv420p + faststart — Telegram/telefon brauzeri o'ynaydi.
    OpenCV'ning mp4v kodegini telefon o'ynatmaydi, shuning uchun ffmpeg.
    Kadr soni va yo'lni qaytaradi."""
    files = _kadrlar(arxiv, camera, start, end)
    if not files:
        return 0, None
    cmd = [FFMPEG, "-y", "-loglevel", "error", "-f", "image2pipe",
           "-framerate", str(fps), "-i", "-",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
           "-movflags", "+faststart", out_path]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    n = 0
    try:
        for f in files:
            with open(f, "rb") as fh:
                p.stdin.write(fh.read())
            n += 1
        p.stdin.close()
        p.wait(timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        try:
            p.kill()
        except OSError:
            pass
    if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
        return n, out_path
    return 0, None


def _barcha_kadrlar(arxiv, camera, since_ts):
    """since_ts (epoch) dan beri barcha kadr fayllari: [(ts, path), ...] tartibda."""
    res = []
    start_day = dt.datetime.fromtimestamp(since_ts).date()
    today = dt.date.today()
    day = start_day
    while day <= today:
        d = os.path.join(arxiv, camera, day.strftime("%Y%m%d"))
        for f in sorted(glob.glob(os.path.join(d, "*.jpg"))):
            hhmmss = os.path.basename(f)[:6]
            try:
                t = dt.datetime.combine(
                    day, dt.datetime.strptime(hhmmss, "%H%M%S").time()).timestamp()
            except ValueError:
                continue
            if t >= since_ts:
                res.append((t, f))
        day += dt.timedelta(days=1)
    return res


def sessiyalar(arxiv, camera, since_ts, gap=25):
    """Kassa faoliyatini alohida "tashriflar"ga bo'ladi. Ketma-ket kadrlar
    orasidagi tanaffus gap soniyadan katta bo'lsa — yangi sessiya.
    Qaytaradi: [{start, end, kadr}, ...] (eng yangisi birinchi)."""
    kadrlar = _barcha_kadrlar(arxiv, camera, since_ts)
    if not kadrlar:
        return []
    sess = []
    s0 = p0 = kadrlar[0][0]
    n = 1
    for t, _ in kadrlar[1:]:
        if t - p0 > gap:
            sess.append({"start": s0, "end": p0, "kadr": n})
            s0, n = t, 0
        p0 = t
        n += 1
    sess.append({"start": s0, "end": p0, "kadr": n})
    sess.reverse()
    return sess


def ochir_oralik(arxiv, camera, start_ts, end_ts):
    """[start,end] oralig'idagi kadr fayllarini arxivdan o'chiradi (ko'rib bo'lgach)."""
    n = 0
    for t, f in _barcha_kadrlar(arxiv, camera, start_ts - 1):
        if start_ts <= t <= end_ts:
            try:
                os.remove(f)
                n += 1
            except OSError:
                pass
    return n


def tozala(arxiv, kun=14):
    """kun kundan eski arxiv papkalarini o'chiradi."""
    chegara = (dt.date.today() - dt.timedelta(days=kun)).strftime("%Y%m%d")
    for cam in glob.glob(os.path.join(arxiv, "*")):
        for daydir in glob.glob(os.path.join(cam, "*")):
            nom = os.path.basename(daydir)
            if nom.isdigit() and nom < chegara:
                shutil.rmtree(daydir, ignore_errors=True)
