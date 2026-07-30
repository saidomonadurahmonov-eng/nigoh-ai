"""Sinov videosi: ultralytics bilan keladigan bus.jpg (4 odam bor) rasmini
kadr bo'ylab chapdan o'ngga va qaytib yurgizadi — odamlar virtual chiziqni
kesib o'tishini simulyatsiya qiladi. Kamera shart emas.
"""
import cv2
import numpy as np
from ultralytics.utils import ASSETS

W, H = 960, 540
FRAMES_PER_PASS = 240
OUT = "sinov_video.mp4"

img = cv2.imread(str(ASSETS / "bus.jpg"))
scale = H / img.shape[0]
img = cv2.resize(img, (int(img.shape[1] * scale), H))
iw = img.shape[1]

writer = cv2.VideoWriter(OUT, cv2.VideoWriter_fourcc(*"mp4v"), 30, (W, H))
if not writer.isOpened():
    OUT = "sinov_video.avi"
    writer = cv2.VideoWriter(OUT, cv2.VideoWriter_fourcc(*"XVID"), 30, (W, H))


def put(canvas, x):
    x = int(x)
    x0, x1 = max(0, x), min(W, x + iw)
    if x1 <= x0:
        return
    sx0 = x0 - x
    canvas[:, x0:x1] = img[:, sx0:sx0 + (x1 - x0)]


path = list(np.linspace(-iw, W, FRAMES_PER_PASS)) \
     + list(np.linspace(W, -iw, FRAMES_PER_PASS))
for x in path:
    canvas = np.full((H, W, 3), 235, np.uint8)
    put(canvas, x)
    writer.write(canvas)
writer.release()
print(f"{OUT} tayyor: {len(path)} kadr, {W}x{H}")
