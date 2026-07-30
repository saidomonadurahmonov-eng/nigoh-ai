"""Railway'da ishlaydigan Mini App + so'rov navbati (gibrid arxitektura).

Do'kon kompyuteri bu yerga faqat TASHQARIGA ulanadi (agent):
 - holat/hodisalarni yuboradi (heartbeat)
 - video so'rovlarini so'rab oladi, lokal kesib, bu yerga yuklaydi

Telefondagi Mini App shu yerga ulanadi. Faqat egasining Telegram'i kiradi.
So'ralgan video vaqtincha shu yerda turadi, "Ish bitdi"da o'chadi.

ENV: BOT_TOKEN, OWNER_ID, AGENT_SECRET
"""
import hashlib
import hmac
import json
import os
import time
import urllib.parse
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER_ID = os.environ.get("OWNER_ID", "")
AGENT_SECRET = os.environ.get("AGENT_SECRET", "")
DEV = os.environ.get("DEV") == "1"

STATIC = Path(__file__).parent / "static"
CLIPS = Path("clips")
CLIPS.mkdir(exist_ok=True)

app = FastAPI(title="Kassa nazorati")

STATE = {"status": {"kameralar": []}, "events": {"hodisalar": []},
         "sessions": [], "hb": 0}
REQS = {}       # id -> {type,start,end,status,url,ts,xabar}
_counter = [0]


# ---------- Auth ----------
def _valid_init(init_data):
    if DEV:
        return True
    if not init_data:
        return False
    try:
        pairs = dict(urllib.parse.parse_qsl(init_data))
        got = pairs.pop("hash", "")
        check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, got):
            return False
        user = json.loads(pairs.get("user", "{}"))
        return str(user.get("id")) == str(OWNER_ID)
    except Exception:
        return False


def _auth_user(init_data):
    if not _valid_init(init_data):
        raise HTTPException(status_code=401, detail="ruxsat yo'q")


def _auth_agent(secret):
    if not AGENT_SECRET or not hmac.compare_digest(secret or "", AGENT_SECRET):
        raise HTTPException(status_code=403, detail="agent taqiqlangan")


# ---------- Mini App (telefon) ----------
@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC / "index.html").read_text(encoding="utf-8")


@app.get("/api/status")
def status(x_init: str = Header("", alias="X-Init-Data")):
    _auth_user(x_init)
    online = (time.time() - STATE["hb"]) < 30
    return {"online": online, **STATE["status"]}


@app.get("/api/events")
def events(x_init: str = Header("", alias="X-Init-Data")):
    _auth_user(x_init)
    return STATE["events"]


@app.get("/api/sessions")
def sessions(x_init: str = Header("", alias="X-Init-Data")):
    _auth_user(x_init)
    return {"sessions": STATE["sessions"]}


@app.post("/api/clip")
async def clip(request: Request, x_init: str = Header("", alias="X-Init-Data")):
    _auth_user(x_init)
    body = await request.json()
    try:
        start = float(body["start"])
        end = float(body["end"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(status_code=400, detail="start/end noto'g'ri")
    if (time.time() - STATE["hb"]) > 30:
        return JSONResponse({"ok": False, "xabar": "Do'kon kompyuteri oflayn."})
    _counter[0] += 1
    rid = f"r{int(time.time())}{_counter[0]}"
    REQS[rid] = {"type": "clip", "start": start, "end": end, "status": "pending",
                 "url": None, "ts": time.time(), "xabar": None}
    return {"ok": True, "id": rid}


@app.post("/api/delete_segment")
async def delete_segment(request: Request, x_init: str = Header("", alias="X-Init-Data")):
    _auth_user(x_init)
    body = await request.json()
    try:
        start = float(body["start"])
        end = float(body["end"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(status_code=400, detail="start/end noto'g'ri")
    _counter[0] += 1
    rid = f"d{int(time.time())}{_counter[0]}"
    REQS[rid] = {"type": "delete", "start": start, "end": end, "status": "pending",
                 "url": None, "ts": time.time(), "xabar": None}
    return {"ok": True, "id": rid}


@app.get("/api/clip/{rid}")
def clip_status(rid: str, x_init: str = Header("", alias="X-Init-Data")):
    _auth_user(x_init)
    r = REQS.get(rid)
    if not r:
        raise HTTPException(status_code=404, detail="topilmadi")
    return {"status": r["status"], "url": r["url"], "xabar": r["xabar"]}


@app.get("/clip/{rid}.mp4")
def get_clip(rid: str):
    r = REQS.get(rid)
    p = CLIPS / f"{rid}.mp4"
    if not r or not p.exists():
        raise HTTPException(status_code=404, detail="topilmadi")
    return FileResponse(str(p), media_type="video/mp4")


@app.post("/api/done/{rid}")
def done(rid: str, x_init: str = Header("", alias="X-Init-Data")):
    _auth_user(x_init)
    REQS.pop(rid, None)
    p = CLIPS / f"{rid}.mp4"
    if p.exists():
        try:
            p.unlink()
        except OSError:
            pass
    return {"ok": True}


# ---------- Agent (do'kon kompyuteri) ----------
@app.post("/agent/heartbeat")
async def heartbeat(request: Request, x_secret: str = Header("", alias="X-Agent-Secret")):
    _auth_agent(x_secret)
    data = await request.json()
    STATE["status"] = data.get("status", {"kameralar": []})
    STATE["events"] = data.get("events", {"hodisalar": []})
    STATE["sessions"] = data.get("sessions", [])
    STATE["hb"] = time.time()
    return {"ok": True}


@app.get("/agent/next")
def agent_next(x_secret: str = Header("", alias="X-Agent-Secret")):
    _auth_agent(x_secret)
    now = time.time()
    for rid, r in REQS.items():
        if r["status"] == "processing" and now - r["ts"] > 120:
            r["status"] = "pending"      # osilib qolgan so'rovni qaytaramiz
    for rid, r in sorted(REQS.items(), key=lambda kv: kv[1]["ts"]):
        if r["status"] == "pending":
            r["status"] = "processing"
            r["ts"] = now
            return {"id": rid, "type": r.get("type", "clip"),
                    "start": r["start"], "end": r["end"]}
    return {}


@app.post("/agent/deleted/{rid}")
async def agent_deleted(rid: str, request: Request,
                        x_secret: str = Header("", alias="X-Agent-Secret")):
    _auth_agent(x_secret)
    r = REQS.get(rid)
    if r:
        body = await request.json()
        r["status"] = "done"
        r["xabar"] = f"arxivdan {body.get('kadr', 0)} kadr o'chirildi"
    return {"ok": True}


@app.post("/agent/upload/{rid}")
async def agent_upload(rid: str, video: UploadFile = File(...),
                       x_secret: str = Header("", alias="X-Agent-Secret")):
    _auth_agent(x_secret)
    r = REQS.get(rid)
    if not r:
        raise HTTPException(status_code=404, detail="so'rov yo'q")
    with open(CLIPS / f"{rid}.mp4", "wb") as f:
        f.write(await video.read())
    r["status"] = "ready"
    r["url"] = f"/clip/{rid}.mp4"
    return {"ok": True}


@app.post("/agent/failed/{rid}")
async def agent_failed(rid: str, request: Request,
                       x_secret: str = Header("", alias="X-Agent-Secret")):
    _auth_agent(x_secret)
    r = REQS.get(rid)
    if r:
        r["status"] = "failed"
        body = await request.json()
        r["xabar"] = body.get("xabar", "arxivda kadr yo'q")
    return {"ok": True}
