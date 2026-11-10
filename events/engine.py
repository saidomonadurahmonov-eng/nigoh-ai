class RuleEngine:
    """Strukturaviy qoidalar dvigateli — kod emas, config.yaml dagi sonlar
    bilan boshqariladi.

    Qoida namunasi:
      - name: navbat_uzun
        kamera: kassa        # qaysi kameraga (yozilmasa — hammasiga)
        metrika: navbat      # navbat | kutish | ichkarida | kadrda
        chegara: 4           # shu qiymatga yetsa yoki oshsa
        davomiylik: 60       # kamida shuncha soniya davom etsa
        cooldown: 600        # alertdan keyin shuncha soniya jim turadi
        xabar: "Navbat: {navbat} kishi"

    Uchta himoya spamdan saqlaydi: chegara + davomiylik + cooldown.
    """

    def __init__(self, rules):
        self.rules = rules or []
        self._since = {}
        self._last_fired = {}

    @staticmethod
    def _vaqt_mos(r, now):
        """Qoida faqat belgilangan soatlar oralig'ida ishlasin (masalan tunda)."""
        d, g = r.get("soat_dan"), r.get("soat_gacha")
        if d is None or g is None:
            return True
        import datetime as _dt
        soat = _dt.datetime.fromtimestamp(now).hour
        if d <= g:
            return d <= soat < g
        return soat >= d or soat < g      # yarim tundan o'tadigan oraliq

    def update(self, camera, metrics, now):
        fired = []
        for r in self.rules:
            if r.get("kamera") not in (None, camera):
                continue
            if not self._vaqt_mos(r, now):
                self._since.pop((r["name"], camera), None)
                continue
            key = (r["name"], camera)
            value = metrics.get(r.get("metrika", "navbat"), 0)
            if value >= r.get("chegara", 1):
                self._since.setdefault(key, now)
                davom = now - self._since[key]
                jim = now - self._last_fired.get(key, 0)
                if davom >= r.get("davomiylik", 0) and jim >= r.get("cooldown", 300):
                    self._last_fired[key] = now
                    text = r.get("xabar", "{kamera}: {navbat}").format(
                        kamera=camera, **metrics)
                    fired.append((r["name"], text))
            else:
                self._since.pop(key, None)
        return fired
