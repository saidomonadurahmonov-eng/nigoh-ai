"""Barcha model fayllarini oldindan yuklab, dastur papkasiga joylaydi.

Nega kerak: dastur birinchi ishga tushganda modellarni internetdan o'zi
yuklaydi (YOLO, yuz modellari, mobilenet). Obyektda internet sekin yoki
GitHub ochilmasa — tizim yarim ishlaydi. Bu skript ularni OLDINDAN yuklaydi,
shunda o'rnatuvchi paketiga qo'shib yuborish mumkin (tools/paket_yasa.py).

Ishga tushirish (dastur papkasida):
    python tools/modellar_yukla.py

Natija:
    yolo11n.pt
    models/face_detection_yunet_2023mar.onnx
    models/face_recognition_sface_2021dec.onnx
    models/torch/hub/checkpoints/mobilenet_v3_small-*.pth
"""
import os
import sys

ILDIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ILDIZ)
sys.path.insert(0, ILDIZ)

TORCH = os.path.join(ILDIZ, "models", "torch")
os.makedirs(os.path.join(TORCH, "hub", "checkpoints"), exist_ok=True)
os.environ["TORCH_HOME"] = TORCH          # mobilenet shu yerga tushsin


def main():
    xato = 0

    try:
        from ultralytics import YOLO
        YOLO("yolo11n.pt")
        print("[ok]   yolo11n.pt")
    except Exception as e:
        xato += 1
        print(f"[XATO] yolo11n.pt: {e}")

    try:
        from vision import face
        for nom in (face.YUNET, face.SFACE):
            face._yukla_fayl(nom)
        print("[ok]   yuz modellari (YuNet + SFace)")
    except Exception as e:
        xato += 1
        print(f"[XATO] yuz modellari: {e}")

    try:
        from torchvision.models import (MobileNet_V3_Small_Weights,
                                        mobilenet_v3_small)
        mobilenet_v3_small(weights=MobileNet_V3_Small_Weights.DEFAULT)
        print("[ok]   mobilenet_v3_small")
    except Exception as e:
        xato += 1
        print(f"[XATO] mobilenet_v3_small: {e}")

    print("Hammasi tayyor." if not xato else f"{xato} ta model yuklanmadi.")
    return 1 if xato else 0


if __name__ == "__main__":
    sys.exit(main())
