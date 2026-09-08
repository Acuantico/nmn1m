TEMPLATE_ID = "cq_wpx"
TEMPLATE_NAME = "CQ-WPX"
LOG_KIND = "ham"
IS_CONTEST = True
DEFAULT_CONTEST_TEXT = "CQ-WPX-CW"
ALLOW_CABRILLO = True

FORM_FIELDS = [
    {"key": "call", "label": "Call", "default": "", "required": True, "width": 26},
    {"key": "rst_sent", "label": "RST enviado", "default": "599", "required": True, "width": 26},
    {"key": "serial_sent", "label": "Serial enviado", "default": "", "required": True, "width": 26},
    {"key": "rst_recv", "label": "RST recibido", "default": "599", "required": True, "width": 26},
    {"key": "serial_recv", "label": "Serial recibido", "default": "", "required": True, "width": 26},
    {"key": "notes", "label": "Notas", "default": "", "required": False, "width": 26},
]

TREE_COLUMNS = [
    ("utc", "UTC", 140),
    ("call", "Call", 100),
    ("band", "Banda", 70),
    ("mode", "Modo", 70),
    ("freq", "Freq Hz", 100),
    ("snt", "RST Tx", 70),
    ("sent", "Serie Tx", 70),
    ("rcv", "RST Rx", 70),
    ("recv", "Serie Rx", 80),
    ("notes", "Notas", 220),
]


def build_qso(ctx: dict) -> dict:
    get = ctx["get"]
    call = str(get("call") or "").strip().upper()
    if not call:
        raise ValueError("El indicativo es obligatorio")

    rst_sent = str(get("rst_sent") or "599").strip() or "599"
    rst_recv = str(get("rst_recv") or "599").strip() or "599"

    serial_sent = str(get("serial_sent") or "").strip()
    if ctx.get("auto_serial") and not serial_sent:
        serial_sent = f"{int(ctx.get('next_serial', 1)):03d}"
    if not serial_sent or not serial_sent.isdigit():
        raise ValueError("El serial enviado es obligatorio y numérico")

    serial_recv = str(get("serial_recv") or "").strip()
    if not serial_recv or not serial_recv.isdigit():
        raise ValueError("El serial recibido es obligatorio y numérico")

    serial_sent_i = int(serial_sent)

    return {
        "timestamp_utc": str(ctx["timestamp_utc"]),
        "call": call,
        "band": str(ctx["band"]),
        "mode": str(ctx["mode"]),
        "freq_hz": int(ctx["freq_hz"]),
        "rst_sent": rst_sent,
        "serial_sent": serial_sent_i,
        "rst_recv": rst_recv,
        "serial_recv": serial_recv,
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
        f"{int(qso.get('serial_sent', 0)):03d}",
        qso.get("rst_recv", ""),
        qso.get("serial_recv", ""),
        qso.get("notes", ""),
    )


def adif_fields(qso: dict, station: dict) -> dict:
    dt = qso["timestamp_utc"]
    date = dt[0:10].replace("-", "")
    time_on = dt[11:19].replace(":", "")
    return {
        "CALL": qso.get("call", ""),
        "QSO_DATE": date,
        "TIME_ON": time_on,
        "BAND": str(qso.get("band", "")).replace("m", "M"),
        "MODE": qso.get("mode", ""),
        "FREQ": f"{float(qso.get('freq_hz', 0)) / 1_000_000:.6f}",
        "RST_SENT": qso.get("rst_sent", ""),
        "RST_RCVD": qso.get("rst_recv", ""),
        "STX": str(qso.get("serial_sent", "")),
        "SRX": qso.get("serial_recv", ""),
        "STX_STRING": f"{qso.get('rst_sent', '')} {int(qso.get('serial_sent', 0)):03d}".strip(),
        "SRX_STRING": f"{qso.get('rst_recv', '')} {qso.get('serial_recv', '')}".strip(),
        "CONTEST_ID": station.get("contest", "CQ-WPX-CW"),
        "OPERATOR": station.get("operator", ""),
        "MY_GRIDSQUARE": station.get("my_grid", ""),
        "COMMENT": qso.get("notes", ""),
    }


def cabrillo_header(station: dict) -> list[str]:
    call = station.get("operator") or "EA0XXX"
    contest = station.get("contest") or "CQ-WPX-CW"
    return [
        "START-OF-LOG: 3.0",
        f"CALLSIGN: {call}",
        f"CONTEST: {contest}",
        "CATEGORY-OPERATOR: SINGLE-OP",
        "CATEGORY-BAND: ALL",
        "CATEGORY-MODE: MIXED",
        f"GRID-LOCATOR: {station.get('my_grid', '')}",
        f"OPERATORS: {call}",
        f"NAME: {call}",
        "CLAIMED-SCORE: 0",
    ]


def cabrillo_qso_line(qso: dict, station: dict) -> str:
    dt = qso["timestamp_utc"]
    freq_khz = int(round(float(qso.get("freq_hz", 0)) / 1000.0))
    mode = str(qso.get("mode", "")).upper()
    mode = "PH" if mode == "SSB" else ("CW" if mode == "CW" else mode[:2])
    sent_serial = f"{int(qso.get('serial_sent', 0)):03d}"
    recv_serial = str(qso.get("serial_recv", "")).strip()
    operator = str(station.get("operator", "") or "")
    return (
        f"QSO: {freq_khz:>5} {mode:<2} {dt[0:10]} {dt[11:16].replace(':', '')} "
        f"{operator:<13} {str(qso.get('rst_sent', '')):<3} {sent_serial:<6} "
        f"{str(qso.get('call', '')):<13} {str(qso.get('rst_recv', '')):<3} {recv_serial:<6}"
    )
