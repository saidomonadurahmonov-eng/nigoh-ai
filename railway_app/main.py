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

from fastapi import (FastAPI, File, Form, Header, HTTPException, Request,
                     UploadFile)
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


@app.post("/api/search")
async def search(request: Request, photo: UploadFile = File(...),
                 x_init: str = Header("", alias="X-Init-Data")):
    """Rasm yuklanadi -> do'kon kompyuteri indeksdan o'sha odamni qidiradi."""
    _auth_user(x_init)
    if (time.time() - STATE["hb"]) > 30:
        return JSONResponse({"ok": False, "xabar": "Do'kon kompyuteri oflayn."})
    data = await photo.read()
    if len(data) > 12 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="rasm juda katta")
    _counter[0] += 1
    sid = f"s{int(time.time())}{_counter[0]}"
    (CLIPS / f"{sid}.query.jpg").write_bytes(data)
    kun = float(request.query_params.get("kun", 1))
    REQS[sid] = {"type": "search", "status": "pending", "ts": time.time(),
                 "start": time.time() - kun * 86400, "end": time.time(),
                 "url": None, "xabar": None, "natija": None}
    return {"ok": True, "id": sid}


@app.get("/api/search/{sid}")
def search_status(sid: str, x_init: str = Header("", alias="X-Init-Data")):
    _auth_user(x_init)
    r = REQS.get(sid)
    if not r:
        raise HTTPException(status_code=404, detail="topilmadi")
    return {"status": r["status"], "natija": r.get("natija"),
            "xabar": r.get("xabar")}


@app.post("/api/kun")
async def kun_soro(request: Request, x_init: str = Header("", alias="X-Init-Data")):
    """Sana tanlanadi -> do'kon kompyuteri NVR arxivini ko'rib chiqadi."""
    _auth_user(x_init)
    if (time.time() - STATE["hb"]) > 30:
        return JSONResponse({"ok": False, "xabar": "Do'kon kompyuteri oflayn."})
    body = await request.json()
    sana = str(body.get("sana", ""))[:10]
    if not sana:
        raise HTTPException(status_code=400, detail="sana kerak")
    _counter[0] += 1
    rid = f"k{int(time.time())}{_counter[0]}"
    REQS[rid] = {"type": "kun", "status": "pending", "ts": time.time(),
                 "sana": sana, "kanal": int(body.get("kanal", 1)),
                 "nomi": str(body.get("nomi", ""))[:40],
                 "start": 0, "end": 0, "url": None, "xabar": None,
                 "xulosa": None, "lahzalar": None}
    return {"ok": True, "id": rid}


@app.get("/api/kun/{rid}")
def kun_holat(rid: str, x_init: str = Header("", alias="X-Init-Data")):
    _auth_user(x_init)
    r = REQS.get(rid)
    if not r:
        raise HTTPException(status_code=404, detail="topilmadi")
    return {"status": r["status"], "xulosa": r.get("xulosa"),
            "lahzalar": r.get("lahzalar"), "xabar": r.get("xabar")}


@app.post("/agent/kun_result/{rid}")
async def kun_result(rid: str, request: Request,
                     x_secret: str = Header("", alias="X-Agent-Secret")):
    _auth_agent(x_secret)
    r = REQS.get(rid)
    if not r:
        raise HTTPException(status_code=404, detail="topilmadi")
    body = await request.json()
    r["xulosa"] = body.get("xulosa")
    r["lahzalar"] = body.get("lahzalar")
    r["xabar"] = body.get("xabar")
    r["status"] = "ready"
    return {"ok": True}


@app.get("/api/kameralar")
def kameralar(x_init: str = Header("", alias="X-Init-Data")):
    """Kun tahlili uchun kamera ro'yxati (agent heartbeat'da yuboradi)."""
    _auth_user(x_init)
    return {"kameralar": STATE.get("kanallar", {})}


@app.get("/api/employees")
def employees(x_init: str = Header("", alias="X-Init-Data")):
    _auth_user(x_init)
    return {"hodimlar": STATE.get("employees", []),
            "stat": STATE.get("index_stat", {})}


@app.post("/api/employee")
async def employee_add(ism: str = Form(...), photo: UploadFile = File(...),
                       x_init: str = Header("", alias="X-Init-Data")):
    """Hodim qo'shish: ism + yuz rasmi."""
    _auth_user(x_init)
    if (time.time() - STATE["hb"]) > 30:
        return JSONResponse({"ok": False, "xabar": "Do'kon kompyuteri oflayn."})
    data = await photo.read()
    _counter[0] += 1
    eid = f"e{int(time.time())}{_counter[0]}"
    (CLIPS / f"{eid}.query.jpg").write_bytes(data)
    REQS[eid] = {"type": "employee_add", "status": "pending", "ts": time.time(),
                 "start": 0, "end": 0, "ism": ism.strip(), "url": None,
                 "xabar": None, "natija": None}
    return {"ok": True, "id": eid}


@app.post("/api/employee_del/{hid}")
def employee_del(hid: int, x_init: str = Header("", alias="X-Init-Data")):
    _auth_user(x_init)
    _counter[0] += 1
    rid = f"x{int(time.time())}{_counter[0]}"
    REQS[rid] = {"type": "employee_del", "status": "pending", "ts": time.time(),
                 "start": float(hid), "end": 0, "url": None, "xabar": None}
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
    STATE["employees"] = data.get("employees", [])
    STATE["index_stat"] = data.get("index_stat", {})
    STATE["kanallar"] = data.get("kanallar", {})
    STATE["hb"] = time.time()
    return {"ok": True}


@app.get("/agent/next")
def agent_next(x_secret: str = Header("", alias="X-Agent-Secret")):
    _auth_agent(x_secret)
    now = time.time()
    for rid, r in REQS.items():
        # kun tahlili uzoq davom etadi (arxivni skanerlash) — unga ko'proq vaqt
        chegara = 1800 if r.get("type") == "kun" else 120
        if r["status"] == "processing" and now - r["ts"] > chegara:
            r["status"] = "pending"      # osilib qolgan so'rovni qaytaramiz
    for rid, r in sorted(REQS.items(), key=lambda kv: kv[1]["ts"]):
        if r["status"] == "pending":
            r["status"] = "processing"
            r["ts"] = now
            job = {"id": rid, "type": r.get("type", "clip"),
                   "start": r["start"], "end": r["end"]}
            if r.get("ism"):
                job["ism"] = r["ism"]
            if r.get("type") == "kun":
                job["sana"] = r.get("sana")
                job["kanal"] = r.get("kanal", 1)
                job["nomi"] = r.get("nomi", "")
            return job
    return {}


@app.get("/agent/search_photo/{sid}")
def agent_search_photo(sid: str, x_secret: str = Header("", alias="X-Agent-Secret")):
    """Agent qidiruv rasmini yuklab oladi."""
    _auth_agent(x_secret)
    p = CLIPS / f"{sid}.query.jpg"
    if not p.exists():
        raise HTTPException(status_code=404, detail="rasm yo'q")
    return FileResponse(str(p), media_type="image/jpeg")


@app.post("/agent/search_result/{sid}")
async def agent_search_result(sid: str, request: Request,
                              x_secret: str = Header("", alias="X-Agent-Secret")):
    """Agent qidiruv natijasini (JSON + base64 rasmchalar) qaytaradi."""
    _auth_agent(x_secret)
    r = REQS.get(sid)
    if not r:
        raise HTTPException(status_code=404, detail="so'rov yo'q")
    body = await request.json()
    r["natija"] = body.get("natija", [])
    r["xabar"] = body.get("xabar")
    r["status"] = "ready"
    p = CLIPS / f"{sid}.query.jpg"      # so'rov rasmi endi kerak emas
    if p.exists():
        try:
            p.unlink()
        except OSError:
            pass
    return {"ok": True}


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
