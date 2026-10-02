"""Plantilla del Diploma de Municipios de España (DME) de URE.

Bases: https://diplomas.ure.es/diplomas/dme/bases/
- DME general: 300 municipios distintos en mixto (fonía, CW y MGM), contactos
  desde el 1 de enero de 1999.
- Monobanda (300 por banda), Plus (1000 en un modo) y Máster (2000 en cada
  modo): contactos desde el 1 de septiembre de 2018.
- No valen los contactos a través de repetidores.

La referencia DME es el código INE del municipio: 5 cifras, las dos primeras
son la provincia (01-52). Sirve para cazar referencias y, si algún día activas
un municipio, para guardar también la tuya (campo «Mi DME»).
"""

TEMPLATE_ID = "dme"
TEMPLATE_NAME = "Diploma DME"
LOG_KIND = "ham"
IS_CONTEST = True
DEFAULT_CONTEST_TEXT = "DME"
ALLOW_CABRILLO = False

FORM_FIELDS = [
    {"key": "call", "label": "Call", "default": "", "required": True, "width": 26},
    {"key": "rst_sent", "label": "RST enviado", "default": "59", "required": False, "width": 26},
    {"key": "rst_recv", "label": "RST recibido", "default": "59", "required": False, "width": 26},
    {"key": "dme_ref", "label": "Referencia DME (5 cifras)", "default": "", "required": False, "width": 26},
    {"key": "municipio", "label": "Municipio", "default": "", "required": False, "width": 26},
    {"key": "my_dme_ref", "label": "Mi DME (solo si activas)", "default": "", "required": False, "width": 26},
    {"key": "notes", "label": "Notas", "default": "", "required": False, "width": 26},
]

TREE_COLUMNS = [
    ("utc", "UTC", 140),
    ("call", "Call", 100),
    ("band", "Banda", 70),
    ("mode", "Modo", 70),
    ("freq", "Freq Hz", 100),
    ("dme_ref", "DME", 70),
    ("provincia", "Provincia", 130),
    ("municipio", "Municipio", 150),
    ("my_dme_ref", "Mi DME", 70),
    ("notes", "Notas", 200),
]

#: Provincias por código INE (las dos primeras cifras de la referencia DME).
PROVINCIAS = {
    "01": "Araba/Álava", "02": "Albacete", "03": "Alicante", "04": "Almería",
    "05": "Ávila", "06": "Badajoz", "07": "Illes Balears", "08": "Barcelona",
    "09": "Burgos", "10": "Cáceres", "11": "Cádiz", "12": "Castellón",
    "13": "Ciudad Real", "14": "Córdoba", "15": "A Coruña", "16": "Cuenca",
    "17": "Girona", "18": "Granada", "19": "Guadalajara", "20": "Gipuzkoa",
    "21": "Huelva", "22": "Huesca", "23": "Jaén", "24": "León",
    "25": "Lleida", "26": "La Rioja", "27": "Lugo", "28": "Madrid",
    "29": "Málaga", "30": "Murcia", "31": "Navarra", "32": "Ourense",
    "33": "Asturias", "34": "Palencia", "35": "Las Palmas", "36": "Pontevedra",
    "37": "Salamanca", "38": "Santa Cruz de Tenerife", "39": "Cantabria", "40": "Segovia",
    "41": "Sevilla", "42": "Soria", "43": "Tarragona", "44": "Teruel",
    "45": "Toledo", "46": "Valencia", "47": "Valladolid", "48": "Bizkaia",
    "49": "Zamora", "50": "Zaragoza", "51": "Ceuta", "52": "Melilla",
}

#: Modos de cada categoría del diploma (fonía, CW y MGM = modos generados por
#: máquina). Un modo que no esté aquí cuenta solo para el DME general (mixto).
FONIA_MODES = frozenset({"SSB", "USB", "LSB", "AM", "FM", "PH"})
CW_MODES = frozenset({"CW", "CWR"})
MGM_MODES = frozenset({
    "DIGI", "FT8", "FT4", "RTTY", "PSK", "PSK31", "PSK63", "JS8", "MFSK", "OLIVIA",
    "JT65", "JT9", "Q65", "MSK144", "FST4", "CONTESTI", "THOR", "HELL", "SSTV",
})

GENERAL_SINCE = "1999-01-01"
NEW_CATEGORIES_SINCE = "2018-09-01"
DIPLOMA_TARGET = 300


def normalize_dme_ref(raw: str) -> str:
    """'DME 08121', '08-121' o '8121' -> '08121'. Vacío si no se indica.
    Lanza ValueError si no es una referencia DME válida."""
    text = str(raw or "").strip().upper()
    if not text:
        return ""
    if text.startswith("DME"):
        text = text[3:]
    digits = "".join(ch for ch in text if not ch.isspace() and ch not in "-./")
    if not digits.isdigit() or len(digits) not in (4, 5):
        raise ValueError("La referencia DME debe tener 5 cifras (p. ej. 08121)")
    digits = digits.zfill(5)
    if digits[:2] not in PROVINCIAS:
        raise ValueError(f"La referencia DME {digits} no corresponde a ninguna provincia (01-52)")
    return digits


def provincia_de(ref: str) -> str:
    return PROVINCIAS.get(str(ref or "")[:2], "") if ref else ""


def build_qso(ctx: dict) -> dict:
    get = ctx["get"]
    call = str(get("call") or "").strip().upper()
    if not call:
        raise ValueError("El indicativo es obligatorio")

    rst_sent = str(get("rst_sent") or "59").strip() or "59"
    rst_recv = str(get("rst_recv") or "59").strip() or "59"
    dme_ref = normalize_dme_ref(get("dme_ref"))
    my_dme_ref = normalize_dme_ref(get("my_dme_ref"))

    return {
        "timestamp_utc": str(ctx["timestamp_utc"]),
        "call": call,
        "band": str(ctx["band"]),
        "mode": str(ctx["mode"]),
        "freq_hz": int(ctx["freq_hz"]),
        "rst_sent": rst_sent,
        "rst_recv": rst_recv,
        "dme_ref": dme_ref,
        "municipio": str(get("municipio") or "").strip(),
        "my_dme_ref": my_dme_ref,
        "notes": str(get("notes") or "").strip(),
    }


def row_values(qso: dict) -> tuple:
    return (
        qso.get("timestamp_utc", ""),
        qso.get("call", ""),
        qso.get("band", ""),
        qso.get("mode", ""),
        qso.get("freq_hz", 0),
        qso.get("dme_ref", ""),
        provincia_de(qso.get("dme_ref", "")),
        qso.get("municipio", ""),
        qso.get("my_dme_ref", ""),
        qso.get("notes", ""),
    )


def adif_fields(qso: dict, station: dict) -> dict:
    dt = qso["timestamp_utc"]
    out = {
        "CALL": qso.get("call", ""),
        "QSO_DATE": dt[0:10].replace("-", ""),
        "TIME_ON": dt[11:19].replace(":", ""),
        "BAND": str(qso.get("band", "")).replace("m", "M"),
        "MODE": qso.get("mode", ""),
        "FREQ": f"{float(qso.get('freq_hz', 0)) / 1_000_000:.6f}",
        "RST_SENT": qso.get("rst_sent", ""),
        "RST_RCVD": qso.get("rst_recv", ""),
        "OPERATOR": station.get("operator", ""),
        "MY_GRIDSQUARE": station.get("my_grid", ""),
        "COMMENT": qso.get("notes", ""),
    }
    if qso.get("dme_ref"):
        out["SIG"] = "DME"
        out["SIG_INFO"] = qso["dme_ref"]
    if qso.get("municipio"):
        out["QTH"] = qso["municipio"]
    if qso.get("my_dme_ref"):
        out["MY_SIG"] = "DME"
        out["MY_SIG_INFO"] = qso["my_dme_ref"]
    return out


def _mode_category(mode: str) -> str:
    m = str(mode or "").strip().upper()
    if m in FONIA_MODES:
        return "fonia"
    if m in CW_MODES:
        return "cw"
    if m in MGM_MODES:
        return "mgm"
    return ""


def progress(qsos: list[dict]) -> dict:
    """Referencias DME distintas para cada categoría del diploma."""
    general: set[str] = set()
    by_mode: dict[str, set[str]] = {"fonia": set(), "cw": set(), "mgm": set()}
    by_band: dict[str, set[str]] = {}
    for q in qsos:
        ref = str(q.get("dme_ref", "")).strip()
        if not ref:
            continue
        date = str(q.get("timestamp_utc", ""))[:10]
        if date < GENERAL_SINCE:
            continue
        general.add(ref)
        if date < NEW_CATEGORIES_SINCE:
            continue
        cat = _mode_category(q.get("mode", ""))
        if cat:
            by_mode[cat].add(ref)
        band = str(q.get("band", "")).strip().lower()
        if band:
            by_band.setdefault(band, set()).add(ref)
    return {
        "general": len(general),
        "fonia": len(by_mode["fonia"]),
        "cw": len(by_mode["cw"]),
        "mgm": len(by_mode["mgm"]),
        "bands": {band: len(refs) for band, refs in by_band.items()},
    }


def stats_text(qsos: list[dict], *, my_call: str = "", cty_path: str = "") -> str:
    """Texto para la barra de estadísticas: avance hacia el diploma."""
    p = progress(qsos)
    text = (
        f"DME: {p['general']}/{DIPLOMA_TARGET} municipios"
        f" | Fonía {p['fonia']} · CW {p['cw']} · MGM {p['mgm']}"
    )
    top = sorted(p["bands"].items(), key=lambda kv: kv[1], reverse=True)[:3]
    if top:
        text += " | " + " · ".join(f"{band} {n}" for band, n in top)
    return text
