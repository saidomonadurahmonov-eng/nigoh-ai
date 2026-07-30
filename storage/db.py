import sqlite3
import threading


class Database:
    """SQLite ombori — faqat agregat raqamlar va hodisalar, video saqlanmaydi.

    metrics: har daqiqaga bitta qator (kirdi/chiqdi shu daqiqadagi delta,
    navbat/kutish shu daqiqadagi maksimum).
    events: alertlar tarixi.
    """

    def __init__(self, path="analitika.db"):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS metrics ("
            " ts INTEGER NOT NULL,"
            " camera TEXT NOT NULL,"
            " kirdi INTEGER NOT NULL,"
            " chiqdi INTEGER NOT NULL,"
            " navbat_max INTEGER NOT NULL,"
            " kutish_max REAL NOT NULL,"
            " PRIMARY KEY (ts, camera))")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS events ("
            " ts INTEGER NOT NULL,"
            " camera TEXT NOT NULL,"
            " rule TEXT NOT NULL,"
            " message TEXT NOT NULL)")
        self._conn.commit()

    def yoz_metrika(self, ts, camera, kirdi, chiqdi, navbat_max, kutish_max):
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO metrics VALUES (?,?,?,?,?,?)",
                (int(ts), camera, int(kirdi), int(chiqdi),
                 int(navbat_max), round(float(kutish_max), 1)))
            self._conn.commit()

    def yoz_hodisa(self, ts, camera, rule, message):
        with self._lock:
            self._conn.execute(
                "INSERT INTO events VALUES (?,?,?,?)",
                (int(ts), camera, rule, message))
            self._conn.commit()

    def _q(self, sql, args=()):
        with self._lock:
            return self._conn.execute(sql, args).fetchall()

    def hisobot(self, start_ts, end_ts):
        """[start,end] oralig'i uchun har kamera bo'yicha jami: kirdi, chiqdi,
        eng ko'p navbat, eng uzoq kutish, va eng gavjum soat."""
        rows = self._q(
            "SELECT camera, SUM(kirdi), SUM(chiqdi), MAX(navbat_max), "
            "MAX(kutish_max) FROM metrics WHERE ts>=? AND ts<? GROUP BY camera",
            (int(start_ts), int(end_ts)))
        out = {}
        for cam, kirdi, chiqdi, nmax, kmax in rows:
            hh = self._q(
                "SELECT CAST((ts%86400)/3600 AS INT) h, SUM(kirdi) s FROM metrics "
                "WHERE ts>=? AND ts<? AND camera=? GROUP BY h ORDER BY s DESC LIMIT 1",
                (int(start_ts), int(end_ts), cam))
            out[cam] = {
                "kirdi": kirdi or 0, "chiqdi": chiqdi or 0,
                "navbat_max": nmax or 0, "kutish_max": kmax or 0,
                "pik_soat": hh[0][0] if hh else None,
            }
        return out

    def soatlik(self, camera, start_ts, end_ts):
        """Soatlik kirdi (grafik uchun): {soat: kirdi}."""
        rows = self._q(
            "SELECT CAST((ts%86400)/3600 AS INT) h, SUM(kirdi) FROM metrics "
            "WHERE ts>=? AND ts<? AND camera=? GROUP BY h",
            (int(start_ts), int(end_ts), camera))
        return {h: s or 0 for h, s in rows}

    def kassa_faoliyat(self, camera, start_ts, end_ts):
        """Oralиqda kassada odam bo'lgan daqiqalar: [(ts, navbat, kutish), ...]."""
        return self._q(
            "SELECT ts, navbat_max, kutish_max FROM metrics WHERE ts>=? AND ts<? "
            "AND camera=? AND navbat_max>0 ORDER BY ts",
            (int(start_ts), int(end_ts), camera))
