"""Kun tahlili — arxivdagi bitta sanani avtomatik ko'rib chiqib, "nima bo'lgan"ini
aniqlaydi.

Ishlash tartibi (ikki bosqich — bir kunni oqitib bo'lmagani uchun):
  1) QO'POL SKAN: kun bo'yi har `qadam` soniyada bitta kadr (odatda 5 daqiqa).
     Har kadrda odam/mashina aniqlanadi. ~12 soat / 5 daq = 144 kadr ≈ 4 daqiqa.
  2) ANIQLASHTIRISH: faqat harakat topilgan oraliqlar mayda qadam bilan
     (odatda 1 daqiqa) qayta olinadi — hodisa chegaralari aniq bo'lsin.

Natija — odam o'qiydigan xulosa: ochilish/yopilish, gavjum soat, mashina
kelishi, tungi harakat (xavfsizlik), va har hodisa uchun kadr + vaqt.
"""
import datetime as dt

PERSON = 0
TRANSPORT = {2: "mashina", 3: "mototsikl", 5: "avtobus", 7: "yuk mashina"}


def _aniqla(model, kadr, conf=0.35, imgsz=640):
    """Bitta kadrda odam va transport sonini qaytaradi."""
    r = model.predict(kadr, conf=conf, imgsz=imgsz, verbose=False,
                      classes=[PERSON] + list(TRANSPORT))[0]
    odam, transport = 0, {}
    for c in r.boxes.cls.tolist():
        c = int(c)
        if c == PERSON:
            odam += 1
        elif c in TRANSPORT:
            transport[TRANSPORT[c]] = transport.get(TRANSPORT[c], 0) + 1
    return odam, transport


def _bloklar(namunalar, uzilish):
    """Harakat bor namunalarni ketma-ket "bloklar"ga birlashtiradi.
    namunalar: [(vaqt, odam, transport, kadr), ...] tartibda."""
    bloklar, joriy = [], None
    for v, odam, tr, kadr in namunalar:
        bor = odam > 0 or bool(tr)
        if not bor:
            continue
        if joriy and (v - joriy["tugadi"]).total_seconds() <= uzilish:
            joriy["tugadi"] = v
            joriy["namuna"] += 1
            if odam > joriy["max_odam"]:
                joriy["max_odam"], joriy["kadr"] = odam, kadr
            for k, n in tr.items():
                joriy["transport"][k] = max(joriy["transport"].get(k, 0), n)
        else:
            if joriy:
                bloklar.append(joriy)
            joriy = {"boshlandi": v, "tugadi": v, "namuna": 1,
                     "max_odam": odam, "transport": dict(tr), "kadr": kadr}
    if joriy:
        bloklar.append(joriy)
    return bloklar


def tahlil(arxiv, model, channel, sana, boshlanish=7, tugash=22,
           qadam=300, aniq_qadam=60, tun_boshi=22, tun_oxiri=6,
           ishchi=4, holat=None):
    """Bitta kunni tahlil qiladi.

    boshlanish/tugash — kunning qaysi soatlari skanerlanadi (ish vaqti).
    Tun (tun_boshi..tun_oxiri) ham skanerlanadi, lekin qo'polroq qadam bilan —
    u yerda HAR QANDAY harakat muhim (xavfsizlik).
    """
    kun_boshi = dt.datetime.combine(sana, dt.time(0, 0))

    def skan(b, t, q, teg):
        if holat:
            holat(f"{teg}: {b:%H:%M}–{t:%H:%M} skanerlanmoqda…", 0, 0)
        kadrlar = arxiv.kadrlar(channel, b, t, q, ishchi=ishchi,
                                holat=(lambda d, j: holat(teg, d, j)) if holat else None)
        out = []
        for v, k in kadrlar:
            odam, tr = _aniqla(model, k)
            out.append((v, odam, tr, k))
        return out

    # --- 1-bosqich: ish vaqti qo'pol skan + tun ---
    ish_b = kun_boshi + dt.timedelta(hours=boshlanish)
    ish_t = kun_boshi + dt.timedelta(hours=tugash)
    namunalar = skan(ish_b, ish_t, qadam, "Kunduzi")

    tun = []
    if tun_boshi is not None:
        t1 = kun_boshi + dt.timedelta(hours=tun_boshi)
        t2 = kun_boshi + dt.timedelta(hours=24)
        tun += skan(t1, t2, qadam * 2, "Tun")
        t3 = kun_boshi
        t4 = kun_boshi + dt.timedelta(hours=tun_oxiri)
        tun += skan(t3, t4, qadam * 2, "Tun")

    # --- 2-bosqich: harakat topilgan joylarni aniqlashtirish ---
    xom_bloklar = _bloklar(sorted(namunalar, key=lambda x: x[0]), qadam * 2.5)
    aniq = list(namunalar)
    for b in xom_bloklar[:12]:          # eng ko'pi 12 blok — vaqtni cheklash uchun
        b1 = b["boshlandi"] - dt.timedelta(seconds=qadam)
        b2 = b["tugadi"] + dt.timedelta(seconds=qadam)
        aniq += skan(b1, b2, aniq_qadam, "Aniqlashtirish")

    hammasi = sorted({v: (v, o, t, k) for v, o, t, k in aniq}.values(), key=lambda x: x[0])
    bloklar = _bloklar(hammasi, aniq_qadam * 2.5)
    tun_bloklar = _bloklar(sorted(tun, key=lambda x: x[0]), qadam * 4)

    # --- Xulosa ---
    faol = [(v, o, t, k) for v, o, t, k in hammasi if o > 0]
    soatlik = {}
    for v, o, _, _ in hammasi:
        soatlik.setdefault(v.hour, []).append(o)
    soat_ort = {h: sum(v) / len(v) for h, v in soatlik.items() if v}
    gavjum = max(soat_ort.items(), key=lambda kv: kv[1]) if soat_ort else None

    transport_hodisa = []
    for b in bloklar:
        if b["transport"]:
            transport_hodisa.append(b)

    return {
        "sana": sana,
        "kanal": channel,
        "namuna": len(hammasi),
        "tun_namuna": len(tun),
        "birinchi": faol[0][0] if faol else None,
        "oxirgi": faol[-1][0] if faol else None,
        "eng_kop": max((o for _, o, _, _ in hammasi), default=0),
        "gavjum_soat": gavjum,
        "bloklar": bloklar,
        "transport": transport_hodisa,
        "tun_bloklar": tun_bloklar,
        "soatlik": soat_ort,
    }


def matn(n, kamera_nomi=""):
    """Tahlil natijasini odam o'qiydigan xulosaga aylantiradi (Telegram HTML)."""
    s = n["sana"].strftime("%d.%m.%Y")
    q = [f"📅 <b>{s}</b> — {kamera_nomi or 'kanal ' + str(n['kanal'])} tahlili", ""]

    if not n["birinchi"]:
        q.append("😴 Kun bo'yi hech qanday harakat topilmadi.")
    else:
        q.append(f"🌅 Birinchi harakat: <b>{n['birinchi']:%H:%M}</b>")
        q.append(f"🌆 Oxirgi harakat: <b>{n['oxirgi']:%H:%M}</b>")
        if n["gavjum_soat"]:
            h, o = n["gavjum_soat"]
            q.append(f"👥 Eng gavjum: <b>{h:02d}:00–{h+1:02d}:00</b> (o'rtacha {o:.1f} odam)")
        q.append(f"📈 Bir vaqtda eng ko'p: <b>{n['eng_kop']} odam</b>")
        q.append(f"🔢 Faoliyat oraliqlari: <b>{len(n['bloklar'])} ta</b>")

    if n["transport"]:
        q.append("")
        q.append("🚚 <b>Transport:</b>")
        for b in n["transport"][:6]:
            turlar = ", ".join(f"{k}" for k in b["transport"])
            q.append(f"   {b['boshlandi']:%H:%M} — {turlar}")

    q.append("")
    if n["tun_bloklar"]:
        q.append("🚨 <b>TUNDA HARAKAT ANIQLANDI:</b>")
        for b in n["tun_bloklar"][:6]:
            q.append(f"   ⚠️ {b['boshlandi']:%H:%M}–{b['tugadi']:%H:%M} "
                     f"({b['max_odam']} odam)")
    else:
        q.append("🌙 Tunda harakat yo'q — tinch.")

    q.append("")
    q.append(f"<i>{n['namuna']} kadr tekshirildi (kunduzi) + {n['tun_namuna']} (tun)</i>")
    return "\n".join(q)


def eng_muhim(n, soni=3):
    """Eng muhim lahzalar: tungi harakat > transport > eng gavjum blok."""
    tanlov = []
    for b in n["tun_bloklar"]:
        tanlov.append(("🚨 Tungi harakat", b))
    for b in n["transport"]:
        tanlov.append(("🚚 Transport", b))
    for b in sorted(n["bloklar"], key=lambda x: -x["max_odam"]):
        tanlov.append(("👥 Eng gavjum", b))
    natija, korilgan = [], set()
    for teg, b in tanlov:
        kalit = b["boshlandi"]
        if kalit in korilgan:
            continue
        korilgan.add(kalit)
        natija.append((teg, b))
        if len(natija) >= soni:
            break
    return natija
