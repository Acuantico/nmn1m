TEMPLATE_ID = "iaru_hf"
TEMPLATE_NAME = "IARU HF"
LOG_KIND = "ham"
IS_CONTEST = True
DEFAULT_CONTEST_TEXT = "IARU-HF"
ALLOW_CABRILLO = True

FORM_FIELDS = [
    {"key": "call", "label": "Call", "default": "", "required": True, "width": 26},
    {"key": "rst_sent", "label": "RST enviado", "default": "59", "required": True, "width": 26},
    {
        "key": "exchange_sent",
        "label": "Intercambio enviado (zona/HQ)",
        "default": "37",
        "required": True,
        "width": 26,
    },
    {"key": "rst_recv", "label": "RST recibido", "default": "59", "required": True, "width": 26},
    {
        "key": "exchange_recv",
        "label": "Intercambio recibido (zona/HQ)",
        "default": "",
        "required": True,
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
    ("exchange_sent", "Exch Tx", 110),
    ("rst_recv", "RST Rx", 70),
    ("exchange_recv", "Exch Rx", 110),
    ("notes", "Notas", 220),
]


def _clean_exchange(raw: str) -> str:
    text = str(raw or "").strip().upper()
    if not text:
        raise ValueError("El intercambio es obligatorio")
    return text


def build_qso(ctx: dict) -> dict:
    get = ctx["get"]
    call = str(get("call") or "").strip().upper()
    if not call:
        raise ValueError("El indicativo es obligatorio")

    rst_sent = str(get("rst_sent") or "59").strip() or "59"
    rst_recv = str(get("rst_recv") or "59").strip() or "59"
    exchange_sent = _clean_exchange(get("exchange_sent"))
    exchange_recv = _clean_exchange(get("exchange_recv"))

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
        "CATEGORY-MODE: MIXED",
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
    mode = str(qso.get("mode", "")).upper()
    if mode == "SSB":
        mode = "PH"
    elif mode not in {"CW", "PH"}:
        mode = mode[:2] or "PH"
    return (
        f"QSO: {freq_khz:>5} {mode:<2} {dt[0:10]} {dt[11:16].replace(':', '')} "
        f"{our_call:<13} {str(qso.get('rst_sent', '')):<3} {str(qso.get('exchange_sent', '')):<6} "
        f"{str(qso.get('call', '')):<13} {str(qso.get('rst_recv', '')):<3} {str(qso.get('exchange_recv', '')):<6}"
    )
