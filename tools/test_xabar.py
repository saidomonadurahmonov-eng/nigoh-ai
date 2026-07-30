"""Telegram ulanishini tekshirish: config dagi token/chat_id ga sinov xabari."""
import pathlib

import requests
import yaml

cfg = yaml.safe_load(
    open(pathlib.Path(__file__).resolve().parent.parent / "config.yaml",
         encoding="utf-8"))
c = cfg["telegram"]
r = requests.post(
    f"https://api.telegram.org/bot{c['token']}/sendMessage",
    data={"chat_id": c["chat_id"],
          "text": "Video analitika tizimi ulandi. Bu sinov xabari — "
                  "alertlar shu yerga keladi."},
    timeout=15).json()
print("yuborildi:", r.get("ok"), "| xato:", r.get("description"))
