"""Mini App web-server — kassa nazorati.

Do'kon kompyuterida ishlaydi. Mini App (telefon) shu serverga ulanadi:
  GET  /                  -> Mini App sahifasi
  GET  /api/status        -> hozirgi ahvol (jonli)
  GET  /api/events        -> so'nggi hodisalar (alertlar)
  POST /api/clip          -> {start,end} oralig'idan video KESADI (so'rovga ko'ra)
  GET  /clip/{id}.mp4     -> yasalgan videoni beradi
  POST /api/done/{id}     -> "ish bitdi": videoni O'CHIRADI

Video avtomatik yuklanmaydi — faqat so'ralganda kesiladi. Faqat egasining
Telegram'i kira oladi (initData imzosi tekshiriladi).
"""
import datetime as dt
import hashlib
import hmac
import json
import os
import time
import urllib.parse
import uuid
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from storage import evidence

STATIC = Path(__file__).parent / "static"
CLIPS = Path("webapp_clips")
CLIPS.mkdir(exist_ok=True)

# main.py startda to'ldiradi
CTX = {"db": None, "arxiv": "kassa_arxiv", "kassa": "kassa", "live": {},
       "token": "", "owner": "", "dev": False}
_clips = {}  # id -> path

app = FastAPI(title="Kassa nazorati")


def _check(init_data):
    """Telegram WebApp initData imzosini tekshiradi va egasi ekanini."""
    if CTX["dev"]:
        return True
    # Token yoki egasi sozlanmagan bo'lsa imzo hech narsani isbotlamaydi
    # (bo'sh kalit bilan uni istalgan odam yasay oladi) — hammasini rad etamiz.
    if not init_data or not CTX["token"] or not CTX["owner"]:
        return False
    try:
        pairs = dict(urllib.parse.parse_qsl(init_data))
        got = pairs.pop("hash", "")
        check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
        secret = hmac.new(b"WebAppData", CTX["token"].encode(), hashlib.sha256).digest()
        calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, got):
            return False
        user = json.loads(pairs.get("user", "{}"))
        return str(user.get("id")) == str(CTX["owner"])
    except Exception:
        return False


def _auth(init_data):
    if not _check(init_data):
        raise HTTPException(status_code=401, detail="ruxsat yo'q")


@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC / "index.html").read_text(encoding="utf-8")


@app.get("/api/status")
def status(x_init: str = Header("", alias="X-Init-Data")):
    _auth(x_init)
    out = []
    for name, s in CTX["live"].items():
        out.append({
            "kamera": name, "kadrda": s.get("kadrda", 0),
            "kirdi": s.get("kirdi", 0), "chiqdi": s.get("chiqdi", 0),
            "navbat": s.get("navbat", 0), "kutish": int(s.get("kutish", 0)),
            "jonli": (time.time() - s.get("ts", 0)) < 30,
            "line": s.get("line", False), "zone": s.get("zone", False),
        })
    return {"kameralar": out}


@app.get("/api/events")
def events(x_init: str = Header("", alias="X-Init-Data")):
    _auth(x_init)
    rows = CTX["db"]._q(
        "SELECT ts,camera,rule,message FROM events ORDER BY ts DESC LIMIT 50")
    out = []
    for ts, cam, rule, msg in rows:
        d = dt.datetime.fromtimestamp(ts)
        out.append({"ts": int(ts), "kamera": cam, "qoida": rule, "xabar": msg,
                    "vaqt": d.strftime("%d.%m %H:%M:%S")})
    return {"hodisalar": out}


@app.post("/api/clip")
async def clip(request: Request, x_init: str = Header("", alias="X-Init-Data")):
    _auth(x_init)
    body = await request.json()
    try:
        start = dt.datetime.fromtimestamp(float(body["start"]))
        end = dt.datetime.fromtimestamp(float(body["end"]))
    except (KeyError, ValueError, TypeError):
        raise HTTPException(status_code=400, detail="start/end noto'g'ri")
    if (end - start).total_seconds() > 600:
        end = start + dt.timedelta(seconds=600)
    cid = uuid.uuid4().hex[:12]
    out = str(CLIPS / f"{cid}.mp4")
    n, path = evidence.klip_yasa(CTX["arxiv"], CTX["kassa"], start, end, out, fps=4)
    if not path:
        return JSONResponse({"ok": False,
                             "xabar": "Bu vaqt uchun arxivda kadr yo'q."})
    _clips[cid] = path
    return {"ok": True, "id": cid, "url": f"/clip/{cid}.mp4", "kadrlar": n,
            "start": start.strftime("%H:%M:%S"), "end": end.strftime("%H:%M:%S")}


@app.get("/clip/{cid}.mp4")
def get_clip(cid: str):
    path = _clips.get(cid)
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="topilmadi")
    return FileResponse(path, media_type="video/mp4")


@app.post("/api/done/{cid}")
def done(cid: str, x_init: str = Header("", alias="X-Init-Data")):
    _auth(x_init)
    path = _clips.pop(cid, None)
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass
    return {"ok": True}


def tozala_kliplar():
    """Ishga tushganda eski (yakunlanmagan) kliplarni o'chiradi."""
    for f in CLIPS.glob("*.mp4"):
        try:
            f.unlink()
        except OSError:
            pass
