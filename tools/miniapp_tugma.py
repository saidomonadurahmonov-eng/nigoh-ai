"""Bot menyu tugmasini Mini App'ni ochadigan qilib sozlaydi.

config.yaml da webapp_url (ochiq HTTPS manzil) to'ldirilgan bo'lishi kerak.
Ishga tushirish:  .venv\\Scripts\\python tools\\miniapp_tugma.py
Shundan keyin botdagi menyu (chapdagi tugma) Mini App'ni ochadi.
"""
import pathlib

import requests
import yaml

cfg = yaml.safe_load(
    open(pathlib.Path(__file__).resolve().parent.parent / "config.yaml",
         encoding="utf-8"))
token = (cfg.get("telegram") or {}).get("token", "").strip()
# Railway gibrid bo'lsa railway_url, aks holda webapp_url (tunnel)
url = (cfg.get("railway_url") or cfg.get("webapp_url") or "").strip()
if not token:
    raise SystemExit("config.yaml da telegram.token yo'q")
if not url.startswith("https://"):
    raise SystemExit("config.yaml da railway_url (yoki webapp_url) https:// to'ldiring")

r = requests.post(
    f"https://api.telegram.org/bot{token}/setChatMenuButton",
    json={"menu_button": {"type": "web_app", "text": "Kassa nazorati",
                          "web_app": {"url": url}}},
    timeout=15).json()
print("natija:", r.get("ok"), "|", r.get("description", "menyu tugmasi o'rnatildi"))
print("Endi botni oching — pastdagi/menyudagi 'Kassa nazorati' tugmasi Mini App'ni ochadi.")
