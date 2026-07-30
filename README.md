# NIGOH AI — bor kameralarni analitikaga aylantiruvchi tizim
### Turning already-installed CCTV into business analytics

> **UZ:** O'zbekistondagi do'kon, ombor va sexlarda yuz minglab videokuzatuv kamerasi
> allaqachon o'rnatilgan va kechayu kunduz yozib turadi. Lekin ularning
> deyarli hammasi faqat "o'g'irlik bo'lsa orqaga qarab ko'rish" uchun ishlatiladi.
> NIGOH AI yangi qurilma sotib olishni talab qilmaydi — **bor NVR/kameralarga
> ulanib**, ularni real vaqtli biznes analitikasiga aylantiradi.
>
> **EN:** Hundreds of thousands of CCTV cameras are already installed and recording
> in shops, warehouses and workshops across Uzbekistan — yet almost all of them are
> used only to look backwards after a theft. NIGOH AI requires **no new hardware**:
> it connects to the existing NVR and turns those cameras into real-time business
> analytics.

---

## Nima qiladi / What it does

| | UZ | EN |
|---|---|---|
| 👥 | Kirdi/chiqdi sanash (virtual chiziq) | Entry/exit counting via a virtual line |
| ⏳ | Kassa navbati va kutish vaqti (poligon zona) | Checkout queue length and waiting time (polygon zone) |
| 🔔 | Qoida buzilganda darhol Telegram ogohlantirish | Instant Telegram alerts on rule breach |
| 📊 | Har kuni avtomatik hisobot (soatlik grafik) | Automatic daily report with hourly chart |
| 🎬 | So'rovga ko'ra dalil videosi kesib beriladi | On-demand evidence clip extraction |
| 📱 | Telegram Mini App — telefondan boshqarish | Telegram Mini App control from a phone |

## Arxitektura / Architecture

```
  Bor NVR (Hikvision)          Obyekt kompyuteri (edge)                Bulut
 ┌────────────────────┐      ┌──────────────────────────────┐      ┌──────────────┐
 │ 9 × IP kamera      │      │ ISAPI JPEG polling           │      │ Mini App     │
 │ DS-7616NI-Q2       │─────▶│ YOLO11n  →  ByteTrack        │      │ (FastAPI)    │
 │                    │ HTTP │ LineZone / PolygonZone       │      │ so'rov       │
 └────────────────────┘digest│ qoida dvigateli (rules)      │      │ navbati      │
                             │ SQLite (metrics + events)    │◀────▶│              │
                             │ dalil arxivi (JPEG)          │ agent└──────────────┘
                             └──────────────────────────────┘ (faqat tashqariga)
```

**Muhim dizayn qarorlari / Key design decisions**

1. **RTSP tashlab yuborildi.** Bu obyektda RTSP dekod (OpenCV/FFmpeg) H.265 va
   H.264 da ham yashil kadr berardi — parametr to'plami qo'llanmasdi. Yechim:
   NVR'ning **ISAPI JPEG snapshot** interfeysi (`/ISAPI/Streaming/channels/<ch>02/picture`,
   digest auth). 9/9 kamera toza ishladi. → `vision/stream.py`
   *(EN: RTSP decoding produced green frames on this NVR for both H.265 and H.264;
   we switched to the NVR's own ISAPI JPEG snapshot endpoint. All 9 channels worked.)*
2. **Edge-first.** Tahlil obyektning o'z kompyuterida bo'ladi. Video internetga
   chiqmaydi — faqat raqamlar va hodisalar. Ish stoli internetga **ochilmaydi**:
   agent faqat o'zi tashqariga ulanadi (`bot/agent.py`), ya'ni NAT ortida
   port ochish shart emas.
3. **Maxfiylik.** Video doimiy saqlanmaydi, yuz tanish yo'q, faqat agregat
   raqamlar. Dalil videosi **faqat ega so'raganda** kesiladi va "Ish bitdi"
   bosilganda o'chiriladi. → `storage/evidence.py`
4. **Arzon.** Model — YOLO11n (eng kichik), CPU'da ~9.6 FPS. Har kadr uchun
   tashqi API to'lovi yo'q. Mijozning mini-PC'si (~$150–200) yetadi.

## Kod xaritasi / Code map

| Fayl | Vazifa |
|---|---|
| `vision/detector.py` | YOLO11n + ByteTrack — odam aniqlash va barqaror ID |
| `vision/stream.py` | `ISAPIFrameSource` (NVR JPEG polling) + RTSP/fayl manbasi |
| `vision/zones.py` | Virtual chiziq (kirdi/chiqdi) va poligon zona (navbat) |
| `events/engine.py` | Qoida dvigateli: chegara + davomiylik + cooldown |
| `storage/db.py` | SQLite — daqiqalik `metrics`, `events` |
| `storage/evidence.py` | Kadr arxivi, sessiyalarga bo'lish, ffmpeg H.264 klip |
| `bot/commands.py` | `/holat /bugun /hafta /kassa /kamchiqdi` |
| `bot/alerts.py` | Telegram ogohlantirish (tokensiz quruq-rejim ham bor) |
| `bot/agent.py` | Bulut ↔ obyekt ko'prigi (faqat chiquvchi ulanish) |
| `report/daily.py` | Kunlik hisobot + matplotlib soatlik grafik |
| `webapp/server.py` | Lokal Mini App API (Telegram initData HMAC auth) |
| `railway_app/` | Bulutdagi Mini App + so'rov navbati |

## Holati / Status

Tizim **jonli ishlab turgan** MVP: ulgurji savdo obyektida, 9 kamerali
Hikvision NVR'ga ulangan, obyekt kompyuterida avtostart bilan 24/7 ishlaydi.
Kirdi/chiqdi sanash, kassa navbati qoidasi, kunlik hisobot, Telegram buyruqlar
va Mini App orqali dalil videosi kesish — hammasi jonli sinovdan o'tgan.

*(EN: A live MVP running 24/7 at a wholesale trading site on a 9-camera Hikvision
NVR, with autostart on the on-site PC. Entry/exit counting, queue rule, daily
reports, Telegram commands and on-demand evidence clips are all verified live.)*

**Halol chegaralar / Honest limitations.** Aniqlash modeli — tayyor, oldindan
o'qitilgan YOLO11n (o'z datasetimizda o'qitilgan model hozircha yo'q). Bizning
qiymatimiz — obyektga ulanish qatlami, domen qoidalari, dalil zanjiri va edge
deploy. Keyingi bosqich: o'z ma'lumotlarimizda o'qitilgan xatti-harakat modellari
(navbat dinamikasi, kassa oldidagi anomaliyalar) va ko'p obyektli boshqaruv paneli.

## Ishga tushirish / Quick start

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy config.example.yaml config.yaml     # o'z qiymatlaringizni yozing
```

Kamerasiz sinov / test without cameras:

```bash
.venv\Scripts\python tools\make_test_video.py
.venv\Scripts\python main.py --save natija.mp4
```

Haqiqiy NVR bilan / with a real NVR:

```bash
.venv\Scripts\python main.py --tekshir      # har kanaldan surat (koordinata sozlash)
.venv\Scripts\python main.py                # to'liq ishga tushirish
```

> ⚠️ `numpy < 2.4` shart — numpy 2.5 da 2D `np.cross` olib tashlangan va
> `supervision` 0.29 `LineZone` buziladi.

## Litsenziya va maxfiylik / License & privacy

Bu repozitoriya tanlov hakamlari uchun kod namunasi sifatida ochilgan.
Ichida **hech qanday parol, token yoki obyekt tasviri yo'q** — jonli
`config.yaml`, ma'lumotlar bazasi va kadr arxivi `.gitignore` orqali
chiqarib tashlangan. Obyekt egasining kamera ma'lumotlari maxfiy.
