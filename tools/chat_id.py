"""chat_id ni aniqlash. Tartib:
1) config.yaml dagi telegram.token ga @BotFather bergan tokenni yozing
2) Telegramda botingizga /start deb yozing (yoki botni guruhga qo'shib xabar yozing)
3) .venv\\Scripts\\python tools\\chat_id.py
Chiqqan raqamni config.yaml dagi telegram.chat_id ga yozing.
"""
import pathlib

import requests
import yaml

cfg_path = pathlib.Path(__file__).resolve().parent.parent / "config.yaml"
cfg = yaml.safe_load(open(cfg_path, encoding="utf-8"))
token = ((cfg.get("telegram") or {}).get("token") or "").strip()
if not token:
    raise SystemExit("Avval config.yaml dagi telegram.token ni to'ldiring")

r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=15).json()
if not r.get("ok"):
    raise SystemExit(f"Token xato ko'rinadi: {r.get('description')}")

chats = {}
for u in r.get("result", []):
    msg = u.get("message") or u.get("channel_post") or {}
    chat = msg.get("chat")
    if chat:
        chats[chat["id"]] = chat.get("title") or chat.get("first_name") or "?"

if not chats:
    print("Xabar topilmadi. Telegramda botga /start deb yozib, qayta ishga tushiring.")
for cid, nomi in chats.items():
    print(f"chat_id: {cid}   ({nomi})")
