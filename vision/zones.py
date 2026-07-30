import numpy as np
import supervision as sv


class LineCounter:
    """Virtual chiziq: markazi kesib o'tgan odamlarni kirdi/chiqdi deb sanaydi."""

    def __init__(self, p1, p2):
        self.zone = sv.LineZone(
            start=sv.Point(*p1),
            end=sv.Point(*p2),
            triggering_anchors=[sv.Position.CENTER],
        )

    def update(self, det: sv.Detections):
        # tracker_id hali berilmagan kadrlarda (birinchi 1-2 kadr) sanamaymiz
        if det.tracker_id is not None:
            self.zone.trigger(det)

    @property
    def kirdi(self) -> int:
        return self.zone.in_count

    @property
    def chiqdi(self) -> int:
        return self.zone.out_count


class QueueZone:
    """Poligon zona: ichidagi odamlar soni va eng uzoq kutish vaqti (soniya)."""

    def __init__(self, points):
        self.zone = sv.PolygonZone(polygon=np.array(points, dtype=int))
        self._enter_ts = {}

    def update(self, det: sv.Detections, now: float):
        mask = self.zone.trigger(det)
        count = int(mask.sum())
        inside = set()
        if det.tracker_id is not None:
            inside = {int(t) for t in det.tracker_id[mask]}
        for tid in inside:
            self._enter_ts.setdefault(tid, now)
        for tid in list(self._enter_ts):
            if tid not in inside:
                del self._enter_ts[tid]
        wait = max((now - t for t in self._enter_ts.values()), default=0.0)
        return count, wait
