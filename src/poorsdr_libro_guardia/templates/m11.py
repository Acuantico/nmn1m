TEMPLATE_ID = "11m"
TEMPLATE_NAME = "11m"
LOG_KIND = "11m"
IS_MAIN_LOG = True
DEFAULT_CONTEST_TEXT = "11M"
ALLOW_CABRILLO = False

FORM_FIELDS = [
    {"key": "call", "label": "Call", "default": "", "required": True, "width": 26},
    {"key": "rst_sent", "label": "RST enviado", "default": "59", "required": False, "width": 26},
    {"key": "rst_recv", "label": "RST recibido", "default": "59", "required": False, "width": 26},
    {"key": "name", "label": "Nombre corresponsal", "default": "", "required": False, "width": 26},
    {"key": "qth", "label": "QTH", "default": "", "required": False, "width": 26},
    {"key": "grid", "label": "Grid corresponsal", "default": "", "required": False, "width": 26},
    {"key": "power_w", "label": "Potencia (W)", "default": "", "required": False, "width": 26},
    {"key": "notes", "label": "Notas", "default": "", "required": False, "width": 26},
]

TREE_COLUMNS = [
    ("utc", "UTC", 140),
    ("call", "Call", 110),
    ("band", "Banda", 70),
    ("mode", "Modo", 70),
    ("freq", "Freq Hz", 100),
    ("name", "Nombre", 120),
    ("qth", "QTH", 90),
    ("grid", "Grid", 90),
    ("notes", "Notas", 220),
]


def _int_or_empty(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    value = int(float(text))
    if value < 0:
        raise ValueError("La potencia no puede ser negativa")
    return str(value)


def build_qso(ctx: dict) -> dict:
    get = ctx["get"]
    call = str(get("call") or "").strip().upper()
    if not call:
        raise ValueError("El indicativo es obligatorio")

    rst_sent = str(get("rst_sent") or "59").strip() or "59"
    rst_recv = str(get("rst_recv") or "59").strip() or "59"

    band = str(ctx.get("band") or "11m")
    if not band or band == "?":
        band = "11m"

    return {
        "timestamp_utc": str(ctx["timestamp_utc"]),
        "call": call,
        "band": band,
        "mode": str(ctx["mode"]),
        "freq_hz": int(ctx["freq_hz"]),
        "rst_sent": rst_sent,
        "rst_recv": rst_recv,
        "name": str(get("name") or "").strip(),
        "operator_name": str(get("operator_name") or "").strip(),
        "qth": str(get("qth") or "").strip(),
        "grid": str(get("grid") or "").strip().upper(),
        "power_w": _int_or_empty(get("power_w")),
        "notes": str(get("notes") or "").strip(),
    }


def row_values(qso: dict) -> tuple:
    return (
        qso.get("timestamp_utc", ""),
        qso.get("call", ""),
        qso.get("band", ""),
        qso.get("mode", ""),
        qso.get("freq_hz", 0),
        qso.get("name", ""),
        qso.get("qth", ""),
        qso.get("grid", ""),
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
        "MODE": qso.get("mode", ""),
        "FREQ": f"{float(qso.get('freq_hz', 0)) / 1_000_000:.6f}",
        "RST_SENT": qso.get("rst_sent", ""),
        "RST_RCVD": qso.get("rst_recv", ""),
        "NAME": qso.get("name", ""),
        "QTH": qso.get("qth", ""),
        "GRIDSQUARE": qso.get("grid", ""),
        "OPERATOR": station.get("operator", ""),
        "MY_GRIDSQUARE": station.get("my_grid", ""),
        "COMMENT": qso.get("notes", ""),
    }
    if qso.get("power_w"):
        out["TX_PWR"] = qso.get("power_w")
    if station.get("contest"):
        out["CONTEST_ID"] = station.get("contest")
    return out
