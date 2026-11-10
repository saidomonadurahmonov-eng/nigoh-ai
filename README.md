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
| 🔎 | Rasm bo'yicha odam qidirish (tashqi ko'rinish "barmoq izi") | Find a person across cameras from a photo (appearance re-ID) |
| 🪪 | Hodimni yuzidan tanish, davomat, kassada "notanish" | Staff face ID, attendance, "stranger at the till" |
| 📅 | O'tgan kun tahlili — to'g'ridan-to'g'ri NVR arxividan | Past-day analysis straight from the NVR archive |
| 📱 | Telegram Mini App — telefondan boshqarish | Telegram Mini App control from a phone |

## Ikki xil ishlatish / Two ways to run it

**1. Yakka obyekt — o'z botingiz bilan.** `config.yaml` ga NVR va Telegram bot
ma'lumotini yozasiz, `python main.py`. Alertlar, buyruqlar (`/holat /bugun
/hafta /kassa /kun`), kunlik hisobot va lokal Mini App shu kompyuterda ishlaydi.
Telefondan internet orqali ochish uchun `railway_app/` ni o'z serveringizga
qo'yasiz — obyekt kompyuteri baribir internetga ochilmaydi.

**2. Qurilma rejimi — o'rnatuvchi bilan.** `qurilma.py` kompyuterni bulutga
"ulash kodi" orqali bog'laydi, NVR'ni tarmoqdan o'zi topadi, sozlamani bulutdan
oladi va `main.py` ni boshqaradi. `tools/paket_yasa.py` obyektga olib boriladigan
zip-o'rnatuvchini yig'adi (`ornatuvchi/` — mijoz bitta `.bat` ni bosadi).
Bulut serverining o'zi bu repozitoriyada **yo'q**: qurilma gaplashadigan API
`qurilma.py` va `bot/agent.py` da ochiq ko'rinib turibdi, manzil `bulut.txt`
orqali beriladi. Standart manzil yo'q — dastur o'zidan hech qayerga ulanmaydi.

*(EN: Run it stand-alone with your own Telegram bot and `config.yaml`, or in
"device mode": `qurilma.py` pairs the PC with a cloud panel via a pairing code,
discovers the NVR and supervises `main.py`. The cloud server is not part of this
repository; the device-side API is visible in `qurilma.py` / `bot/agent.py`.
There is no default server — nothing phones home.)*

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
3. **Maxfiylik.** Video doimiy saqlanmaydi. Dalil videosi **faqat ega
   so'raganda** kesiladi va "Ish bitdi" bosilganda o'chiriladi
   (`storage/evidence.py`). Odam qidiruvi yoqilgan bo'lsa, kadrdagi har odamning
   kichik kesma surati va ko'rinish vektori **obyekt kompyuterida** 14 kun
   saqlanadi; yuz bo'yicha tanish faqat siz ro'yxatga kiritgan hodimlar bilan
   solishtiradi. Ikkalasini ham o'chirib qo'yish mumkin: `odam_indeks: false`,
   `hodim_yuz: false`.
4. **Arzon.** Model — YOLO11n (eng kichik), CPU'da ~9.6 FPS. Har kadr uchun
   tashqi API to'lovi yo'q. Mijozning mini-PC'si (~$150–200) yetadi.
5. **Koordinata kadr o'lchamiga bog'liq emas.** Chiziq va zona nisbiy (0..1)
   koordinatada berilishi mumkin — surat va tahlil kadri turli o'lchamda bo'lsa
   ham chiziq siljimaydi. Eski piksel koordinatalar ham ishlayveradi.

## Alert profillari / Alert profiles

Har obyektning shovqini har xil: sokin omborda har harakat — hodisa, gavjum
do'konda esa bu kuniga yuzlab keraksiz xabar. Qurilma rejimida bulut profilni
tanlaydi (`qurilma.py: qoidalar_yasa`):

| Profil | Qachon | Nima xabar beradi |
|---|---|---|
| `ombor` | sokin joy: ombor, ofis | kirishda odam, har kamerada harakat, kassada notanish, tungi harakat |
| `dokon` | gavjum savdo zali | faqat ish soatidan tashqari harakat va uzun navbat |
| `jim` | birinchi kunlar, kuzatish | hech narsa (faqat "kamera uzildi") |

Kamera vazifasi ham ta'sir qiladi: `kocha` — ko'chaga qaragan kamera, harakat
xabari berilmaydi; `tahlilsiz` — faqat jonli ko'rish, tahlilga qo'shilmaydi
(protsessorni tejaydi). Yakka rejimda qoidalarni `config.yaml` da o'zingiz yozasiz.

## Kod xaritasi / Code map

| Fayl | Vazifa |
|---|---|
| `main.py` | Tahlil dvigateli: har kamera uchun ip, qoidalar, hisobot, agent |
| `qurilma.py` | Qurilma rejimi: ulash kodi, NVR'ni topish, sozlama, `main.py` nazorati |
| `vision/detector.py` | YOLO11n + ByteTrack — odam aniqlash va barqaror ID |
| `vision/stream.py` | `ISAPIFrameSource` (NVR JPEG polling) + RTSP/fayl manbasi |
| `vision/zones.py` | Virtual chiziq (kirdi/chiqdi) va poligon zona (navbat) |
| `vision/reid.py` | Tashqi ko'rinish "barmoq izi": HSV histogramma + MobileNetV3 |
| `vision/face.py` | Yuz aniqlash va tanish: OpenCV YuNet + SFace |
| `events/engine.py` | Qoida dvigateli: chegara + davomiylik + cooldown + soat oynasi |
| `storage/db.py` | SQLite — daqiqalik `metrics`, `events` |
| `storage/evidence.py` | Kadr arxivi, sessiyalarga bo'lish, ffmpeg H.264 klip |
| `storage/person_index.py` | Odamlar indeksi va rasm bo'yicha qidiruv |
| `storage/employees.py` | Hodimlar ro'yxati (yuz namunasi bilan) |
| `nvr/arxiv.py` | NVR arxividan kadr va klip olish (RTSP playback) |
| `analysis/kun.py` | O'tgan kun tahlili: ikki bosqichli skan |
| `bot/commands.py` | `/holat /bugun /hafta /kassa /kamchiqdi /kun` |
| `bot/alerts.py` | Telegram ogohlantirish (tokensiz quruq-rejim ham bor) |
| `bot/agent.py` | Bulut ↔ obyekt ko'prigi (faqat chiquvchi ulanish) |
| `report/daily.py` | Kunlik hisobot + matplotlib soatlik grafik |
| `webapp/server.py` | Lokal Mini App API (Telegram initData HMAC auth) |
| `railway_app/` | Yakka obyekt uchun bulutdagi Mini App + so'rov navbati |
| `ornatuvchi/` | Windows o'rnatuvchi: Python, kutubxonalar, avtostart, ulash kodi |
| `tools/paket_yasa.py` | O'rnatuvchi zip-paketini yig'ish (kod + manzil + modellar) |
| `tools/modellar_yukla.py` | Modellarni oldindan yuklab olish (internetsiz o'rnatish uchun) |
| `tests/test_tuzatishlar.py` | Tarmoqsiz sinovlar (ruxsat, koordinata, profillar) |

## Ishga tushirish / Quick start

Python 3.12 (Windows'da sinalgan). Kutubxona versiyalari `requirements.txt` da
ataylab qotirilgan.

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

Sinovlar / tests:

```bash
.venv\Scripts\python tests\test_tuzatishlar.py            # tez, tarmoqsiz
.venv\Scripts\python tests\test_tuzatishlar.py --video    # + sinov videosida to'liq yurgizish
```

O'rnatuvchi paket (qurilma rejimi) / installer package:

```bash
.venv\Scripts\python tools\modellar_yukla.py
.venv\Scripts\python tools\paket_yasa.py --bulut https://sizning-serveringiz --bot Sizning_bot
```

## Xavfsizlik eslatmalari / Security notes

- `config.yaml` va `qurilma.json` ichida NVR paroli va tokenlar **ochiq matnda**
  turadi. Ularni hech qachon git'ga qo'shmang (`.gitignore` da bor) va obyekt
  kompyuteriga kirishni cheklang.
- Lokal Mini App serveri faqat Telegram tokeni va egasi sozlangan bo'lsa ishga
  tushadi; `webapp_dev: true` da u faqat `127.0.0.1` da ochiladi.
- NVR uchun alohida, huquqi cheklangan foydalanuvchi oching — `admin` parolini
  bermang.
- Kamera ostidagi odamlarni xabardor qilish va shaxsga doir ma'lumotlar
  to'g'risidagi qonunlarga rioya qilish — tizimni o'rnatgan tomonning mas'uliyati.

## Holati / Status

Tizim jonli obyektda sinovdan o'tgan: ulgurji savdo obyekti, 9 kamerali
Hikvision NVR, obyekt kompyuterida avtostart bilan 24/7. Kirdi/chiqdi sanash,
navbat qoidasi, kunlik hisobot, Telegram buyruqlar, dalil videosi, rasm bo'yicha
qidiruv va kun tahlili — hammasi shu obyektda tekshirilgan.

*(EN: Verified on a live site — a wholesale trading floor with a 9-camera
Hikvision NVR, running 24/7 with autostart on the on-site PC.)*

**Halol chegaralar / Honest limitations.**
- Aniqlash modeli — tayyor, oldindan o'qitilgan YOLO11n; o'z ma'lumotimizda
  o'qitilgan model hozircha yo'q.
- Faqat Hikvision (va shu ISAPI'ni qo'llaydigan) videoyozgichlar bilan sinalgan.
- Har kamera o'z model nusxasini ishlatadi — oddiy CPU'da bir vaqtda tahlil
  qilinadigan kameralar soni cheklangan (9 ta sinalgan). Ko'p kamerali obyektda
  keraksizlarini `tahlilsiz` qiling.
- Ekrandagi odam tasviri (televizor, plakat) ham "odam" bo'lib sanalishi mumkin.

## Litsenziya / License

Kod **GNU AGPL-3.0** litsenziyasi ostida — [LICENSE](LICENSE). Sababi: tizim
[Ultralytics YOLO](https://github.com/ultralytics/ultralytics) ga tayanadi, u
ham AGPL-3.0.

Amalda bu nimani anglatadi: foydalanish, o'rganish, o'zgartirish va tarqatish
mumkin. Lekin o'zgartirilgan versiyani boshqalarga bersangiz yoki tarmoq orqali
xizmat sifatida ko'rsatsangiz — uning manba kodini ham shu litsenziya bilan
ochishingiz kerak. Yopiq tijoriy mahsulot ichiga qo'shish uchun Ultralytics'dan
alohida litsenziya kerak bo'ladi. Bu yuridik maslahat emas.

Model fayllari repozitoriyada yo'q va har birining o'z litsenziyasi bor:
YOLO11n — Ultralytics (AGPL-3.0); YuNet va SFace — OpenCV Zoo; MobileNetV3 —
torchvision. Dastur hech qanday kafolatsiz beriladi.

Repozitoriyada **hech qanday parol, token yoki obyekt tasviri yo'q** — jonli
`config.yaml`, ma'lumotlar bazasi, kadr arxivi va yuz namunalari `.gitignore`
orqali chiqarib tashlangan.

*(EN: Licensed under GNU AGPL-3.0 because it builds on Ultralytics YOLO. You may
use, modify and redistribute it; if you distribute a modified version or offer
it as a network service you must publish its source under the same licence.
Model weights are not included and carry their own licences. No warranty.)*
