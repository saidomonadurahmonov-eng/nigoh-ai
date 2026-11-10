"""Yuz bo'yicha hodimlarni tanish (OpenCV YuNet + SFace, CPU'da tez).

Maqsad: hodimlarni bir marta ro'yxatga olish -> tizim "o'ziniki" va
"begona"ni ajratadi. Shunda begonalarni sanash va kassada notanish odam
bo'lsa ogohlantirish mumkin.

Modellar birinchi ishlatishda avtomatik yuklanadi (OpenCV Zoo):
  yunet  ~350 KB  — yuzni topadi
  sface  ~37 MB   — yuz barmoq izini hisoblaydi
Internet bo'lmasa yuz qismi o'chadi, qolgan tizim baribir ishlayveradi.
"""
import os
import threading

import cv2
import numpy as np

MODELS = "models"
YUNET = "face_detection_yunet_2023mar.onnx"
SFACE = "face_recognition_sface_2021dec.onnx"
BASE = "https://github.com/opencv/opencv_zoo/raw/main/models"
URLS = {
    YUNET: f"{BASE}/face_detection_yunet/{YUNET}",
    SFACE: f"{BASE}/face_recognition_sface/{SFACE}",
}
# SFace uchun standart chegara (kosinus): 0.363 — rasmiy tavsiya
CHEGARA = 0.36

_det = None
_rec = None
_lock = threading.Lock()
_ok = True


def _yukla_fayl(nom):
    yol = os.path.join(MODELS, nom)
    if os.path.exists(yol) and os.path.getsize(yol) > 10000:
        return yol
    os.makedirs(MODELS, exist_ok=True)
    import requests
    print(f"[yuz] {nom} yuklanmoqda...", flush=True)
    r = requests.get(URLS[nom], timeout=180, stream=True)
    r.raise_for_status()
    with open(yol, "wb") as f:
        for chunk in r.iter_content(65536):
            f.write(chunk)
    print(f"[yuz] {nom} tayyor ({os.path.getsize(yol)//1024} KB)", flush=True)
    return yol


def _init():
    """Modellarni bir marta yuklaydi. Muvaffaqiyatsiz bo'lsa (det, rec)=(None,None)."""
    global _det, _rec, _ok
    with _lock:
        if _det is not None or not _ok:
            return _det, _rec
        try:
            d = _yukla_fayl(YUNET)
            s = _yukla_fayl(SFACE)
            _det = cv2.FaceDetectorYN.create(d, "", (320, 320), 0.75, 0.3, 5000)
            _rec = cv2.FaceRecognizerSF.create(s, "")
        except Exception as e:
            print(f"[yuz] modellar yuklanmadi ({e}) — yuz tanish o'chirilgan",
                  flush=True)
            _ok = False
        return _det, _rec


def mavjudmi():
    return _init()[0] is not None


def yuzlar(img):
    """Rasmdagi yuzlarni topadi -> [(box(4), sifat, xom_qator), ...]"""
    det, _ = _init()
    if det is None or img is None or img.size == 0:
        return []
    h, w = img.shape[:2]
    if h < 40 or w < 40:
        return []
    det.setInputSize((w, h))
    _, faces = det.detect(img)
    if faces is None:
        return []
    out = []
    for f in faces:
        out.append((f[:4].astype(int), float(f[-1]), f))
    return out


def barmoq_izi(img, xom_qator=None):
    """Yuz barmoq izi (128 o'lcham). xom_qator berilmasa — eng katta yuz olinadi."""
    det, rec = _init()
    if rec is None or img is None or img.size == 0:
        return None
    if xom_qator is None:
        fs = yuzlar(img)
        if not fs:
            return None
        # eng katta yuz
        xom_qator = max(fs, key=lambda x: x[0][2] * x[0][3])[2]
    try:
        aligned = rec.alignCrop(img, xom_qator)
        feat = rec.feature(aligned)
        v = np.asarray(feat, np.float32).flatten()
        n = np.linalg.norm(v)
        return (v / n).astype(np.float32) if n > 0 else None
    except cv2.error:
        return None


def oxshashlik(a, b):
    """Ikki yuz barmoq izi o'xshashligi (kosinus, 0..1)."""
    if a is None or b is None or a.shape != b.shape:
        return 0.0
    return float(np.clip(np.dot(a, b), 0.0, 1.0))
