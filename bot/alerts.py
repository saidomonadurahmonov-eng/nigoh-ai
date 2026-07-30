import queue
import threading

import cv2
import requests

API = "https://api.telegram.org/bot{token}/{method}"


class TelegramNotifier:
    """Alertlarni Telegramga yuboradi — alohida ipda, kadr tahlilini sekinlashtirmaydi.

    Token yoki chat_id bo'lmasa "quruq rejim": xabar konsolga chiqadi,
    rasm alert_N.jpg bo'lib saqlanadi — tizim baribir ishlayveradi.
    """

    def __init__(self, token=None, chat_id=None):
        self.token = (token or "").strip()
        self.chat_id = str(chat_id or "").strip()
        self.dry = not (self.token and self.chat_id)
        if self.dry:
            print("[telegram] token/chat_id yozilmagan - alertlar konsolga chiqadi",
                  flush=True)
        self._q = queue.Queue()
        threading.Thread(target=self._worker, daemon=True).start()

    def alert(self, text, frame=None):
        self._q.put((text, frame))

    def _worker(self):
        n = 0
        while True:
            text, frame = self._q.get()
            n += 1
            if self.dry:
                print(f"[telegram-quruq] {text}", flush=True)
                if frame is not None:
                    cv2.imwrite(f"alert_{n}.jpg", frame)
                continue
            try:
                if frame is not None:
                    ok, buf = cv2.imencode(".jpg", frame)
                    requests.post(
                        API.format(token=self.token, method="sendPhoto"),
                        data={"chat_id": self.chat_id, "caption": text},
                        files={"photo": ("kadr.jpg", buf.tobytes(), "image/jpeg")},
                        timeout=15)
                else:
                    requests.post(
                        API.format(token=self.token, method="sendMessage"),
                        data={"chat_id": self.chat_id, "text": text},
                        timeout=15)
            except requests.RequestException as e:
                print(f"[telegram] yuborilmadi: {e}", flush=True)
