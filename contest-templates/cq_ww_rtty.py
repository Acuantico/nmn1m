TEMPLATE_ID = "cq_ww_rtty"
TEMPLATE_NAME = "CQ WW RTTY"
LOG_KIND = "ham"
IS_CONTEST = True
DEFAULT_CONTEST_TEXT = "CQ-WW-RTTY"
ALLOW_CABRILLO = True

FORM_FIELDS = [
    {"key": "call", "label": "Call", "default": "", "required": True, "width": 26},
    {"key": "rst_sent", "label": "RST enviado", "default": "599", "required": True, "width": 26},
    {
        "key": "exchange_sent",
        "label": "Zona CQ enviada",
        "default": "14",
        "required": True,
        "width": 26,
    },
    {"key": "rst_recv", "label": "RST recibido", "default": "599", "required": True, "width": 26},
    {
        "key": "exchange_recv",
        "label": "Zona CQ recibida",
        "default": "",
        "required": True,
        "width": 26,
    },
    {
        "key": "qth_recv",
        "label": "QTH EE.UU./Canadá (solo si aplica)",
        "default": "",
        "required": False,
        "width": 26,
    },
    {"key": "notes", "label": "Notas", "default": "", "required": False, "width": 26},
]

TREE_COLUMNS = [
    ("utc", "UTC", 140),
    ("call", "Call", 100),
    ("band", "Banda", 70),
    ("mode", "Modo", 70),
    ("freq", "Freq Hz", 100),
    ("rst_sent", "RST Tx", 70),
    ("exchange_sent", "Zona Tx", 90),
    ("rst_recv", "RST Rx", 70),
    ("exchange_recv", "Zona Rx", 90),
    ("qth_recv", "QTH US/VE", 90),
    ("notes", "Notas", 220),
]


def _clean_exchange(raw: str) -> str:
    text = str(raw or "").strip().upper()
    if not text:
        raise ValueError("La zona CQ es obligatoria")
    return text


def build_qso(ctx: dict) -> dict:
    get = ctx["get"]
    call = str(get("call") or "").strip().upper()
    if not call:
        raise ValueError("El indicativo es obligatorio")

    rst_sent = str(get("rst_sent") or "599").strip() or "599"
    rst_recv = str(get("rst_recv") or "599").strip() or "599"
    exchange_sent = _clean_exchange(get("exchange_sent"))
    exchange_recv = _clean_exchange(get("exchange_recv"))
    # Solo lo mandan estaciones de EE.UU./Canadá (regla CQ WW RTTY); para el
    # resto del mundo el intercambio es solo RST + zona, así que se deja
    # vacío sin más.
    qth_recv = str(get("qth_recv") or "").strip().upper()

    return {
        "timestamp_utc": str(ctx["timestamp_utc"]),
        "call": call,
        "band": str(ctx["band"]),
        "mode": str(ctx["mode"]),
        "freq_hz": int(ctx["freq_hz"]),
        "rst_sent": rst_sent,
        "exchange_sent": exchange_sent,
        "rst_recv": rst_recv,
        "exchange_recv": exchange_recv,
        "qth_recv": qth_recv,
        "notes": str(get("notes") or "").strip(),
    }


def row_values(qso: dict) -> tuple:
    return (
        qso.get("timestamp_utc", ""),
        qso.get("call", ""),
        qso.get("band", ""),
        qso.get("mode", ""),
        qso.get("freq_hz", 0),
        qso.get("rst_sent", ""),
        qso.get("exchange_sent", ""),
        qso.get("rst_recv", ""),
        qso.get("exchange_recv", ""),
        qso.get("qth_recv", ""),
        qso.get("notes", ""),
    )


def adif_fields(qso: dict, station: dict) -> dict:
    dt = qso["timestamp_utc"]
    date = dt[0:10].replace("-", "")
    time_on = dt[11:19].replace(":", "")
    out = {
        "CALL": qso.get("call", ""),
        "QSO_DATE": date,
        "TIME_ON": time_on,
        "BAND": str(qso.get("band", "")).replace("m", "M"),
        "MODE": "RTTY",
        "FREQ": f"{float(qso.get('freq_hz', 0)) / 1_000_000:.6f}",
        "RST_SENT": qso.get("rst_sent", ""),
        "RST_RCVD": qso.get("rst_recv", ""),
        "STX_STRING": qso.get("exchange_sent", ""),
        "SRX_STRING": qso.get("exchange_recv", ""),
        "CONTEST_ID": station.get("contest", DEFAULT_CONTEST_TEXT),
        "OPERATOR": station.get("operator", ""),
        "MY_GRIDSQUARE": station.get("my_grid", ""),
        "COMMENT": qso.get("notes", ""),
    }
    if str(qso.get("exchange_sent", "")).isdigit():
        out["STX"] = qso.get("exchange_sent", "")
    if str(qso.get("exchange_recv", "")).isdigit():
        out["SRX"] = qso.get("exchange_recv", "")
    if qso.get("qth_recv"):
        out["STATE"] = qso.get("qth_recv", "")
    return out


def cabrillo_header(station: dict) -> list[str]:
    call = str(station.get("operator") or "EA0XXX").strip().upper() or "EA0XXX"
    contest = str(station.get("contest") or DEFAULT_CONTEST_TEXT).strip().upper() or DEFAULT_CONTEST_TEXT
    return [
        "START-OF-LOG: 3.0",
        f"CALLSIGN: {call}",
        f"CONTEST: {contest}",
        "CATEGORY-OPERATOR: SINGLE-OP",
        "CATEGORY-BAND: ALL",
        "CATEGORY-MODE: RTTY",
        "CATEGORY-TRANSMITTER: ONE",
        "CATEGORY-POWER: HIGH",
        f"GRID-LOCATOR: {station.get('my_grid', '')}",
        f"OPERATORS: {call}",
        f"NAME: {call}",
        "CLAIMED-SCORE: 0",
    ]


def cabrillo_qso_line(qso: dict, station: dict) -> str:
    dt = qso["timestamp_utc"]
    freq_khz = int(round(float(qso.get("freq_hz", 0)) / 1000.0))
    our_call = str(station.get("operator") or "EA0XXX").strip().upper() or "EA0XXX"
    # CQ WW RTTY es siempre modo RTTY: en Cabrillo eso es "RY", no CW/PH.
    mode = "RY"
    # Solo EE.UU./Canadá añaden el QTH al intercambio ("599 05 MA"), pero el
    # robot de cqwwrtty.com exige SIEMPRE el campo QTH en el Cabrillo, tanto
    # enviado como recibido: el resto del mundo va como "DX" ("599 14 DX").
    qth_sent = str(station.get("qth") or "").strip().upper() or "DX"
    qth_recv = str(qso.get("qth_recv", "")).strip().upper() or "DX"
    return (
        f"QSO: {freq_khz:>5} {mode:<2} {dt[0:10]} {dt[11:16].replace(':', '')} "
        f"{our_call:<13} {str(qso.get('rst_sent', '')):<3} {str(qso.get('exchange_sent', '')):>2} {qth_sent:<2} "
        f"{str(qso.get('call', '')):<13} {str(qso.get('rst_recv', '')):<3} {str(qso.get('exchange_recv', '')):>2} {qth_recv}"
    )


# --------------------------------------------------------------------------- #
# Puntuación según las reglas (https://cqwwrtty.com/rules.htm)
# --------------------------------------------------------------------------- #
# Multiplicadores POR BANDA: cada zona CQ distinta, cada país distinto (DXCC +
# WAE: p. ej. Sicilia cuenta aparte de Italia) y cada estado de EE.UU.
# continental (48 + DC) / área de Canadá (14). Puntos por QSO: 3 con otro
# continente, 2 mismo continente y otro país, 1 mismo país. Duplicados (misma
# estación en la misma banda) no cuentan. Total = puntos x multiplicadores.
#
# Antes el libro contaba "prefijos distintos" (hasta la primera cifra) de todo
# el log sin separar bandas -- una regla de estilo WPX que no tiene nada que
# ver con el CQ WW RTTY.

US_QTHS = frozenset(
    "AL AZ AR CA CO CT DE DC FL GA ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ "
    "NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
)
#: Áreas de Canadá (14); NF es la abreviatura antigua de Terranova (NL).
CANADA_QTHS = frozenset("NB NS PE QC ON MB SK AB BC NT NU YT NL LB".split())
_QTH_ALIASES = {"NF": "NL", "PQ": "QC", "NWT": "NT"}
_IGNORED_SUFFIXES = frozenset({"P", "M", "MM", "AM", "QRP", "A", "B", "LH"})

_CTY_CACHE: dict[str, tuple[dict, dict]] = {}


def _load_cty(path: str) -> tuple[dict, dict]:
    """cty.csv (country-files.com) -> (prefijos, indicativos exactos), cada
    uno -> (país, continente, zona CQ), con las correcciones por prefijo
    "(zona)" y "{continente}"."""
    cached = _CTY_CACHE.get(path)
    if cached is not None:
        return cached
    import re

    prefixes: dict[str, tuple[str, str, int]] = {}
    exact: dict[str, tuple[str, str, int]] = {}
    token_re = re.compile(r"^(=?)([A-Z0-9/]+)(.*)$")
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            fields = line.strip().split(",")
            if len(fields) < 10:
                continue
            country = fields[1].strip()
            continent = fields[3].strip()
            try:
                zone = int(fields[4])
            except ValueError:
                continue
            for token in fields[9].rstrip(";").split():
                m = token_re.match(token.strip())
                if not m:
                    continue
                is_exact, key, extras = m.group(1), m.group(2), m.group(3)
                zm = re.search(r"\((\d+)\)", extras)
                cm = re.search(r"\{(\w+)\}", extras)
                info = (country, cm.group(1) if cm else continent, int(zm.group(1)) if zm else zone)
                (exact if is_exact else prefixes)[key] = info
    _CTY_CACHE[path] = (prefixes, exact)
    return prefixes, exact


def country_info(call: str, cty_path: str) -> tuple[str, str, int] | None:
    """(país, continente, zona CQ) de un indicativo, o None si no se sabe."""
    prefixes, exact = _load_cty(cty_path)
    call = str(call or "").strip().upper()
    if not call:
        return None
    if call in exact:
        return exact[call]
    parts = [p for p in call.split("/") if p and p not in _IGNORED_SUFFIXES and not p.isdigit()]
    if not parts:
        return None
    # "EA8/K1ABC" o "K1ABC/EA8": manda la parte corta (el prefijo de destino).
    base = min(parts, key=len) if len(parts) > 1 and len(min(parts, key=len)) <= 4 else parts[0]
    if base in exact:
        return exact[base]
    for k in range(len(base), 0, -1):
        info = prefixes.get(base[:k])
        if info is not None:
            return info
    return None


def _norm_qth(qth: str) -> str:
    q = str(qth or "").strip().upper()
    q = _QTH_ALIASES.get(q, q)
    return q if q in US_QTHS or q in CANADA_QTHS else ""


def score(qsos: list[dict], *, my_call: str, cty_path: str) -> dict:
    """Puntuación del log: puntos, multiplicadores (por tipo) y total."""
    mine = country_info(my_call, cty_path)
    seen: set[tuple[str, str]] = set()
    zones: set[tuple[str, int]] = set()
    countries: set[tuple[str, str]] = set()
    qths: set[tuple[str, str]] = set()
    points = 0
    valid = 0
    dupes = 0
    for q in qsos:
        call = str(q.get("call", "")).strip().upper()
        band = str(q.get("band", "")).strip().lower()
        if not call:
            continue
        if (call, band) in seen:
            dupes += 1
            continue
        seen.add((call, band))
        valid += 1
        info = country_info(call, cty_path)
        try:
            zone = int(str(q.get("exchange_recv", "")).strip())
        except ValueError:
            zone = 0
        if 1 <= zone <= 40:
            zones.add((band, zone))
        if info is not None:
            countries.add((band, info[0]))
        qth = _norm_qth(q.get("qth_recv", ""))
        if qth:
            qths.add((band, qth))
        if info is None or mine is None:
            points += 1  # sin datos: el mínimo, mejor quedarse corto que inflar
        elif info[1] != mine[1]:
            points += 3
        elif info[0] != mine[0]:
            points += 2
        else:
            points += 1
    mults = len(zones) + len(countries) + len(qths)
    return {
        "qsos": valid,
        "dupes": dupes,
        "points": points,
        "zones": len(zones),
        "countries": len(countries),
        "qths": len(qths),
        "mults": mults,
        "total": points * mults,
    }


def stats_text(qsos: list[dict], *, my_call: str, cty_path: str) -> str:
    """Texto para la barra de estadísticas del libro."""
    s = score(qsos, my_call=my_call, cty_path=cty_path)
    text = (
        f"Mult: {s['mults']} ({s['zones']} zonas + {s['countries']} países + {s['qths']} W/VE)"
        f" | Puntos: {s['points']} | Total: {s['total']}"
    )
    if s["dupes"]:
        text += f" | Dupes: {s['dupes']}"
    return text
