"""Odamning "tashqi ko'rinish barmoq izi" (appearance embedding).

Maqsad: bir kun ichida bir odamni turli kameralarda tanib olish — kiyim,
rang, gavda ko'rinishi bo'yicha. Yuz kerak emas (kassa kamerasida yuz
har doim ham ko'rinmaydi).

Ikki qismdan iborat, ikkalasi ham CPU'da tez:
  1) RANG: gavdaning 3 qismi (yuqori/o'rta/past) bo'yicha HSV histogramma —
     kiyim rangi eng kuchli belgi (bir kun ichida kiyim o'zgarmaydi).
  2) CHUQUR: mobilenet_v3_small (ImageNet) xususiyatlari — shakl/tekstura,
     yorug'lik o'zgarsa ham barqarorroq.

Ikkalasi alohida normallanadi, keyin birlashtiriladi. Taqqoslash: kosinus.
Model yuklanmasa (internet yo'q) — faqat rang qismi ishlaydi (baribir ishlaydi).
"""
import os
import threading

import cv2
import numpy as np

# O'rnatuvchi paketi model og'irliklarini dastur yoniga qo'ygan bo'lsa
# (models/torch/hub/checkpoints), internetdan qayta yuklamay o'shani olamiz.
_YEREL_TORCH = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "models", "torch")
if os.path.isdir(os.path.join(_YEREL_TORCH, "hub", "checkpoints")):
    os.environ.setdefault("TORCH_HOME", _YEREL_TORCH)

W, H = 128, 256          # standart ReID o'lchami (odam tik turadi)
COLOR_W = 0.55           # rang og'irligi (kiyim - eng kuchli belgi)
DEEP_W = 0.45            # chuqur xususiyatlar og'irligi

_model = None
_lock = threading.Lock()
_deep_ok = True


def _load_model():
    """mobilenet_v3_small ni bir marta yuklaydi (kerak bo'lganda)."""
    global _model, _deep_ok
    with _lock:
        if _model is not None or not _deep_ok:
            return _model
        try:
            import torch
            from torchvision.models import (MobileNet_V3_Small_Weights,
                                            mobilenet_v3_small)
            m = mobilenet_v3_small(weights=MobileNet_V3_Small_Weights.DEFAULT)
            m.classifier = torch.nn.Identity()   # faqat xususiyat vektori
            m.eval()
            torch.set_num_threads(2)             # CPU'ni bo'g'ib qo'ymaslik
            _model = m
        except Exception as e:
            print(f"[reid] chuqur model yuklanmadi ({e}) - faqat rang ishlatiladi",
                  flush=True)
            _deep_ok = False
        return _model


def _color_feat(img):
    """Gavdaning 3 qismi bo'yicha HSV histogramma (kiyim rangi)."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    parts = []
    h3 = img.shape[0] // 3
    for i in range(3):
        band = hsv[i * h3:(i + 1) * h3]
        # H(16) x S(8) birgalikda + V(8) alohida
        hs = cv2.calcHist([band], [0, 1], None, [16, 8], [0, 180, 0, 256])
        v = cv2.calcHist([band], [2], None, [8], [0, 256])
        parts.append(hs.flatten())
        parts.append(v.flatten())
    f = np.concatenate(parts).astype(np.float32)
    n = np.linalg.norm(f)
    return f / n if n > 0 else f


def _deep_feat(img):
    """mobilenet xususiyatlari (576 o'lcham)."""
    m = _load_model()
    if m is None:
        return None
    import torch
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    mean = np.array([0.485, 0.456, 0.406], np.float32)
    std = np.array([0.229, 0.224, 0.225], np.float32)
    x = (rgb - mean) / std
    x = torch.from_numpy(x.transpose(2, 0, 1)).unsqueeze(0)
    with torch.no_grad():
        f = m(x).numpy().flatten().astype(np.float32)
    n = np.linalg.norm(f)
    return f / n if n > 0 else f


def embed(crop):
    """Odam kesmasidan barmoq izi (float32 vektor). Kichik kesma -> None."""
    if crop is None or crop.size == 0:
        return None
    h, w = crop.shape[:2]
    if h < 48 or w < 20:          # juda kichik - ishonchsiz
        return None
    img = cv2.resize(crop, (W, H), interpolation=cv2.INTER_LINEAR)
    color = _color_feat(img) * COLOR_W
    deep = _deep_feat(img)
    if deep is None:
        vec = color
    else:
        vec = np.concatenate([color, deep * DEEP_W])
    n = np.linalg.norm(vec)
    return (vec / n).astype(np.float32) if n > 0 else None


def similarity(a, b):
    """Ikki barmoq izi o'xshashligi: 0..1 (1 = bir xil)."""
    if a is None or b is None or a.shape != b.shape:
        return 0.0
    return float(np.clip(np.dot(a, b), 0.0, 1.0))


def kesma(frame, xyxy, pad=0.04):
    """Kadrdan odam kesmasini oladi (chetidan biroz kengaytirib)."""
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in xyxy]
    px, py = int((x2 - x1) * pad), int((y2 - y1) * pad)
    x1, y1 = max(0, x1 - px), max(0, y1 - py)
    x2, y2 = min(w, x2 + px), min(h, y2 + py)
    if x2 <= x1 or y2 <= y1:
        return None
    return frame[y1:y2, x1:x2]
