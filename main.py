"""Video analitika — 2-bosqich: sanash + navbat + SQLite + Telegram alert.

Ishga tushirish:
    python main.py                      # config.yaml dagi hamma kamera
    python main.py --tekshir            # kameralar ulanishini tekshirish + surat
    python main.py --camera sinov       # faqat bitta kamera
    python main.py --show               # jonli oyna bilan (chiqish: q)
    python main.py --save natija.mp4    # belgilangan videoni saqlash
"""
import argparse
import threading
import time

import cv2
import numpy as np
import supervision as sv
import yaml

from bot.alerts import TelegramNotifier
from bot.commands import CommandBot
from events.engine import RuleEngine
from report import daily
from storage import evidence
from storage.db import Database
from vision.detector import PersonTracker
from vision.stream import FrameSource, ISAPIFrameSource, masked
from vision.zones import LineCounter, QueueZone

NVR = {}  # config'dagi nvr bloki (ip/user/pass)


def build_source(cfg):
    """config'ga qarab kadr manbaini tanlaydi: NVR kanali yoki RTSP/fayl/webcam."""
    if "channel" in cfg and NVR:
        return ISAPIFrameSource(NVR["ip"], NVR["user"], NVR["pass"],
                                cfg["channel"], cfg.get("fps", 3))
    return FrameSource(cfg["source"], cfg.get("fps", 3))

PRINT_INTERVAL = 2.0
LINE_COLOR = (60, 60, 230)
ZONE_COLOR = (30, 160, 240)
UZILISH_SEK = 30


class MinuteAgg:
    """Daqiqalik agregat: kirdi/chiqdi delta, navbat/kutish maksimumi."""

    def __init__(self, db, camera):
        self.db = db
        self.camera = camera
        self.minute = None
        self.k0 = self.c0 = 0
        self.kirdi = self.chiqdi = 0
        self.navbat_max = 0
        self.kutish_max = 0.0

    def update(self, now, kirdi, chiqdi, navbat, kutish):
        minute = int(now // 60) * 60
        if self.minute is None:
            self.minute, self.k0, self.c0 = minute, kirdi, chiqdi
        elif minute != self.minute:
            self.db.yoz_metrika(self.minute, self.camera,
                                kirdi - self.k0, chiqdi - self.c0,
                                self.navbat_max, self.kutish_max)
            self.minute, self.k0, self.c0 = minute, kirdi, chiqdi
            self.navbat_max, self.kutish_max = 0, 0.0
        self.kirdi, self.chiqdi = kirdi, chiqdi
        self.navbat_max = max(self.navbat_max, navbat)
        self.kutish_max = max(self.kutish_max, kutish)

    def flush(self):
        if self.minute is not None:
            self.db.yoz_metrika(self.minute, self.camera,
                                self.kirdi - self.k0, self.chiqdi - self.c0,
                                self.navbat_max, self.kutish_max)


def annotate(frame, det, cfg, line, zone, navbat, kutish, box_ann, label_ann):
    frame = box_ann.annotate(frame, det)
    if det.tracker_id is not None:
        labels = [f"ID {int(t)}" for t in det.tracker_id]
        frame = label_ann.annotate(frame, det, labels=labels)
    if cfg.get("line"):
        (x1, y1), (x2, y2) = cfg["line"]
        cv2.line(frame, (x1, y1), (x2, y2), LINE_COLOR, 2)
    if cfg.get("zone"):
        cv2.polylines(frame, [np.array(cfg["zone"], np.int32)], True, ZONE_COLOR, 2)
    parts = []
    if line:
        parts.append(f"kirdi {line.kirdi}  chiqdi {line.chiqdi}")
    if zone:
        parts.append(f"navbat {navbat}  kutish {int(kutish)}s")
    cv2.rectangle(frame, (0, 0), (frame.shape[1], 34), (30, 30, 30), -1)
    cv2.putText(frame, "  ".join(parts), (10, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    return frame


def run_camera(name, cfg, show, save, stop, db, engine, notifier, rasm, status,
               arxiv=None):
    tracker = PersonTracker(conf=cfg.get("conf", 0.35))
    source = build_source(cfg)
    line = LineCounter(cfg["line"][0], cfg["line"][1]) if cfg.get("line") else None
    zone = QueueZone(cfg["zone"]) if cfg.get("zone") else None
    agg = MinuteAgg(db, name)
    last_arxiv = 0.0

    box_ann = sv.BoxAnnotator(thickness=2)
    label_ann = sv.LabelAnnotator(text_scale=0.5)
    writer = None
    last_print = 0.0
    navbat, kutish = 0, 0.0
    frames_done = 0
    t0 = time.time()
    status[name] = {"ts": time.time(), "is_file": source.is_file,
                    "line": bool(line), "zone": bool(zone)}

    for frame, ts in source.frames():
        if stop.is_set():
            break
        det = tracker.track(frame)
        now = time.time()
        status[name]["ts"] = now
        if line:
            line.update(det)
        if zone:
            navbat, kutish = zone.update(det, now)
        frames_done += 1

        metrics = {
            "kirdi": line.kirdi if line else 0,
            "chiqdi": line.chiqdi if line else 0,
            "ichkarida": (line.kirdi - line.chiqdi) if line else 0,
            "navbat": navbat,
            "kutish": int(kutish),
            "kadrda": len(det),
        }
        status[name].update(metrics)
        agg.update(now, metrics["kirdi"], metrics["chiqdi"], navbat, kutish)

        # Kassa dalil arxivi: harakat bo'lganda kadrni JPEG saqlaymiz (~2 fps)
        if arxiv and metrics["kadrda"] > 0 and now - last_arxiv >= 0.5:
            last_arxiv = now
            try:
                evidence.saqla(arxiv, name, frame, now)
            except Exception:
                pass

        frame = annotate(frame, det, cfg, line, zone, navbat, kutish,
                         box_ann, label_ann)

        for rule_name, text in engine.update(name, metrics, now):
            print(f"[{name}] ALERT ({rule_name}): {text}", flush=True)
            db.yoz_hodisa(now, name, rule_name, text)
            notifier.alert(text, frame if rasm else None)

        if save:
            if writer is None:
                writer = cv2.VideoWriter(
                    save, cv2.VideoWriter_fourcc(*"mp4v"),
                    cfg.get("fps", 3), (frame.shape[1], frame.shape[0]))
            writer.write(frame)
        if show:
            cv2.imshow(name, frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                stop.set()

        if now - last_print >= PRINT_INTERVAL:
            last_print = now
            parts = [f"[{name}]"]
            if line:
                parts.append(f"kirdi={line.kirdi} chiqdi={line.chiqdi} "
                             f"ichkarida={metrics['ichkarida']}")
            parts.append(f"kadrda={len(det)}")
            if zone:
                parts.append(f"navbat={navbat} kutish={int(kutish)}s")
            print(" ".join(parts), flush=True)

    agg.flush()
    if writer is not None:
        writer.release()
    parts = [f"[{name}] YAKUN:"]
    if line:
        parts.append(f"kirdi={line.kirdi} chiqdi={line.chiqdi}")
    parts.append(f"kadr={frames_done} vaqt={time.time() - t0:.0f}s")
    print(" ".join(parts), flush=True)


def watchdog(status, notifier, db, stop):
    """Jonli kamera kadr bermay qolsa alert, tiklansa yana xabar."""
    down = set()
    while not stop.is_set():
        now = time.time()
        for name, st in list(status.items()):
            if st["is_file"]:
                continue
            silent = now - st["ts"]
            if silent > UZILISH_SEK and name not in down:
                down.add(name)
                msg = (f"DIQQAT: {name} kamerasi {int(silent)} soniyadan beri "
                       f"kadr bermayapti")
                print(f"[watchdog] {msg}", flush=True)
                db.yoz_hodisa(now, name, "kamera_uzildi", msg)
                notifier.alert(msg)
            elif silent < 10 and name in down:
                down.discard(name)
                msg = f"{name} kamerasi tiklandi"
                print(f"[watchdog] {msg}", flush=True)
                db.yoz_hodisa(now, name, "kamera_tiklandi", msg)
                notifier.alert(msg)
        time.sleep(5)


def scheduler(db, tg, kirish_kamera, hisobot_soat, arxiv, arxiv_kun, stop):
    """Har kuni belgilangan soatda hisobot yuboradi + eski arxivni tozalaydi."""
    import datetime as dt
    oxirgi = None
    while not stop.is_set():
        now = dt.datetime.now()
        bugun = now.date()
        if now.hour == hisobot_soat and oxirgi != bugun:
            oxirgi = bugun
            try:
                daily.yubor(db, tg.get("token"), tg.get("chat_id"), kirish_kamera)
            except Exception as e:
                print(f"[hisobot] xato: {e}", flush=True)
            try:
                evidence.tozala(arxiv, arxiv_kun)      # eski dalil kadrlarini o'chir
            except Exception:
                pass
        for _ in range(60):          # ~1 daqiqada bir tekshiradi
            if stop.is_set():
                return
            time.sleep(1)


def start_webserver(conf, db, status, tg, kassa_kamera, arxiv):
    """Mini App web-serverini alohida ipda ishga tushiradi."""
    import uvicorn

    from webapp import server as ws
    ws.CTX.update(db=db, arxiv=arxiv, kassa=kassa_kamera, live=status,
                  token=tg.get("token", ""), owner=str(tg.get("chat_id", "")),
                  dev=bool(conf.get("webapp_dev", False)))
    ws.tozala_kliplar()
    port = int(conf.get("webapp_port", 8770))
    cfg = uvicorn.Config(ws.app, host="0.0.0.0", port=port, log_level="warning")
    srv = uvicorn.Server(cfg)
    threading.Thread(target=srv.run, daemon=True).start()
    print(f"Mini App serveri: http://localhost:{port}", flush=True)


def tekshir(cams):
    """Har bir kamerani ochib 1 kadr oladi, suratini saqlaydi."""
    print("Kameralar tekshirilmoqda...")
    hammasi_ok = True
    for name, cfg in cams.items():
        frame = None
        src_txt = f"kanal {cfg['channel']}" if "channel" in cfg else masked(cfg.get("source"))
        try:
            source = build_source(cfg)
            for frame, _ in source.frames():
                break
        except Exception as e:
            print(f"  [XATO] {name}: {e}")
        if frame is not None:
            h, w = frame.shape[:2]
            surat = f"{name}_surat.jpg"
            cv2.imwrite(surat, frame)
            print(f"  [OK]   {name}: {w}x{h} - surat: {surat}")
        else:
            hammasi_ok = False
            print(f"  [XATO] {name}: kadr olinmadi ({src_txt})")
    if hammasi_ok:
        print("Hammasi joyida. Endi ishga tushiring: python main.py")
    else:
        print("Ochilmagan kamera manzilini config.yaml da tuzating.")


def main():
    ap = argparse.ArgumentParser(description="Video analitika - 2-bosqich")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--camera", help="faqat shu nomdagi kamerani ishga tushirish")
    ap.add_argument("--show", action="store_true", help="jonli oyna (chiqish: q)")
    ap.add_argument("--save", help="belgilangan videoni saqlash yo'li")
    ap.add_argument("--tekshir", action="store_true",
                    help="kameralarni tekshirib surat olish va chiqish")
    args = ap.parse_args()

    with open(args.config, encoding="utf-8") as f:
        conf = yaml.safe_load(f)

    global NVR
    NVR = conf.get("nvr") or {}
    cams = conf["cameras"]
    if args.camera:
        cams = {args.camera: cams[args.camera]}

    if args.tekshir:
        tekshir(cams)
        return

    tg = conf.get("telegram") or {}
    notifier = TelegramNotifier(tg.get("token"), tg.get("chat_id"))
    rasm = bool(tg.get("rasm", True))
    db = Database(conf.get("db", "analitika.db"))
    engine = RuleEngine(conf.get("rules"))
    print(f"Kameralar: {', '.join(cams)} | qoidalar: {len(engine.rules)} | "
          f"baza: {conf.get('db', 'analitika.db')}", flush=True)

    # kirish/kassa kameralarini aniqlaymiz (config yoki line/zone bo'yicha)
    def _topib(kalit, xossa):
        if conf.get(kalit) in cams:
            return conf[kalit]
        for nm, c in cams.items():
            if xossa in c:
                return nm
        return next(iter(cams), None)

    kirish_kamera = _topib("kirish_kamera", "line")
    kassa_kamera = _topib("kassa_kamera", "zone")
    arxiv = conf.get("arxiv", "kassa_arxiv")
    arxiv_kun = int(conf.get("arxiv_kun", 14))

    stop = threading.Event()
    status = {}
    threads = []
    for name, cfg in cams.items():
        save = args.save
        if save and len(cams) > 1:
            save = f"{name}_{save}"
        cam_arxiv = arxiv if name == kassa_kamera else None
        t = threading.Thread(
            target=run_camera,
            args=(name, cfg, args.show, save, stop, db, engine, notifier,
                  rasm, status, cam_arxiv),
            daemon=True)
        t.start()
        threads.append(t)
    threading.Thread(target=watchdog, args=(status, notifier, db, stop),
                     daemon=True).start()

    bot = CommandBot(tg.get("token"), tg.get("chat_id"), db, status,
                     kassa_kamera, arxiv)
    threading.Thread(target=bot.run, args=(stop,), daemon=True).start()
    print(f"Buyruq boti yoqildi | kassa={kassa_kamera} kirish={kirish_kamera}",
          flush=True)

    hisobot_soat = int(conf.get("hisobot_soat", 21))
    threading.Thread(target=scheduler,
                     args=(db, tg, kirish_kamera, hisobot_soat, arxiv, arxiv_kun, stop),
                     daemon=True).start()
    print(f"Kunlik hisobot har kuni soat {hisobot_soat}:00 da", flush=True)

    try:
        start_webserver(conf, db, status, tg, kassa_kamera, arxiv)
    except Exception as e:
        print(f"[webapp] server ishga tushmadi: {e}", flush=True)

    # Railway gibrid: agent tashqariga ulanib video so'rovlarini bajaradi
    if conf.get("railway_url") and conf.get("agent_secret"):
        from bot.agent import Agent
        ag = Agent(conf["railway_url"], conf["agent_secret"], db, status,
                   kassa_kamera, arxiv)
        threading.Thread(target=ag.run, args=(stop,), daemon=True).start()
    try:
        while any(t.is_alive() for t in threads):
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("To'xtatilmoqda...")
        stop.set()
    for t in threads:
        t.join(timeout=5)


if __name__ == "__main__":
    main()
