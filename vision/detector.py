import supervision as sv
from ultralytics import YOLO

PERSON = 0  # COCO klass raqami


class PersonTracker:
    """YOLO11n bilan odamlarni aniqlaydi, ByteTrack bilan barqaror ID beradi.

    Har kamera o'z nusxasini ishlatadi (persist=True holat modelda saqlanadi).
    """

    def __init__(self, model_path="yolo11n.pt", conf=0.35, imgsz=640):
        self.model = YOLO(model_path)
        self.conf = conf
        self.imgsz = imgsz

    def track(self, frame) -> sv.Detections:
        result = self.model.track(
            frame,
            persist=True,
            classes=[PERSON],
            conf=self.conf,
            imgsz=self.imgsz,
            tracker="bytetrack.yaml",
            verbose=False,
        )[0]
        return sv.Detections.from_ultralytics(result)
