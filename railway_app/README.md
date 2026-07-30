# Kassa nazorati — Railway ilovasi (gibrid Mini App)

Bu papka Railway'ga deploy qilinadi. Mini App'ni ko'rsatadi va do'kon
kompyuteri (agent) bilan video so'rovlarini almashadi.

Video FAQAT so'ralganda, agent tomonidan yuklanadi va "Ish bitdi"da o'chadi.
Jonli video va arxiv do'kon kompyuterida qoladi — bu yerga kelmaydi.

## Deploy (Railway)

1. Shu `railway_app` papkasini alohida GitHub repo qiling (yoki Railway'da
   root papka sifatida shuni ko'rsating).
2. Railway'da yangi loyiha → GitHub repodan deploy. Railway Python'ni o'zi
   aniqlaydi, `Procfile` bilan ishga tushadi.
3. Railway → Variables (ENV) ga qo'ying:
   - `BOT_TOKEN`   = botning tokeni
   - `OWNER_ID`    = egasining Telegram chat_id (masalan 123456789)
   - `AGENT_SECRET`= do'kon config.yaml dagi `agent_secret` bilan BIR XIL
4. Deploy tugagach Railway bergan manzilni (https://...up.railway.app) oling.

## Do'kon kompyuterida (bir marta)

`config.yaml` ga yozing:
```yaml
railway_url: "https://SIZNING.up.railway.app"
agent_secret: "Railway'dagi AGENT_SECRET bilan bir xil"
```
Keyin bot menyu tugmasini o'rnating:
```
.venv\Scripts\python tools\miniapp_tugma.py
```
Tizimni qayta ishga tushiring (yoki avtostart o'zi ko'taradi).

## Tekshirish

- Botni oching → menyudagi "Kassa nazorati" tugmasi Mini App'ni ochadi.
- Yuqorida "● onlayn" bo'lsa — agent ulangan.
- Hodisadagi "Ko'rish" yoki vaqt tanlab "Kes va ko'r" → video keladi →
  "Ish bitdi" bosilsa o'chadi.
