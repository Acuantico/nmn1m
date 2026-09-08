import ast
import contextlib
import csv
import importlib.util
import io
import json
import math
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import unicodedata
import uuid
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

try:
    # Integrado en PoorSDR4All: usa sus rutas XDG (una sola fuente de verdad).
    from poorsdr.infra import paths as poorsdr_paths
except ImportError:
    # Uso independiente (sin PoorSDR4All instalado): mismo esquema de rutas
    # (~/.config/poorsdr, ~/.local/share/poorsdr...) para que los datos no se
    # dupliquen si más adelante se instala junto a él.
    class _StandalonePaths:
        _APP_NAME = "poorsdr"

        @classmethod
        def _xdg(cls, env_var: str, default: Path) -> Path:
            raw = os.environ.get(env_var)
            base = Path(raw).expanduser() if raw else default
            return base / cls._APP_NAME

        @classmethod
        def config_dir(cls) -> Path:
            if os.name == "nt":
                raw = os.environ.get("APPDATA")
                base = Path(raw).expanduser() if raw else Path.home() / "AppData" / "Roaming"
                return base / cls._APP_NAME
            return cls._xdg("XDG_CONFIG_HOME", Path.home() / ".config")

        @classmethod
        def data_dir(cls) -> Path:
            if os.name == "nt":
                raw = os.environ.get("LOCALAPPDATA")
                base = Path(raw).expanduser() if raw else Path.home() / "AppData" / "Local"
                return base / cls._APP_NAME
            return cls._xdg("XDG_DATA_HOME", Path.home() / ".local" / "share")

        @classmethod
        def cache_dir(cls) -> Path:
            if os.name == "nt":
                return cls.data_dir() / "cache"
            return cls._xdg("XDG_CACHE_HOME", Path.home() / ".cache")

        @classmethod
        def config_file(cls) -> Path:
            return cls.config_dir() / "config.json"

    poorsdr_paths = _StandalonePaths()

APP_TITLE = "NMN1M"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4532
DEFAULT_OPERATOR = "EA0XXX"
DEFAULT_GRID = "IN80XX"
DEFAULT_WSJTX_UDP_HOST = "0.0.0.0"
DEFAULT_WSJTX_UDP_PORT = 2237
DEFAULT_WSJTX_FWD_HOST = "127.0.0.1"
DEFAULT_WSJTX_FWD_PORT = 2240
DEFAULT_SYNC_HOST = "0.0.0.0"
DEFAULT_SYNC_PORT = 8080
SYNC_PROTOCOL_VERSION = 1
SYNC_MAX_BODY_BYTES = 32 * 1024 * 1024
POLL_MS = 1500
DEFAULT_MAIN_GEOMETRY = "1380x800"
LOG_PAGE_SIZE = 120
MAIN_LOG_TEMPLATE_IDS = ("general", "11m")

# Paleta alineada con la consola de PoorSDR (poorsdr.ui.theme / settings.style).
THEME_BG = "#060608"
THEME_PANEL = "#121217"
THEME_INPUT = "#0d1015"
THEME_INPUT_HOVER = "#141821"
THEME_BORDER = "#2a2f36"
THEME_TEXT = "#f5f7ff"
THEME_MUTED = "#c4cad8"
THEME_ACCENT = "#7b8794"
THEME_SELECTED_BG = "#7b8794"
THEME_ACCENT_BY_BACKGROUND = {
    "back.png": "#7b8794",   # Classic (acero suave)
    "back.jpg": "#f10a0a",   # Rojo
    "back0.jpg": "#ffd200",  # Amarillo
    "back1.jpg": "#36f715",  # Verde
    "back2.jpg": "#0314ec",  # Azul
    "back3.jpg": "#dc12b0",  # Rosa
}
UI_FONT = ("TkDefaultFont",)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USER_CONFIG_DIR = os.fspath(poorsdr_paths.config_dir() / "libro-guardia")
USER_DATA_DIR = os.fspath(poorsdr_paths.data_dir() / "libro-guardia")
USER_CACHE_DIR = os.fspath(poorsdr_paths.cache_dir() / "libro-guardia")
SETTINGS_FILE = os.path.join(USER_CONFIG_DIR, "settings.json")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
LOGS_DIR = os.path.join(USER_DATA_DIR, "logs")
HAMQTH_LOG_FILE = os.path.join(LOGS_DIR, "hamqth.log")
DX11_DIVISIONS_FILE = os.path.join(BASE_DIR, "assets", "dx11_divisions.csv")
DEFAULT_DB_EXT = ".sqlite"
APP_ICON_ICO = os.path.join(BASE_DIR, "assets", "app_icon.ico")
APP_ICON_PNG = os.path.join(BASE_DIR, "assets", "app_icon.png")
APP_TOOLBAR_LOGO = os.path.join(BASE_DIR, "assets", "toolbar_logo.png")
WORLD_MAP_GEOJSON = os.path.join(BASE_DIR, "assets", "map", "ne_110m_land.geojson")
WORLD_COUNTRIES_GEOJSON = os.path.join(BASE_DIR, "assets", "map", "ne_110m_admin_0_countries.geojson")
WORLD_PLACES_GEOJSON = os.path.join(BASE_DIR, "assets", "map", "ne_10m_populated_places.geojson")
WORLD_GEONAMES_CITIES_FILE = os.path.join(BASE_DIR, "assets", "map", "cities500.txt")
WORLD_GEONAMES_CITIES_ZIP = os.path.join(BASE_DIR, "assets", "map", "cities500.zip")
MAP_PLACE_OVERRIDES: list[tuple[str, float, float, int, bool, bool]] = [
    # name, lat, lon, pop_max_estimate, is_national_capital, is_provincial_capital
    ("Lugo", 43.00992, -7.55602, 98000, False, True),
    ("Maceda", 42.26972, -7.65052, 3000, False, False),
]


@contextlib.contextmanager
def _open_geonames_cities():
    """Abre cities500 en texto o directamente desde su ZIP oficial."""
    if os.path.isfile(WORLD_GEONAMES_CITIES_FILE):
        with open(WORLD_GEONAMES_CITIES_FILE, "r", encoding="utf-8", errors="ignore") as handle:
            yield handle
        return
    with zipfile.ZipFile(WORLD_GEONAMES_CITIES_ZIP) as archive:
        with archive.open("cities500.txt") as raw:
            with io.TextIOWrapper(raw, encoding="utf-8", errors="ignore") as handle:
                yield handle

BANDS = [
    (1800000, 2000000, "160m"),
    (3500000, 4000000, "80m"),
    (7000000, 7300000, "40m"),
    (10100000, 10150000, "30m"),
    (14000000, 14350000, "20m"),
    (18068000, 18168000, "17m"),
    (21000000, 21450000, "15m"),
    (24890000, 24990000, "12m"),
    (26965000, 27999999, "11m"),
    (28000000, 29700000, "10m"),
    (50000000, 54000000, "6m"),
]

MODE_MAP = {
    "USB": "SSB",
    "LSB": "SSB",
    "CW": "CW",
    "CWR": "CW",
    "RTTY": "RTTY",
    "PKTLSB": "DIGI",
    "PKTUSB": "DIGI",
    "DIGU": "DIGI",
    "DIGL": "DIGI",
    "FT8": "DIGI",
    "FT4": "DIGI",
}

# Visual country hints for UI only (does not alter stored/exported logs).
CALL_COUNTRY_PATTERNS: list[tuple[str, str, str]] = [
    # Special-event / contest style prefixes (Spain / Portugal)
    (r"^(AO|AM|AN|ED|EE|EF|EG|EH)", "España", "ES"),
    (r"^(CQ|CR|CS)", "Portugal", "PT"),
    # Common DX/expedition entities and numeric prefixes
    (r"^3D2", "Fiyi", "FJ"),
    (r"^4U1", "Naciones Unidas", "UN"),
    (r"^5B", "Chipre", "CY"),
    (r"^5H", "Tanzania", "TZ"),
    (r"^5R", "Madagascar", "MG"),
    (r"^6W", "Senegal", "SN"),
    (r"^7Q", "Malaui", "MW"),
    (r"^8P", "Barbados", "BB"),
    (r"^9K", "Kuwait", "KW"),
    (r"^9N", "Nepal", "NP"),
    (r"^9Q", "R. D. del Congo", "CD"),
    (r"^A4", "Omán", "OM"),
    (r"^A5", "Bután", "BT"),
    (r"^A7", "Catar", "QA"),
    (r"^C3", "Andorra", "AD"),
    (r"^C5", "Gambia", "GM"),
    (r"^C6", "Bahamas", "BS"),
    (r"^C9", "Mozambique", "MZ"),
    (r"^D2", "Angola", "AO"),
    (r"^E7", "Bosnia y Herzegovina", "BA"),
    (r"^ET", "Etiopía", "ET"),
    (r"^EX", "Kirguistán", "KG"),
    (r"^EY", "Tayikistán", "TJ"),
    (r"^EZ", "Turkmenistán", "TM"),
    (r"^H4", "Islas Salomón", "SB"),
    (r"^HR", "Honduras", "HN"),
    (r"^HS", "Tailandia", "TH"),
    (r"^J3", "Granada", "GD"),
    (r"^J6", "Santa Lucía", "LC"),
    (r"^J8", "San Vicente y Granadinas", "VC"),
    (r"^P2", "Papúa Nueva Guinea", "PG"),
    (r"^T2", "Tuvalu", "TV"),
    (r"^T8", "Palaos", "PW"),
    (r"^V3", "Belice", "BZ"),
    (r"^V5", "Namibia", "NA"),
    (r"^V7", "Islas Marshall", "MH"),
    (r"^XA|^XB|^XC", "México", "MX"),
    (r"^XU", "Camboya", "KH"),
    (r"^XV", "Vietnam", "VN"),
    (r"^XX9", "Macao", "MO"),
    (r"^YA", "Afganistán", "AF"),
    (r"^Z2", "Zimbabue", "ZW"),
    (r"^Z3", "Macedonia del Norte", "MK"),
    (r"^ZD7", "Santa Elena", "SH"),
    (r"^ZD8", "Ascensión", "AC"),
    (r"^ZD9", "Tristán da Cunha", "TA"),
    (r"^ZF", "Islas Caimán", "KY"),
    (r"^ZK3", "Tokelau", "TK"),
    (r"^ZL7", "Chatham", "NZ"),
    (r"^ZL8", "Kermadec", "NZ"),
    (r"^ZL9", "Campbell", "NZ"),
    # Iberian full blocks (contest/special calls included)
    (r"^(EA|EB|EC|ED|EE|EF|EG|EH|AM|AN|AO)", "España", "ES"),
    (r"^(CT|CQ|CR|CS|CU)", "Portugal", "PT"),
    (r"^F", "Francia", "FR"),
    (r"^I", "Italia", "IT"),
    (r"^DL", "Alemania", "DE"),
    (r"^G|^M|^2E", "Reino Unido", "GB"),
    (r"^EI", "Irlanda", "IE"),
    (r"^ON", "Bélgica", "BE"),
    (r"^PA|^PB|^PC|^PD", "Países Bajos", "NL"),
    (r"^LX", "Luxemburgo", "LU"),
    (r"^HB", "Suiza", "CH"),
    (r"^OE", "Austria", "AT"),
    (r"^OK", "Chequia", "CZ"),
    (r"^OM", "Eslovaquia", "SK"),
    (r"^SP", "Polonia", "PL"),
    (r"^SM", "Suecia", "SE"),
    (r"^LA", "Noruega", "NO"),
    (r"^OH", "Finlandia", "FI"),
    (r"^OZ", "Dinamarca", "DK"),
    (r"^SV", "Grecia", "GR"),
    (r"^YO", "Rumanía", "RO"),
    (r"^LZ", "Bulgaria", "BG"),
    (r"^9A", "Croacia", "HR"),
    (r"^S5", "Eslovenia", "SI"),
    (r"^YU", "Serbia", "RS"),
    (r"^HA|^HG", "Hungría", "HU"),
    (r"^UA", "Rusia", "RU"),
    (r"^UR|^UT|^UX|^UY|^UZ", "Ucrania", "UA"),
    (r"^ER", "Moldavia", "MD"),
    (r"^LY", "Lituania", "LT"),
    (r"^YL", "Letonia", "LV"),
    (r"^ES", "Estonia", "EE"),
    (r"^TF", "Islandia", "IS"),
    (r"^4X|^4Z", "Israel", "IL"),
    (r"^TA", "Turquía", "TR"),
    (r"^A6", "Emiratos Árabes Unidos", "AE"),
    (r"^SU", "Egipto", "EG"),
    (r"^ZS", "Sudáfrica", "ZA"),
    (r"^CN", "Marruecos", "MA"),
    (r"^7X", "Argelia", "DZ"),
    (r"^5T", "Mauritania", "MR"),
    (r"^K|^N|^W|^A[A-L]", "Estados Unidos", "US"),
    (r"^VE|^VA|^VO|^VY", "Canadá", "CA"),
    (r"^XE|^XF", "México", "MX"),
    (r"^CO|^CM", "Cuba", "CU"),
    (r"^HI", "República Dominicana", "DO"),
    (r"^KP4", "Puerto Rico", "PR"),
    (r"^PY|^PP|^PQ|^PR|^PS|^PT|^PU", "Brasil", "BR"),
    (r"^LU|^LW|^AY|^AZ", "Argentina", "AR"),
    (r"^CX", "Uruguay", "UY"),
    (r"^CE", "Chile", "CL"),
    (r"^YV|^YY", "Venezuela", "VE"),
    (r"^HK|^HJ", "Colombia", "CO"),
    (r"^OA|^OB", "Perú", "PE"),
    (r"^HC|^HD", "Ecuador", "EC"),
    (r"^CP", "Bolivia", "BO"),
    (r"^ZP", "Paraguay", "PY"),
    (r"^JA|^7J|^8J", "Japón", "JP"),
    (r"^BY|^BD|^BG|^BH", "China", "CN"),
    (r"^HL|^DS|^6K", "Corea del Sur", "KR"),
    (r"^VU|^AT", "India", "IN"),
    (r"^9M2|^9M4", "Malasia", "MY"),
    (r"^9V", "Singapur", "SG"),
    (r"^HS|^E2", "Tailandia", "TH"),
    (r"^YB|^YC|^YD", "Indonesia", "ID"),
    (r"^VK", "Australia", "AU"),
    (r"^ZL", "Nueva Zelanda", "NZ"),
]

# 11 m divisions live in assets/dx11_divisions.csv.  Keeping a second partial
# table here previously allowed stale, contradictory assignments to survive.
DX11_DIVISIONS: dict[int, tuple[str, str]] = {}


def _load_dx11_divisions_from_file() -> dict[int, tuple[str, str]]:
    if not os.path.isfile(DX11_DIVISIONS_FILE):
        return {}
    out: dict[int, tuple[str, str]] = {}
    try:
        with open(DX11_DIVISIONS_FILE, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if not isinstance(row, dict):
                    continue
                div_raw = str(row.get("division", "") or row.get("id", "") or row.get("num", "")).strip()
                country = str(row.get("country", "") or row.get("pais", "")).strip()
                iso = str(row.get("iso2", "") or row.get("iso", "")).strip().upper()
                if not div_raw or not country:
                    continue
                try:
                    division = int(div_raw)
                except Exception:
                    continue
                if len(iso) != 2 or not iso.isalpha():
                    iso = ""
                out[division] = (country, iso)
    except Exception:
        return {}
    # Corrupt/empty file guard.
    if len(out) < 5:
        return {}
    return out


def _load_template_module(path: str):
    name = os.path.basename(path)
    spec = importlib.util.spec_from_file_location(f"lg_template_{name[:-3]}_{time.time_ns()}", path)
    if spec is None or spec.loader is None:
        raise ValueError("No se puede cargar el archivo como módulo Python.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    template_id = str(getattr(module, "TEMPLATE_ID", "")).strip().lower()
    template_name = str(getattr(module, "TEMPLATE_NAME", "")).strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", template_id) or not template_name:
        raise ValueError("TEMPLATE_ID o TEMPLATE_NAME no son válidos.")
    if not isinstance(getattr(module, "FORM_FIELDS", None), list) or not isinstance(
        getattr(module, "TREE_COLUMNS", None), list
    ):
        raise ValueError("FORM_FIELDS y TREE_COLUMNS deben ser listas.")
    for function_name in ("build_qso", "row_values", "adif_fields"):
        if not callable(getattr(module, function_name, None)):
            raise ValueError(f"Falta la función obligatoria {function_name}().")
    log_kind = str(getattr(module, "LOG_KIND", "11m" if template_id == "11m" else "ham")).strip().lower()
    if log_kind not in {"ham", "11m"}:
        raise ValueError("LOG_KIND debe ser 'ham' o '11m'.")
    module.LOG_KIND = log_kind
    return module


def _inspect_contest_template_file(path: str) -> tuple[str, str, str]:
    if os.path.getsize(path) > 1_000_000:
        raise ValueError("El archivo supera el tamaño máximo de 1 MB.")
    with open(path, "r", encoding="utf-8-sig") as source_file:
        tree = ast.parse(source_file.read(), filename=path)
    literals = {}
    functions = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value_node = node.value
            for target in targets:
                if isinstance(target, ast.Name) and target.id in {
                    "TEMPLATE_ID", "TEMPLATE_NAME", "LOG_KIND", "IS_CONTEST"
                }:
                    try:
                        literals[target.id] = ast.literal_eval(value_node)
                    except (ValueError, TypeError):
                        pass
    template_id = str(literals.get("TEMPLATE_ID", "")).strip().lower()
    template_name = str(literals.get("TEMPLATE_NAME", "")).strip()
    log_kind = str(literals.get("LOG_KIND", "")).strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", template_id):
        raise ValueError("TEMPLATE_ID debe usar letras minúsculas, números, guion o guion bajo.")
    if template_id in MAIN_LOG_TEMPLATE_IDS:
        raise ValueError("Una plantilla importada no puede sustituir los libros General o 11 m.")
    if not template_name:
        raise ValueError("Falta TEMPLATE_NAME.")
    if log_kind not in {"ham", "11m"}:
        raise ValueError("Falta LOG_KIND = 'ham' o LOG_KIND = '11m'.")
    if literals.get("IS_CONTEST") is not True:
        raise ValueError("La plantilla debe declarar IS_CONTEST = True.")
    missing = {"build_qso", "row_values", "adif_fields"} - functions
    if missing:
        raise ValueError("Faltan funciones obligatorias: " + ", ".join(sorted(missing)))
    return template_id, template_name, log_kind


def _load_templates() -> dict:
    templates = {}
    if not os.path.isdir(TEMPLATES_DIR):
        return templates
    files = [f for f in os.listdir(TEMPLATES_DIR) if f.endswith(".py") and not f.startswith("_")]
    for name in sorted(files):
        try:
            module = _load_template_module(os.path.join(TEMPLATES_DIR, name))
        except Exception:
            continue
        templates[module.TEMPLATE_ID] = module
    return templates


class RigctldClient:
    def __init__(self, host: str, port: int, timeout: float = 2.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock = None
        self.lock = threading.Lock()

    def connect(self):
        self.close()
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self.sock.settimeout(self.timeout)

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def _readline(self) -> str:
        if not self.sock:
            raise ConnectionError("No conectado a rigctld")
        data = bytearray()
        while True:
            chunk = self.sock.recv(1)
            if not chunk:
                raise ConnectionError("Conexión cerrada por rigctld")
            if chunk == b"\n":
                return data.decode("utf-8", errors="replace").rstrip("\r")
            data.extend(chunk)

    def command(self, cmd: str, expect_lines: int | None = None):
        if not self.sock:
            raise ConnectionError("No conectado a rigctld")
        with self.lock:
            self.sock.sendall((cmd.strip() + "\n").encode("utf-8"))
            if expect_lines is None:
                line = self._readline()
                if line.startswith("RPRT"):
                    code = int(line.split()[1])
                    if code != 0:
                        raise RuntimeError(f"rigctld devolvió {line}")
                    return line
                return line
            out = []
            for _ in range(expect_lines):
                line = self._readline()
                if line.startswith("RPRT"):
                    raise RuntimeError(f"rigctld devolvió {line}")
                out.append(line)
            return out

    def get_freq(self) -> int:
        return int(float(self.command("f")))

    def get_mode(self) -> str:
        lines = self.command("m", expect_lines=2)
        return lines[0].strip().upper()

    def get_ptt(self) -> int:
        return int(float(self.command("t")))

    def set_freq(self, freq_hz: int):
        self.command(f"F {int(freq_hz)}")

    def set_mode(self, mode: str):
        mode_up = str(mode or "").strip().upper()
        if not mode_up:
            raise ValueError("Modo vacío")
        passband = 2400 if mode_up in {"USB", "LSB", "DIGU", "DIGL"} else 0
        self.command(f"M {mode_up} {passband}")


class LogSyncServer:
    def __init__(self, host: str, port: int, token: str, sync_callback):
        self.host = host
        self.port = int(port)
        self.token = str(token or "")
        self.sync_callback = sync_callback
        self.httpd: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    def start(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "NMN1MSync/1.0"

            def _send_json(self, status: int, payload: dict):
                raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                if self.path.rstrip("/") not in {"", "/v1/status"}:
                    self._send_json(404, {"ok": False, "error": "Ruta no encontrada"})
                    return
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "app": APP_TITLE,
                        "protocol": SYNC_PROTOCOL_VERSION,
                        "service": "log-sync",
                    },
                )

            def do_POST(self):
                if self.path.rstrip("/") != "/v1/sync":
                    self._send_json(404, {"ok": False, "error": "Ruta no encontrada"})
                    return
                if owner.token and self.headers.get("X-NMN1M-Token", "") != owner.token:
                    self._send_json(401, {"ok": False, "error": "Clave de sincronización incorrecta"})
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0") or 0)
                except ValueError:
                    length = 0
                if length <= 0 or length > SYNC_MAX_BODY_BYTES:
                    self._send_json(413, {"ok": False, "error": "Tamaño de petición no válido"})
                    return
                try:
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    if not isinstance(payload, dict):
                        raise ValueError("La petición debe ser un objeto JSON")
                    response = owner.sync_callback(payload, self.client_address[0])
                    self._send_json(200, response)
                except ValueError as exc:
                    self._send_json(400, {"ok": False, "error": str(exc)})
                except Exception as exc:
                    self._send_json(500, {"ok": False, "error": f"Error interno: {exc}"})

            def log_message(self, _format, *_args):
                return

        self.httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True, name="nmn1m-sync-server")
        self.thread.start()

    def stop(self):
        server = self.httpd
        self.httpd = None
        if server is not None:
            try:
                server.shutdown()
            except Exception:
                pass
            try:
                server.server_close()
            except Exception:
                pass
        thread = self.thread
        self.thread = None
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)


class ContestLoggerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry(DEFAULT_MAIN_GEOMETRY)
        self.root.configure(bg=THEME_BG)
        self._icon_refs: list[tk.PhotoImage] = []
        self._apply_window_icon(self.root)

        self.templates = _load_templates()
        if not self.templates:
            raise RuntimeError("No hay plantillas válidas en Libro-Guardia/templates")
        os.makedirs(LOGS_DIR, exist_ok=True)
        self.dx11_divisions = dict(DX11_DIVISIONS)
        self.dx11_divisions.update(_load_dx11_divisions_from_file())

        self.client: RigctldClient | None = None
        self.connected = False
        self.polling = False
        self._poll_inflight = False
        self.current_freq_hz = 14000000
        self.current_mode = "CW"
        self.current_band = "20m"
        self.next_serial = 1
        self.selected_qso_index: int | None = None
        self._dupe_index: dict[tuple[str, str, str], int] = {}
        self.template_db_map: dict[str, str] = {}
        self._db_connections: dict[str, sqlite3.Connection] = {}
        self.logs_by_template: dict[str, list[dict]] = {}
        self.field_vars: dict[str, tk.StringVar] = {}
        self.field_entries: dict[str, tk.Entry] = {}
        self.freq_entry: ttk.Entry | None = None
        self.band_entry: ttk.Entry | None = None
        self.mode_entry: ttk.Entry | None = None
        self._settings_save_after_id = None
        self._view_indices: list[int] = []
        # Default visualization order: newest contacts first.
        self.sort_column_id: str | None = "utc"
        self.sort_desc: bool = True
        self._refresh_table_after_id = None
        self._refresh_compute_token = 0
        self._refresh_worker_thread: threading.Thread | None = None
        self._table_render_after_id = None
        self._table_render_token = 0
        self._table_render_rows: list[tuple[int, dict]] = []
        self._table_render_pos = 0
        self._country_render_lite = False
        self._all_filtered_rows: list[tuple[int, dict]] = []
        self._page_index = 0
        self._page_size = LOG_PAGE_SIZE
        self.page_info_var = tk.StringVar(value="Página 1/1")
        self.settings_window: tk.Toplevel | None = None
        self.template_combo: ttk.Combobox | None = None
        self.contest_template_combo: ttk.Combobox | None = None
        self.log_ops_template_combo: ttk.Combobox | None = None
        self.log_ops_contest_combo: ttk.Combobox | None = None
        self.db_combo: ttk.Combobox | None = None
        self._main_logs_menu: tk.Menu | None = None
        self._contest_logs_menu: tk.Menu | None = None
        self._suppress_call_filter_refresh = False
        self._suppress_form_reactions = False
        self._last_window_geometry: str = DEFAULT_MAIN_GEOMETRY
        self._pending_window_geometry: str = ""
        self._wsjtx_restart_after_id = None
        self._auto_connect_after_id = None
        self._auto_connect_attempt = 0
        self._hamqth_after_id = None
        self._hamqth_last_call = ""
        self._country_label: tk.Label | None = None
        self._country_flag_image: tk.PhotoImage | None = None
        self._flag_image_cache: dict[tuple[str, int, int], tk.PhotoImage] = {}
        self._tree_flag_icon_mode = False
        self._ordered_tree_base_cols: list[str] = []
        self.wsjtx_sock: socket.socket | None = None
        self.wsjtx_fwd_sock: socket.socket | None = None
        self.wsjtx_thread: threading.Thread | None = None
        self.wsjtx_stop = threading.Event()
        self._wsjtx_bound: tuple[str, int] | None = None
        self._map_canvas: tk.Canvas | None = None
        self._map_status_var = tk.StringVar(value="Sin datos para mostrar en el mapa.")
        self._map_land_polygons: list[list[tuple[float, float]]] = []
        self._map_land_loaded = False
        self._map_country_polygons: list[tuple[str, int, list[tuple[float, float]]]] = []
        self._map_country_labels: list[tuple[str, float, float]] = []
        self._map_countries_loaded = False
        self._map_places: list[tuple[str, str, float, float, int, int, bool, bool]] = []
        self._map_places_loaded = False
        self._map_render_after_id = None
        self._map_zoom = 1.0
        self._map_pan_x = 0.0
        self._map_pan_y = 0.0
        self._map_drag_start: tuple[int, int] | None = None
        self._map_drag_moved = False
        self._map_station_points: list[tuple[float, float, str, str]] = []
        self._map_location_filter = ""
        self._theme_accent_cached = THEME_ACCENT
        self._theme_accent_mtime = 0.0
        self._sync_lock = threading.RLock()
        self._sync_server: LogSyncServer | None = None
        self._sync_inflight = False
        self._last_revision = 0
        self.sync_device_id = str(uuid.uuid4())

        self.host_var = tk.StringVar(value=DEFAULT_HOST)
        self.port_var = tk.StringVar(value=str(DEFAULT_PORT))
        self.status_var = tk.StringVar(value="Desconectado")
        self.operator_var = tk.StringVar(value=DEFAULT_OPERATOR)
        self.operator_11_var = tk.StringVar(value="")
        self.grid_var = tk.StringVar(value=DEFAULT_GRID)
        self.contest_var = tk.StringVar(value="")
        self.hamqth_user_var = tk.StringVar(value="")
        self.hamqth_pass_var = tk.StringVar(value="")
        self.freq_var = tk.StringVar(value="14.000.000")
        self.band_var = tk.StringVar(value="20m")
        self.mode_var = tk.StringVar(value="CW")
        self.auto_poll_var = tk.BooleanVar(value=True)
        self.auto_connect_var = tk.BooleanVar(value=False)
        self.auto_serial_var = tk.BooleanVar(value=True)
        self.wsjtx_udp_enabled_var = tk.BooleanVar(value=False)
        self.wsjtx_udp_host_var = tk.StringVar(value=DEFAULT_WSJTX_UDP_HOST)
        self.wsjtx_udp_port_var = tk.StringVar(value=str(DEFAULT_WSJTX_UDP_PORT))
        self.wsjtx_udp_forward_enabled_var = tk.BooleanVar(value=False)
        self.wsjtx_udp_forward_host_var = tk.StringVar(value=DEFAULT_WSJTX_FWD_HOST)
        self.wsjtx_udp_forward_port_var = tk.StringVar(value=str(DEFAULT_WSJTX_FWD_PORT))
        self.wsjtx_status_var = tk.StringVar(value="WSJT-X UDP: detenido")
        self.sync_server_enabled_var = tk.BooleanVar(value=False)
        self.sync_server_host_var = tk.StringVar(value=DEFAULT_SYNC_HOST)
        self.sync_server_port_var = tk.StringVar(value=str(DEFAULT_SYNC_PORT))
        self.sync_remote_host_var = tk.StringVar(value="")
        self.sync_remote_port_var = tk.StringVar(value=str(DEFAULT_SYNC_PORT))
        self.sync_token_var = tk.StringVar(value="")
        self.sync_device_id_var = tk.StringVar(value=self.sync_device_id)
        self.sync_status_var = tk.StringVar(value="Sincronización: detenida")
        self.template_var = tk.StringVar(value="")
        self.template_header_var = tk.StringVar(value="-")
        self.log_ops_template_var = tk.StringVar(value="")
        self.dupe_var = tk.StringVar(value="")
        self.country_var = tk.StringVar(value="")
        self.mult_var = tk.StringVar(value="Multiplicadores: 0")
        self.rate_var = tk.StringVar(value="QSOs: 0")

        self._refresh_template_catalog()
        self.flags_svg_dir = os.path.join(BASE_DIR, "assets", "flag-icons", "flags", "4x3")
        self.flags_png_cache_dir = os.path.join(USER_CACHE_DIR, "flags")
        self.world_prefix_csv = os.path.join(BASE_DIR, "assets", "cty.csv")
        self.country_meta_json = os.path.join(BASE_DIR, "assets", "flag-icons", "country.json")
        os.makedirs(self.flags_png_cache_dir, exist_ok=True)
        self._country_name_to_iso: dict[str, str] = {}
        self._world_prefixes: list[tuple[str, str, str]] = []
        self._world_exact_calls: dict[str, tuple[str, str]] = {}
        # Keep HAM and 11 m results in separate cache namespaces.  The same
        # leading token can mean completely different things in both systems
        # (for example, HAM prefix 4X versus 11 m division 4).
        self._call_country_cache: dict[tuple[str, str], tuple[str, str]] = {}
        self._load_country_iso_index()
        self._load_world_prefixes()

        self._build_ui()
        self._bind_events()
        self._load_settings()
        self._ensure_all_template_default_dbs()

        initial_template = self._resolve_initial_template()
        self._set_template(initial_template, initialize=True)
        self._restore_window_geometry()

        self._refresh_serial_fields()
        self._update_stats()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.bind("<Configure>", self._on_main_window_configure)
        if self.auto_connect_var.get():
            self._start_auto_connect_sequence(initial_delay_ms=250)
        self._apply_wsjtx_udp_settings()
        self._apply_sync_server_settings(silent=True)

    def _apply_window_icon(self, window) -> None:
        if window is None:
            return
        try:
            if os.path.isfile(APP_ICON_ICO):
                window.iconbitmap(default=APP_ICON_ICO)
        except Exception:
            pass
        try:
            if os.path.isfile(APP_ICON_PNG):
                img = tk.PhotoImage(file=APP_ICON_PNG)
                self._icon_refs.append(img)
                window.iconphoto(True, img)
        except Exception:
            pass

    def _ordered_template_ids(self) -> list[str]:
        main = [template_id for template_id in MAIN_LOG_TEMPLATE_IDS if template_id in self.templates]
        contests = [template_id for template_id in self.templates if template_id not in main]
        contests.sort(key=lambda template_id: self.templates[template_id].TEMPLATE_NAME.lower())
        return main + contests

    def _is_main_log_template(self, template_id: str) -> bool:
        return template_id in MAIN_LOG_TEMPLATE_IDS or bool(
            getattr(self.templates.get(template_id), "IS_MAIN_LOG", False)
        )

    def _template_log_kind(self, template_id: str) -> str:
        module = self.templates.get(str(template_id or "").strip().lower())
        fallback = "11m" if template_id == "11m" else "ham"
        kind = str(getattr(module, "LOG_KIND", fallback)).strip().lower()
        return kind if kind in {"ham", "11m"} else fallback

    def _main_log_id_for(self, template_id: str) -> str:
        return "11m" if self._template_log_kind(template_id) == "11m" else "general"

    def _refresh_template_catalog(self) -> None:
        self.template_ids = self._ordered_template_ids()
        self.main_template_ids = [tid for tid in self.template_ids if self._is_main_log_template(tid)]
        self.contest_template_ids = [tid for tid in self.template_ids if not self._is_main_log_template(tid)]
        self.template_name_to_id = {self.templates[tid].TEMPLATE_NAME: tid for tid in self.template_ids}
        self.main_template_display_values = [self.templates[tid].TEMPLATE_NAME for tid in self.main_template_ids]
        self.contest_template_display_values = [self.templates[tid].TEMPLATE_NAME for tid in self.contest_template_ids]
        self.template_display_values = self.main_template_display_values + self.contest_template_display_values

    def _refresh_template_menus(self) -> None:
        if self._main_logs_menu is not None:
            self._main_logs_menu.delete(0, "end")
            for tid in self.main_template_ids:
                label = self.templates[tid].TEMPLATE_NAME
                if tid == self.current_template_id:
                    label = f"✓ {label}"
                self._main_logs_menu.add_command(label=label, command=lambda value=tid: self._set_template(value))
        if self._contest_logs_menu is not None:
            self._contest_logs_menu.delete(0, "end")
            if self.contest_template_ids:
                for tid in self.contest_template_ids:
                    label = self.templates[tid].TEMPLATE_NAME
                    if tid == self.current_template_id:
                        label = f"✓ {label}"
                    kind = "11 m" if self._template_log_kind(tid) == "11m" else "HAM"
                    self._contest_logs_menu.add_command(
                        label=f"{label}  [{kind}]", command=lambda value=tid: self._set_template(value)
                    )
                self._contest_logs_menu.add_separator()
            self._contest_logs_menu.add_command(label="Importar plantilla...", command=self.import_contest_template)

    def _resolve_initial_template(self) -> str:
        saved = str(self.template_var.get() or "").strip().lower()
        if saved in self.templates:
            return saved
        return "general" if "general" in self.templates else self.template_ids[0]

    def _build_ui(self):
        # Fixed header: the large logo overlays the free left area and does
        # not participate in geometry calculation, so it cannot make the
        # application header taller.
        top = ttk.Frame(self.root, padding=8, height=140)
        top.pack(fill="x")
        top.pack_propagate(False)

        top_bar = ttk.Frame(top)
        top_bar.pack(fill="x")
        actions = ttk.Frame(top_bar)
        actions.pack(side="right")
        try:
            if os.path.isfile(APP_TOOLBAR_LOGO):
                toolbar_logo = tk.PhotoImage(file=APP_TOOLBAR_LOGO)
                self._icon_refs.append(toolbar_logo)
                tk.Label(
                    top,
                    image=toolbar_logo,
                    bg=THEME_BG,
                    bd=0,
                    highlightthickness=0,
                ).place(x=8, rely=0.5, anchor="w")
        except Exception:
            pass
        self.template_header_label = tk.Label(
            top_bar,
            textvariable=self.template_header_var,
            fg=THEME_ACCENT,
            bg=THEME_BG,
            anchor="center",
            font=("TkDefaultFont", 11, "bold"),
        )
        # Exact horizontal centering in the window line.
        self.template_header_label.place(relx=0.5, rely=0.5, anchor="center")
        main_logs_button = ttk.Menubutton(actions, text="Libros principales")
        main_logs_button.pack(side="left", padx=(0, 6))
        self._main_logs_menu = tk.Menu(main_logs_button, tearoff=0)
        main_logs_button.configure(menu=self._main_logs_menu)
        contest_logs_button = ttk.Menubutton(actions, text="Concursos")
        contest_logs_button.pack(side="left", padx=(0, 6))
        self._contest_logs_menu = tk.Menu(contest_logs_button, tearoff=0)
        contest_logs_button.configure(menu=self._contest_logs_menu)
        self._refresh_template_menus()
        ttk.Button(actions, text="Ajustes...", command=self.open_settings_window).pack(fill="x")

        status = ttk.LabelFrame(top, text="Estado", padding=(6, 4))
        status.pack(anchor="center", pady=(4, 0))
        ttk.Label(status, text="Frecuencia").grid(row=0, column=0, sticky="w")
        self.freq_entry = ttk.Entry(status, textvariable=self.freq_var, width=12)
        self.freq_entry.grid(row=0, column=1, padx=3)
        ttk.Label(status, text="Banda").grid(row=0, column=2, sticky="w")
        self.band_entry = ttk.Entry(status, textvariable=self.band_var, width=6)
        self.band_entry.grid(row=0, column=3, padx=3)
        ttk.Label(status, text="Modo").grid(row=0, column=4, sticky="w")
        self.mode_entry = ttk.Entry(status, textvariable=self.mode_var, width=6)
        self.mode_entry.grid(row=0, column=5, padx=3)
        ttk.Label(
            status,
            textvariable=self.status_var,
            wraplength=340,
            justify="left",
            anchor="w",
        ).grid(row=1, column=0, columnspan=6, sticky="ew", pady=(3, 0))

        mid = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        mid.pack(fill="both", expand=True)

        self.form = ttk.LabelFrame(mid, text="Entrada QSO", padding=8)
        self.form.pack(side="left", fill="y", padx=(0, 8))

        self.form_fields_frame = ttk.Frame(self.form)
        self.form_fields_frame.grid(row=0, column=0, columnspan=2, sticky="ew")

        self.auto_serial_check = ttk.Checkbutton(
            self.form,
            text="Serial automático",
            variable=self.auto_serial_var,
            command=self._refresh_serial_fields,
        )
        self.auto_serial_check.grid(row=1, column=0, columnspan=2, sticky="w", pady=4)
        self.auto_serial_check.grid_remove()

        ttk.Label(self.form, textvariable=self.dupe_var).grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 8))
        self._country_label = tk.Label(
            self.form,
            textvariable=self.country_var,
            image="",
            compound="left",
            anchor="w",
            bg=THEME_PANEL,
            fg=THEME_TEXT,
        )
        self._country_label.grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Button(self.form, text="Guardar QSO", command=self.save_qso).grid(row=4, column=0, sticky="ew", pady=3)
        ttk.Button(self.form, text="Limpiar", command=self.clear_entry).grid(row=4, column=1, sticky="ew", pady=3)
        ttk.Button(self.form, text="Actualizar seleccionado", command=self.update_selected_qso).grid(
            row=5, column=0, sticky="ew", pady=3
        )
        ttk.Button(self.form, text="Eliminar seleccionado", command=self.delete_selected_qso).grid(
            row=5, column=1, sticky="ew", pady=3
        )
        ttk.Button(self.form, text="Consultar HamQTH", command=self.lookup_hamqth).grid(
            row=6, column=0, columnspan=2, sticky="ew", pady=3
        )
        self.form.columnconfigure(1, weight=1)

        right = ttk.Frame(mid)
        right.pack(side="left", fill="both", expand=True)

        stats = ttk.Frame(right, padding=(0, 0, 0, 8))
        stats.pack(fill="x")
        ttk.Label(stats, textvariable=self.mult_var).pack(side="left", padx=(0, 12))
        ttk.Label(stats, textvariable=self.rate_var).pack(side="left")
        ttk.Button(stats, text="◀", width=3, command=self._prev_page).pack(side="right")
        ttk.Label(stats, textvariable=self.page_info_var).pack(side="right", padx=6)
        ttk.Button(stats, text="▶", width=3, command=self._next_page).pack(side="right")

        right_notebook = ttk.Notebook(right)
        right_notebook.pack(fill="both", expand=True)
        table_tab = ttk.Frame(right_notebook)
        map_tab = ttk.Frame(right_notebook)
        right_notebook.add(table_tab, text="QSOs")
        right_notebook.add(map_tab, text="Mapa")
        right_notebook.bind("<<NotebookTabChanged>>", lambda _e: self._schedule_map_refresh(20))

        table_wrap = ttk.Frame(table_tab)
        table_wrap.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table_wrap, columns=(), show="headings", height=22)
        yscroll = ttk.Scrollbar(table_wrap, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(table_wrap, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        table_wrap.grid_rowconfigure(0, weight=1)
        table_wrap.grid_columnconfigure(0, weight=1)

        map_tab.rowconfigure(0, weight=1)
        map_tab.columnconfigure(0, weight=1)
        self._map_canvas = tk.Canvas(
            map_tab,
            bg="#0f1e2e",
            highlightthickness=1,
            highlightbackground=THEME_BORDER,
        )
        self._map_canvas.grid(row=0, column=0, sticky="nsew")
        self._map_canvas.bind("<Configure>", lambda _e: self._schedule_map_refresh(20))
        self._map_canvas.bind("<MouseWheel>", self._on_map_mousewheel)
        self._map_canvas.bind("<Button-4>", self._on_map_scroll_linux)
        self._map_canvas.bind("<Button-5>", self._on_map_scroll_linux)
        self._map_canvas.bind("<ButtonPress-1>", self._on_map_drag_start)
        self._map_canvas.bind("<B1-Motion>", self._on_map_drag_move)
        self._map_canvas.bind("<ButtonRelease-1>", self._on_map_left_release)
        self._map_canvas.bind("<Double-Button-1>", self._on_map_reset_view)
        self._map_canvas.bind("<Button-3>", self._on_map_station_click)
        map_tools = ttk.Frame(map_tab)
        map_tools.grid(row=2, column=0, sticky="w", padx=6, pady=(6, 0))
        ttk.Button(map_tools, text="+", width=3, command=lambda: self._map_zoom_step(2.0)).pack(side="left")
        ttk.Button(map_tools, text="-", width=3, command=lambda: self._map_zoom_step(1 / 2.0)).pack(side="left", padx=(4, 0))
        ttk.Button(map_tools, text="Reset", command=self._on_map_reset_view).pack(side="left", padx=(6, 0))
        ttk.Label(map_tab, textvariable=self._map_status_var).grid(row=1, column=0, sticky="w", padx=6, pady=(6, 0))

    def _bind_events(self):
        self.call_var = None
        if self.template_combo is not None:
            self.template_combo.bind("<<ComboboxSelected>>", self._on_template_selected)

        for var in (
            self.host_var,
            self.port_var,
            self.operator_var,
            self.operator_11_var,
            self.grid_var,
            self.contest_var,
            self.hamqth_user_var,
            self.hamqth_pass_var,
            self.log_ops_template_var,
            self.sync_server_host_var,
            self.sync_server_port_var,
            self.sync_remote_host_var,
            self.sync_remote_port_var,
            self.sync_token_var,
        ):
            var.trace_add("write", lambda *_: self._schedule_settings_save())
        self.auto_poll_var.trace_add("write", lambda *_: self._schedule_settings_save())
        self.auto_connect_var.trace_add("write", self._on_auto_connect_changed)
        self.auto_serial_var.trace_add("write", lambda *_: self._schedule_settings_save())
        self.wsjtx_udp_enabled_var.trace_add("write", lambda *_: self._on_wsjtx_udp_cfg_changed())
        self.wsjtx_udp_host_var.trace_add("write", lambda *_: self._on_wsjtx_udp_cfg_changed())
        self.wsjtx_udp_port_var.trace_add("write", lambda *_: self._on_wsjtx_udp_cfg_changed())
        self.wsjtx_udp_forward_enabled_var.trace_add("write", lambda *_: self._on_wsjtx_udp_cfg_changed())
        self.wsjtx_udp_forward_host_var.trace_add("write", lambda *_: self._on_wsjtx_udp_cfg_changed())
        self.wsjtx_udp_forward_port_var.trace_add("write", lambda *_: self._on_wsjtx_udp_cfg_changed())
        self.sync_server_enabled_var.trace_add("write", lambda *_: self._schedule_settings_save())

        self.tree.bind("<<TreeviewSelect>>", self._on_qso_tree_select)
        self.grid_var.trace_add("write", lambda *_: self._schedule_map_refresh(120))

    def _build_log_menu(self, button: ttk.Menubutton):
        menu = tk.Menu(button, tearoff=0)
        menu.add_command(label="Importar log...", command=self.import_log)
        menu.add_command(label="Copia de seguridad base actual...", command=self.backup_current_database)
        menu.add_command(label="Volcar concurso al libro principal...", command=self.import_current_log_to_general)
        menu.add_separator()
        menu.add_command(label="Exportar CSV...", command=self.export_csv)
        menu.add_command(label="Exportar ADIF...", command=self.export_adif)
        menu.add_command(label="Exportar Cabrillo...", command=self.export_cabrillo)
        button.configure(menu=menu)
        self._log_menu = menu

    def _on_settings_close(self):
        if self.settings_window is not None:
            try:
                self.settings_window.destroy()
            except Exception:
                pass
        self.settings_window = None
        self.template_combo = None
        self.contest_template_combo = None
        self.log_ops_template_combo = None
        self.log_ops_contest_combo = None
        self.db_combo = None

    def open_settings_window(self):
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.deiconify()
            self.settings_window.lift()
            self.settings_window.focus_force()
            return

        win = tk.Toplevel(self.root)
        self.settings_window = win
        win.title(f"{APP_TITLE} - Ajustes")
        win.configure(bg=THEME_BG)
        win.geometry("760x470")
        self._apply_window_icon(win)
        win.transient(self.root)
        win.protocol("WM_DELETE_WINDOW", self._on_settings_close)

        notebook = ttk.Notebook(win)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)

        radio_tab = ttk.Frame(notebook, padding=10)
        stn_tab = ttk.Frame(notebook, padding=10)
        log_tab = ttk.Frame(notebook, padding=10)
        sync_tab = ttk.Frame(notebook, padding=10)
        notebook.add(radio_tab, text="Radio / rigctld")
        notebook.add(stn_tab, text="Estación / actividad")
        notebook.add(log_tab, text="Log")
        notebook.add(sync_tab, text="Sincronización")

        ttk.Label(radio_tab, text="Host").grid(row=0, column=0, sticky="w")
        ttk.Entry(radio_tab, textvariable=self.host_var, width=16).grid(row=0, column=1, padx=(2, 4))
        ttk.Label(radio_tab, text="Puerto").grid(row=0, column=2, sticky="w")
        ttk.Entry(radio_tab, textvariable=self.port_var, width=8).grid(row=0, column=3, padx=4)
        ttk.Button(radio_tab, text="Conectar", command=self.connect_rig).grid(row=0, column=4, padx=4)
        ttk.Button(radio_tab, text="Desconectar", command=self.disconnect_rig).grid(row=0, column=5, padx=4)
        ttk.Checkbutton(radio_tab, text="Lectura periódica", variable=self.auto_poll_var).grid(row=0, column=6, padx=8, sticky="w")
        ttk.Checkbutton(radio_tab, text="Autoconectar al inicio", variable=self.auto_connect_var).grid(
            row=1, column=6, padx=8, sticky="w", pady=(6, 0)
        )
        ttk.Button(radio_tab, text="Leer ahora", command=self.poll_rig_once).grid(row=2, column=4, padx=4, pady=(8, 0), sticky="w")
        ttk.Label(radio_tab, textvariable=self.status_var).grid(row=2, column=0, columnspan=4, sticky="w", pady=(8, 0))

        ttk.Separator(radio_tab, orient="horizontal").grid(row=3, column=0, columnspan=7, sticky="ew", pady=(12, 8))
        ttk.Checkbutton(
            radio_tab,
            text="Reenvío UDP",
            variable=self.wsjtx_udp_forward_enabled_var
        ).grid(row=4, column=0, columnspan=3, sticky="w")
        ttk.Label(radio_tab, text="Host").grid(row=4, column=3, sticky="e")
        ttk.Entry(radio_tab, textvariable=self.wsjtx_udp_forward_host_var, width=14).grid(row=4, column=4, padx=(4, 6), sticky="w")
        ttk.Label(radio_tab, text="Puerto").grid(row=4, column=5, sticky="e")
        ttk.Entry(radio_tab, textvariable=self.wsjtx_udp_forward_port_var, width=8).grid(row=4, column=6, padx=(4, 0), sticky="w")

        ttk.Label(stn_tab, text="Indicativo HAM").grid(row=0, column=0, sticky="w")
        ttk.Entry(stn_tab, textvariable=self.operator_var, width=16).grid(row=0, column=1, padx=(6, 2), sticky="w")
        ttk.Label(stn_tab, text="Indicativo 11 m").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(stn_tab, textvariable=self.operator_11_var, width=16).grid(row=1, column=1, padx=(6, 2), pady=(8, 0), sticky="w")
        ttk.Label(stn_tab, text="Grid").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(stn_tab, textvariable=self.grid_var, width=12).grid(row=2, column=1, padx=(6, 2), pady=(8, 0), sticky="w")
        ttk.Label(stn_tab, text="Concurso/Actividad").grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(stn_tab, textvariable=self.contest_var, width=24).grid(row=3, column=1, padx=(6, 2), pady=(8, 0), sticky="w")
        ttk.Label(stn_tab, text="HamQTH usuario").grid(row=4, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(stn_tab, textvariable=self.hamqth_user_var, width=24).grid(row=4, column=1, padx=(6, 2), pady=(8, 0), sticky="w")
        ttk.Label(stn_tab, text="HamQTH clave").grid(row=5, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(stn_tab, textvariable=self.hamqth_pass_var, width=24, show="*").grid(
            row=5, column=1, padx=(6, 2), pady=(8, 0), sticky="w"
        )

        log_canvas = tk.Canvas(log_tab, highlightthickness=0, bg=THEME_PANEL)
        log_scroll = ttk.Scrollbar(log_tab, orient="vertical", command=log_canvas.yview)
        log_canvas.configure(yscrollcommand=log_scroll.set)
        log_canvas.grid(row=0, column=0, sticky="nsew")
        log_scroll.grid(row=0, column=1, sticky="ns")
        log_tab.rowconfigure(0, weight=1)
        log_tab.columnconfigure(0, weight=1)

        log_content = ttk.Frame(log_canvas)
        log_window = log_canvas.create_window((0, 0), window=log_content, anchor="nw")
        log_content.bind("<Configure>", lambda _e: log_canvas.configure(scrollregion=log_canvas.bbox("all")))
        log_canvas.bind("<Configure>", lambda e: log_canvas.itemconfigure(log_window, width=e.width))

        ttk.Label(log_content, text="Libro principal").grid(row=0, column=0, sticky="w")
        self.log_ops_template_combo = ttk.Combobox(
            log_content,
            values=self.main_template_display_values,
            state="readonly",
            textvariable=tk.StringVar(value=""),
            width=20,
        )
        self.log_ops_template_combo.grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.log_ops_template_combo.bind("<<ComboboxSelected>>", self._on_log_ops_template_selected)
        selected_ops_id = self._resolve_log_ops_template_id()
        try:
            if selected_ops_id in self.main_template_ids:
                self.log_ops_template_combo.set(self.templates[selected_ops_id].TEMPLATE_NAME)
        except Exception:
            pass

        ttk.Label(log_content, text="Plantilla de concurso").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.log_ops_contest_combo = ttk.Combobox(
            log_content, values=self.contest_template_display_values, state="readonly", width=20
        )
        self.log_ops_contest_combo.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(8, 0))
        self.log_ops_contest_combo.bind("<<ComboboxSelected>>", self._on_log_ops_contest_selected)
        if selected_ops_id in self.contest_template_ids:
            self.log_ops_contest_combo.set(self.templates[selected_ops_id].TEMPLATE_NAME)

        ttk.Label(log_content, text="Base de datos").grid(row=2, column=0, sticky="w", pady=(12, 0))
        self.db_combo = ttk.Combobox(
            log_content,
            values=[],
            state="readonly",
            width=28,
        )
        self.db_combo.grid(row=3, column=0, sticky="w", pady=(6, 0))
        self._refresh_db_combo_values()
        db_actions = ttk.Frame(log_content)
        db_actions.grid(row=3, column=1, sticky="w", padx=(12, 0))
        ttk.Button(db_actions, text="Cargar", command=self._load_selected_db_for_template).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(db_actions, text="Crear", command=self._create_db_for_template).grid(row=0, column=1, padx=(0, 6))
        ttk.Button(db_actions, text="Renombrar", command=self._rename_selected_db_for_template).grid(row=0, column=2, padx=(0, 6))
        ttk.Button(db_actions, text="Borrar", command=self._delete_selected_db_for_template).grid(row=0, column=3)

        ttk.Label(log_content, text="Importar").grid(row=4, column=0, sticky="w", pady=(12, 0))
        ttk.Button(log_content, text="Importar log...", command=self.import_log).grid(row=5, column=0, sticky="w", pady=(6, 0))
        ttk.Button(log_content, text="Copia de seguridad base actual...", command=self.backup_current_database).grid(
            row=5, column=1, sticky="w", padx=(12, 0), pady=(6, 0)
        )
        ttk.Button(log_content, text="Volcar concurso al libro principal...", command=self.import_current_log_to_general).grid(
            row=6, column=0, sticky="w", pady=(6, 0)
        )
        ttk.Label(log_content, text="Exportar").grid(row=7, column=0, sticky="w", pady=(12, 0))
        ttk.Button(log_content, text="Exportar CSV...", command=self.export_csv).grid(row=8, column=0, sticky="w", pady=(6, 0))
        ttk.Button(log_content, text="Exportar ADIF...", command=self.export_adif).grid(row=9, column=0, sticky="w", pady=(6, 0))
        ttk.Button(log_content, text="Exportar Cabrillo...", command=self.export_cabrillo).grid(row=10, column=0, sticky="w", pady=(6, 0))
        ttk.Button(log_content, text="Abrir carpeta logs", command=self.open_logs_directory).grid(
            row=8, column=1, rowspan=3, sticky="n", padx=(12, 0), pady=(6, 0)
        )
        ttk.Separator(log_content, orient="horizontal").grid(row=11, column=0, columnspan=2, sticky="ew", pady=(12, 8))
        ttk.Checkbutton(log_content, text="Escuchar WSJT-X por UDP", variable=self.wsjtx_udp_enabled_var).grid(
            row=12, column=0, columnspan=2, sticky="w"
        )
        wsjtx_cfg = ttk.Frame(log_content)
        wsjtx_cfg.grid(row=13, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Label(wsjtx_cfg, text="Host").grid(row=0, column=0, sticky="w")
        ttk.Entry(wsjtx_cfg, textvariable=self.wsjtx_udp_host_var, width=14).grid(row=0, column=1, padx=(4, 8))
        ttk.Label(wsjtx_cfg, text="Puerto").grid(row=0, column=2, sticky="w")
        ttk.Entry(wsjtx_cfg, textvariable=self.wsjtx_udp_port_var, width=7).grid(row=0, column=3, padx=(4, 8))
        ttk.Button(wsjtx_cfg, text="Aplicar", command=self._apply_wsjtx_udp_settings).grid(row=0, column=4, padx=(4, 0))
        ttk.Label(log_content, textvariable=self.wsjtx_status_var).grid(row=14, column=0, columnspan=2, sticky="w", pady=(6, 0))

        server_box = ttk.LabelFrame(sync_tab, text="Servidor de este equipo", padding=10)
        server_box.pack(fill="x")
        ttk.Checkbutton(
            server_box,
            text="Activar servidor de sincronización",
            variable=self.sync_server_enabled_var,
            command=self._apply_sync_server_settings,
        ).grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(server_box, text="Escuchar en").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(server_box, textvariable=self.sync_server_host_var, width=18).grid(row=1, column=1, padx=(6, 14), pady=(8, 0))
        ttk.Label(server_box, text="Puerto").grid(row=1, column=2, sticky="w", pady=(8, 0))
        ttk.Entry(server_box, textvariable=self.sync_server_port_var, width=8).grid(row=1, column=3, padx=(6, 0), pady=(8, 0))
        ttk.Label(server_box, text="Clave compartida").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(server_box, textvariable=self.sync_token_var, width=28, show="•").grid(
            row=2, column=1, columnspan=2, sticky="w", padx=(6, 14), pady=(8, 0)
        )
        ttk.Button(server_box, text="Aplicar", command=self._apply_sync_server_settings).grid(
            row=2, column=3, sticky="e", pady=(8, 0)
        )
        local_ips = ", ".join(self._local_ipv4_addresses()) or "no detectada"
        ttk.Label(server_box, text=f"IP de este equipo en la red: {local_ips}").grid(
            row=3, column=0, columnspan=4, sticky="w", pady=(8, 0)
        )

        client_box = ttk.LabelFrame(sync_tab, text="Sincronizar este libro con un servidor", padding=10)
        client_box.pack(fill="x", pady=(12, 0))
        ttk.Label(client_box, text="Servidor / IP").grid(row=0, column=0, sticky="w")
        ttk.Entry(client_box, textvariable=self.sync_remote_host_var, width=28).grid(row=0, column=1, padx=(6, 14))
        ttk.Label(client_box, text="Puerto").grid(row=0, column=2, sticky="w")
        ttk.Entry(client_box, textvariable=self.sync_remote_port_var, width=8).grid(row=0, column=3, padx=(6, 0))
        ttk.Button(client_box, text="Sincronizar ahora", command=self.sync_now).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(10, 0)
        )
        ttk.Label(
            client_box,
            text="Use la misma clave compartida del servidor. Las plantillas de concurso deben estar instaladas en ambos equipos.",
            wraplength=680,
        ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(8, 0))
        ttk.Label(sync_tab, textvariable=self.sync_status_var, wraplength=700).pack(fill="x", pady=(12, 0))

    @property
    def current_template_id(self) -> str:
        return str(self.template_var.get() or "").strip().lower()

    @property
    def current_template(self):
        return self.templates[self.current_template_id]

    @property
    def current_qsos(self) -> list[dict]:
        return self._get_template_qsos(self.current_template_id)

    def _resolve_log_ops_template_id(self) -> str:
        tid = str(self.log_ops_template_var.get() or "").strip().lower()
        if tid in self.templates:
            return tid
        return self.current_template_id

    def _on_log_ops_template_selected(self, _event=None):
        if self.log_ops_template_combo is None:
            return
        selected_name = str(self.log_ops_template_combo.get() or "").strip()
        tid = self.template_name_to_id.get(selected_name)
        if not tid:
            return
        self.log_ops_template_var.set(tid)
        if self.log_ops_contest_combo is not None:
            self.log_ops_contest_combo.set("")
        self._refresh_db_combo_values()

    def _on_log_ops_contest_selected(self, _event=None):
        if self.log_ops_contest_combo is None:
            return
        selected_name = str(self.log_ops_contest_combo.get() or "").strip()
        tid = self.template_name_to_id.get(selected_name)
        if tid not in self.contest_template_ids:
            return
        self.log_ops_template_var.set(tid)
        if self.log_ops_template_combo is not None:
            self.log_ops_template_combo.set("")
        self._refresh_db_combo_values()

    def _refresh_db_combo_values(self):
        if self.db_combo is None:
            return
        tid = self._resolve_log_ops_template_id()
        dbs = self._list_template_databases(tid)
        self.db_combo.configure(values=dbs)
        current = self._template_db_filename(tid)
        try:
            self.db_combo.set(current if current in dbs else dbs[0])
        except Exception:
            pass

    def _selected_db_name_from_combo(self) -> str:
        if self.db_combo is None:
            return ""
        return str(self.db_combo.get() or "").strip()

    def _create_db_for_template(self):
        tid = self._resolve_log_ops_template_id()
        base = simpledialog.askstring(APP_TITLE, "Nombre de nueva base (sin extensión):")
        if not base:
            return
        safe = self._sanitize_db_basename(base)
        if not safe:
            messagebox.showerror(APP_TITLE, "Nombre inválido.")
            return
        filename = f"{tid}__{safe}{DEFAULT_DB_EXT}"
        path = self._template_db_path(tid, filename)
        if os.path.exists(path):
            messagebox.showinfo(APP_TITLE, "Esa base ya existe.")
            self._refresh_db_combo_values()
            return
        conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
        self._ensure_db_schema(conn)
        conn.close()
        self._refresh_db_combo_values()
        messagebox.showinfo(APP_TITLE, f"Base creada:\n{filename}")

    def _load_selected_db_for_template(self):
        tid = self._resolve_log_ops_template_id()
        name = self._selected_db_name_from_combo()
        if not name:
            return
        old_path = self._template_db_path(tid)
        self._close_db_connection_path(old_path)
        self._set_template_db_filename(tid, name)
        # force reload current template if matching
        if tid in self.logs_by_template:
            del self.logs_by_template[tid]
        if tid == self.current_template_id:
            self._set_template(tid)
        self._refresh_db_combo_values()
        self._schedule_settings_save()
        messagebox.showinfo(APP_TITLE, f"Base activa para '{self.templates[tid].TEMPLATE_NAME}':\n{name}")

    def _rename_selected_db_for_template(self):
        tid = self._resolve_log_ops_template_id()
        old = self._selected_db_name_from_combo()
        if not old:
            return
        if old == self._default_db_filename(tid):
            messagebox.showinfo(APP_TITLE, "La base por defecto no se puede renombrar.")
            return
        base = simpledialog.askstring(APP_TITLE, "Nuevo nombre de base (sin extensión):")
        if not base:
            return
        safe = self._sanitize_db_basename(base)
        if not safe:
            messagebox.showerror(APP_TITLE, "Nombre inválido.")
            return
        new = f"{tid}__{safe}{DEFAULT_DB_EXT}"
        old_path = self._template_db_path(tid, old)
        new_path = self._template_db_path(tid, new)
        if os.path.exists(new_path):
            messagebox.showerror(APP_TITLE, "Ya existe una base con ese nombre.")
            return
        self._close_db_connection_path(old_path)
        try:
            os.rename(old_path, new_path)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"No se pudo renombrar:\n{exc}")
            return
        if self._template_db_filename(tid) == old:
            self._set_template_db_filename(tid, new)
        self._refresh_db_combo_values()
        self._schedule_settings_save()

    def _delete_selected_db_for_template(self):
        tid = self._resolve_log_ops_template_id()
        name = self._selected_db_name_from_combo()
        if not name:
            return
        if name == self._default_db_filename(tid):
            messagebox.showinfo(APP_TITLE, "La base por defecto no se puede borrar.")
            return
        if not messagebox.askyesno(APP_TITLE, f"¿Borrar base '{name}'?"):
            return
        path = self._template_db_path(tid, name)
        self._close_db_connection_path(path)
        try:
            os.remove(path)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"No se pudo borrar:\n{exc}")
            return
        if self._template_db_filename(tid) == name:
            self._set_template_db_filename(tid, self._default_db_filename(tid))
            if tid in self.logs_by_template:
                del self.logs_by_template[tid]
            if tid == self.current_template_id:
                self._set_template(tid)
        self._refresh_db_combo_values()
        self._schedule_settings_save()

    def _legacy_template_json_path(self, template_id: str) -> str:
        safe_id = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(template_id or "default").strip().lower())
        return os.path.join(LOGS_DIR, f"{safe_id}.json")

    def _safe_template_id(self, template_id: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]+", "_", str(template_id or "default").strip().lower())

    def _default_db_filename(self, template_id: str) -> str:
        safe_id = self._safe_template_id(template_id)
        return f"{safe_id}{DEFAULT_DB_EXT}"

    def _sanitize_db_basename(self, name: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(name or "").strip())
        return cleaned.strip("_")

    def _template_db_dir(self, template_id: str) -> str:
        return os.path.join(LOGS_DIR, self._safe_template_id(template_id))

    def _ensure_template_db_storage(self, template_id: str):
        db_dir = self._template_db_dir(template_id)
        os.makedirs(db_dir, exist_ok=True)
        safe_id = self._safe_template_id(template_id)
        # One-time migration from old flat layout logs/*.sqlite
        for name in os.listdir(LOGS_DIR):
            src = os.path.join(LOGS_DIR, name)
            if not os.path.isfile(src):
                continue
            if not name.endswith(DEFAULT_DB_EXT):
                continue
            if not (name == f"{safe_id}{DEFAULT_DB_EXT}" or name.startswith(f"{safe_id}__")):
                continue
            dst = os.path.join(db_dir, name)
            if os.path.exists(dst):
                continue
            try:
                os.replace(src, dst)
            except Exception:
                continue

    def _normalize_db_filename_for_template(self, template_id: str, filename: str) -> str:
        safe_id = self._safe_template_id(template_id)
        base = os.path.basename(str(filename or "").strip())
        if not base:
            return self._default_db_filename(template_id)
        if not base.endswith(DEFAULT_DB_EXT):
            base = f"{base}{DEFAULT_DB_EXT}"
        if base == f"{safe_id}{DEFAULT_DB_EXT}" or base.startswith(f"{safe_id}__"):
            return base
        stem = os.path.splitext(base)[0]
        stem = self._sanitize_db_basename(stem) or "db"
        return f"{safe_id}__{stem}{DEFAULT_DB_EXT}"

    def _template_db_filename(self, template_id: str) -> str:
        current = str(self.template_db_map.get(template_id, "") or "").strip()
        if current:
            return self._normalize_db_filename_for_template(template_id, current)
        return self._default_db_filename(template_id)

    def _set_template_db_filename(self, template_id: str, filename: str):
        self.template_db_map[template_id] = self._normalize_db_filename_for_template(template_id, filename)

    def _template_db_path(self, template_id: str, filename: str | None = None) -> str:
        self._ensure_template_db_storage(template_id)
        fname = filename if filename else self._template_db_filename(template_id)
        normalized = self._normalize_db_filename_for_template(template_id, fname)
        return os.path.join(self._template_db_dir(template_id), normalized)

    def _list_template_databases(self, template_id: str) -> list[str]:
        self._ensure_template_db_storage(template_id)
        safe_id = self._safe_template_id(template_id)
        db_dir = self._template_db_dir(template_id)
        out: list[str] = []
        for name in os.listdir(db_dir):
            if not name.endswith(DEFAULT_DB_EXT):
                continue
            if name == f"{safe_id}{DEFAULT_DB_EXT}" or name.startswith(f"{safe_id}__"):
                out.append(name)
        if not out:
            out.append(self._default_db_filename(template_id))
        out = sorted(set(out))
        current = self._template_db_filename(template_id)
        if current in out:
            out.remove(current)
            out.insert(0, current)
        return out

    @staticmethod
    def _sync_payload_from_record(record: dict) -> tuple[str, dict]:
        template_id = str(record.get("template_id") or record.get("templateId") or "").strip().lower()
        nested = record.get("payload")
        payload = dict(nested) if isinstance(nested, dict) else dict(record)
        aliases = {
            "timestampUtc": "timestamp_utc",
            "freqHz": "freq_hz",
            "rstSent": "rst_sent",
            "rstReceived": "rst_recv",
            "powerW": "power_w",
            "serialSent": "serial_sent",
            "serialReceived": "serial_recv",
            "exchangeSent": "exchange_sent",
            "exchangeReceived": "exchange_recv",
            "countryName": "country_name",
            "countryIso": "country_iso",
            "updatedAt": "updated_at",
            "deletedAt": "deleted_at",
            "deviceId": "device_id",
            "qslInfo": "qsl_info",
        }
        for source, target in aliases.items():
            if target not in payload and source in payload:
                payload[target] = payload[source]
        for key in list(payload.keys()):
            if str(key).startswith("__"):
                payload.pop(key, None)
        payload["template_id"] = template_id
        return template_id, payload

    @staticmethod
    def _sync_identity(payload: dict) -> tuple[str, str, int, str] | None:
        timestamp = str(payload.get("timestamp_utc", "") or "").strip()
        call = str(payload.get("call", "") or "").strip().upper()
        frequency = int(payload.get("freq_hz", 0) or 0)
        mode = str(payload.get("mode", "") or "").strip().upper()
        if mode in {"SSB", "USB", "LSB"}:
            mode = "SSB"
        if len(timestamp) < 16 or not call or frequency <= 0 or not mode:
            return None
        return timestamp[:16], call, frequency, mode

    def _find_sync_identity_row(self, conn: sqlite3.Connection, payload: dict):
        identity = self._sync_identity(payload)
        if identity is None:
            return None
        minute, call, frequency, wanted_mode = identity
        candidates = conn.execute(
            """
            SELECT id, uuid, mode, revision, device_id FROM qsos
            WHERE deleted_at IS NULL AND substr(timestamp_utc, 1, 16)=?
              AND upper(call)=? AND freq_hz=?
            ORDER BY id ASC
            """,
            (minute, call, frequency),
        ).fetchall()
        for candidate in candidates:
            candidate_mode = str(candidate["mode"] or "").strip().upper()
            if candidate_mode in {"SSB", "USB", "LSB"}:
                candidate_mode = "SSB"
            if candidate_mode == wanted_mode:
                return candidate
        return None

    def _sync_open_db(self, template_id: str) -> sqlite3.Connection:
        conn = sqlite3.connect(self._template_db_path(template_id), timeout=20, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        self._ensure_db_schema(conn)
        return conn

    def _sync_snapshot(self) -> list[dict]:
        records: list[dict] = []
        with self._sync_lock:
            for template_id in list(self.template_ids):
                conn = self._sync_open_db(template_id)
                try:
                    rows = conn.execute(
                        """
                        SELECT uuid, timestamp_utc, call, band, mode, freq_hz, country_name, country_iso,
                               updated_at, deleted_at, revision, device_id, payload
                        FROM qsos ORDER BY id ASC
                        """
                    ).fetchall()
                    for row in rows:
                        try:
                            payload = json.loads(str(row["payload"] or "{}"))
                        except Exception:
                            payload = {}
                        if not isinstance(payload, dict):
                            payload = {}
                        payload = {k: v for k, v in payload.items() if not str(k).startswith("__")}
                        payload.update(
                            {
                                "uuid": str(row["uuid"] or ""),
                                "template_id": template_id,
                                "timestamp_utc": str(payload.get("timestamp_utc") or row["timestamp_utc"] or ""),
                                "call": str(payload.get("call") or row["call"] or ""),
                                "band": str(payload.get("band") or row["band"] or ""),
                                "mode": str(payload.get("mode") or row["mode"] or ""),
                                "freq_hz": int(payload.get("freq_hz") or row["freq_hz"] or 0),
                                "country_name": str(payload.get("country_name") or row["country_name"] or ""),
                                "country_iso": str(payload.get("country_iso") or row["country_iso"] or ""),
                                "updated_at": int(row["updated_at"] or 0),
                                "deleted_at": row["deleted_at"],
                                "revision": int(row["revision"] or 0),
                                "device_id": str(row["device_id"] or ""),
                            }
                        )
                        records.append(payload)
                finally:
                    conn.close()
        return records

    def _merge_sync_records(self, records: list) -> tuple[int, int, set[str]]:
        if len(records) > 200_000:
            raise ValueError("Demasiados registros en una sola sincronización")
        applied = 0
        skipped = 0
        changed_templates: set[str] = set()
        grouped: dict[str, list[dict]] = {}
        for raw in records:
            if not isinstance(raw, dict):
                skipped += 1
                continue
            template_id, payload = self._sync_payload_from_record(raw)
            if template_id not in self.templates:
                skipped += 1
                continue
            record_uuid = str(payload.get("uuid", "") or "").strip()
            if not record_uuid:
                skipped += 1
                continue
            try:
                uuid.UUID(record_uuid)
            except ValueError:
                skipped += 1
                continue
            payload["uuid"] = record_uuid
            grouped.setdefault(template_id, []).append(payload)

        with self._sync_lock:
            for template_id, items in grouped.items():
                conn = self._sync_open_db(template_id)
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    for payload in items:
                        record_uuid = payload["uuid"]
                        incoming_revision = int(payload.get("revision", 0) or payload.get("updated_at", 0) or 0)
                        if incoming_revision <= 0:
                            incoming_revision = self._next_sync_revision()
                        incoming_updated = int(payload.get("updated_at", 0) or incoming_revision)
                        incoming_device = str(payload.get("device_id", "") or "remote")
                        deleted_at = payload.get("deleted_at")
                        if deleted_at in ("", 0, "0"):
                            deleted_at = None
                        elif deleted_at is not None:
                            deleted_at = int(deleted_at)
                        existing = conn.execute(
                            "SELECT id, revision, device_id FROM qsos WHERE uuid=?", (record_uuid,)
                        ).fetchone()
                        duplicate_identity = None
                        if existing is None and deleted_at is None:
                            duplicate_identity = self._find_sync_identity_row(conn, payload)
                        if duplicate_identity is not None:
                            # The same imported QSO can have different UUIDs on two
                            # devices (notably SSB on PC versus USB on Android).
                            # Keep the server's canonical record and publish a newer
                            # tombstone for the duplicate UUID so every peer removes it.
                            tombstone_revision = max(self._next_sync_revision(), incoming_revision + 1)
                            self._last_revision = max(self._last_revision, tombstone_revision)
                            payload.update(
                                revision=tombstone_revision,
                                updated_at=tombstone_revision,
                                deleted_at=tombstone_revision,
                                device_id=self.sync_device_id,
                                template_id=template_id,
                            )
                            db_payload = self._db_payload_from_qso(payload)
                            conn.execute(
                                """
                                INSERT INTO qsos(
                                    uuid, timestamp_utc, call, band, mode, freq_hz, country_name, country_iso,
                                    updated_at, deleted_at, revision, device_id, payload
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """,
                                (
                                    record_uuid,
                                    str(payload.get("timestamp_utc", "") or ""),
                                    str(payload.get("call", "") or "").upper(),
                                    str(payload.get("band", "") or ""),
                                    str(payload.get("mode", "") or "").upper(),
                                    int(payload.get("freq_hz", 0) or 0),
                                    str(payload.get("country_name", "") or ""),
                                    str(payload.get("country_iso", "") or ""),
                                    tombstone_revision,
                                    tombstone_revision,
                                    tombstone_revision,
                                    self.sync_device_id,
                                    db_payload,
                                ),
                            )
                            applied += 1
                            changed_templates.add(template_id)
                            continue
                        if existing is not None:
                            current_key = (int(existing["revision"] or 0), str(existing["device_id"] or ""))
                            incoming_key = (incoming_revision, incoming_device)
                            if incoming_key <= current_key:
                                skipped += 1
                                continue
                        call = str(payload.get("call", "") or "").strip().upper()
                        if deleted_at is None:
                            country, iso = self._country_info_for_call(call, template_id)
                            payload["country_name"] = country
                            payload["country_iso"] = iso
                        payload.update(
                            revision=incoming_revision,
                            updated_at=incoming_updated,
                            deleted_at=deleted_at,
                            device_id=incoming_device,
                            template_id=template_id,
                        )
                        db_payload = self._db_payload_from_qso(payload)
                        values = (
                            str(payload.get("timestamp_utc", "") or ""),
                            call,
                            str(payload.get("band", "") or ""),
                            str(payload.get("mode", "") or "").upper(),
                            int(payload.get("freq_hz", 0) or 0),
                            str(payload.get("country_name", "") or ""),
                            str(payload.get("country_iso", "") or ""),
                            incoming_updated,
                            deleted_at,
                            incoming_revision,
                            incoming_device,
                            db_payload,
                        )
                        if existing is None:
                            conn.execute(
                                """
                                INSERT INTO qsos(
                                    uuid, timestamp_utc, call, band, mode, freq_hz, country_name, country_iso,
                                    updated_at, deleted_at, revision, device_id, payload
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """,
                                (record_uuid,) + values,
                            )
                        else:
                            conn.execute(
                                """
                                UPDATE qsos SET timestamp_utc=?, call=?, band=?, mode=?, freq_hz=?,
                                    country_name=?, country_iso=?, updated_at=?, deleted_at=?, revision=?,
                                    device_id=?, payload=? WHERE uuid=?
                                """,
                                values + (record_uuid,),
                            )
                        applied += 1
                        changed_templates.add(template_id)
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
                finally:
                    conn.close()
        return applied, skipped, changed_templates

    def _schedule_sync_refresh(self, changed_templates: set[str]):
        if not changed_templates:
            return

        def refresh():
            for template_id in changed_templates:
                self.logs_by_template.pop(template_id, None)
            if self.current_template_id in changed_templates:
                self._set_template(self.current_template_id)

        try:
            self.root.after(0, refresh)
        except Exception:
            pass

    def _handle_sync_request(self, payload: dict, client_ip: str) -> dict:
        protocol = int(payload.get("protocol", 0) or 0)
        if protocol != SYNC_PROTOCOL_VERSION:
            raise ValueError(f"Versión de protocolo incompatible: {protocol}")
        incoming = payload.get("records", [])
        if not isinstance(incoming, list):
            raise ValueError("records debe ser una lista")
        applied, skipped, changed = self._merge_sync_records(incoming)
        self._schedule_sync_refresh(changed)
        records = self._sync_snapshot()
        return {
            "ok": True,
            "protocol": SYNC_PROTOCOL_VERSION,
            "server_device_id": self.sync_device_id,
            "client_ip": client_ip,
            "applied": applied,
            "skipped": skipped,
            "records": records,
        }

    @staticmethod
    def _local_ipv4_addresses() -> list[str]:
        addresses: set[str] = set()
        try:
            import fcntl
            import struct

            for _index, interface in socket.if_nameindex():
                lowered = interface.lower()
                if lowered == "lo" or lowered.startswith(("docker", "br-", "veth")) or "warp" in lowered:
                    continue
                probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                try:
                    packed = struct.pack("256s", interface.encode("utf-8")[:15])
                    value = socket.inet_ntoa(fcntl.ioctl(probe.fileno(), 0x8915, packed)[20:24])
                    if value and not value.startswith("127."):
                        addresses.add(value)
                except OSError:
                    pass
                finally:
                    probe.close()
        except Exception:
            pass
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                value = str(info[4][0] or "").strip()
                if value and not value.startswith("127."):
                    addresses.add(value)
        except Exception:
            pass
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                probe.connect(("8.8.8.8", 80))
                value = str(probe.getsockname()[0] or "").strip()
                if value and not value.startswith(("127.", "172.16.")):
                    addresses.add(value)
            finally:
                probe.close()
        except Exception:
            pass
        return sorted(addresses)

    def _stop_sync_server(self):
        server = self._sync_server
        self._sync_server = None
        if server is not None:
            server.stop()

    def _apply_sync_server_settings(self, silent: bool = False):
        self._stop_sync_server()
        if not bool(self.sync_server_enabled_var.get()):
            self.sync_status_var.set("Sincronización: servidor detenido")
            self._schedule_settings_save()
            return
        host = self.sync_server_host_var.get().strip() or DEFAULT_SYNC_HOST
        try:
            port = int(self.sync_server_port_var.get().strip() or DEFAULT_SYNC_PORT)
            if not (1 <= port <= 65535):
                raise ValueError
        except ValueError:
            self.sync_server_enabled_var.set(False)
            self.sync_status_var.set("Sincronización: puerto de servidor no válido")
            if not silent:
                messagebox.showerror(APP_TITLE, "El puerto del servidor debe estar entre 1 y 65535.")
            return
        try:
            server = LogSyncServer(host, port, self.sync_token_var.get(), self._handle_sync_request)
            server.start()
            self._sync_server = server
            shown_host = host if host not in {"0.0.0.0", "::"} else "todas las interfaces"
            self.sync_status_var.set(f"Servidor activo en {shown_host}:{port}")
            self._schedule_settings_save()
        except Exception as exc:
            self.sync_server_enabled_var.set(False)
            self.sync_status_var.set(f"No se pudo iniciar el servidor: {exc}")
            if not silent:
                messagebox.showerror(APP_TITLE, f"No se pudo iniciar el servidor de sincronización:\n{exc}")

    def sync_now(self):
        if self._sync_inflight:
            return
        host = self.sync_remote_host_var.get().strip()
        if not host:
            messagebox.showerror(APP_TITLE, "Indica la IP o el nombre del equipo servidor.")
            return
        try:
            port = int(self.sync_remote_port_var.get().strip() or DEFAULT_SYNC_PORT)
            if not (1 <= port <= 65535):
                raise ValueError
        except ValueError:
            messagebox.showerror(APP_TITLE, "El puerto remoto debe estar entre 1 y 65535.")
            return
        if "://" not in host:
            host = f"http://{host}"
        try:
            parsed = urllib.parse.urlsplit(host)
            embedded_port = parsed.port
        except ValueError:
            parsed = None
            embedded_port = None
        if parsed is None or parsed.scheme not in {"http", "https"} or not parsed.hostname:
            messagebox.showerror(APP_TITLE, "La dirección del servidor no es válida.")
            return
        netloc = parsed.netloc
        if embedded_port is None:
            hostname = parsed.hostname or ""
            if ":" in hostname and not hostname.startswith("["):
                hostname = f"[{hostname}]"
            netloc = f"{hostname}:{port}"
        url = urllib.parse.urlunsplit((parsed.scheme, netloc, "/v1/sync", "", ""))
        token = self.sync_token_var.get()
        self._sync_inflight = True
        self.sync_status_var.set("Sincronizando…")
        self._save_settings()

        def finish(message: str, error: bool = False):
            self._sync_inflight = False
            self.sync_status_var.set(message)
            if error:
                messagebox.showerror(APP_TITLE, message)
            else:
                messagebox.showinfo(APP_TITLE, message)

        def worker():
            try:
                outgoing = self._sync_snapshot()
                body = json.dumps(
                    {
                        "protocol": SYNC_PROTOCOL_VERSION,
                        "device_id": self.sync_device_id,
                        "records": outgoing,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
                request = urllib.request.Request(url, data=body, method="POST")
                request.add_header("Content-Type", "application/json; charset=utf-8")
                if token:
                    request.add_header("X-NMN1M-Token", token)
                with urllib.request.urlopen(request, timeout=60) as response:
                    result = json.loads(response.read(SYNC_MAX_BODY_BYTES + 1).decode("utf-8"))
                if not isinstance(result, dict) or not result.get("ok"):
                    raise ValueError(str(result.get("error", "Respuesta no válida del servidor")))
                if int(result.get("protocol", 0) or 0) != SYNC_PROTOCOL_VERSION:
                    raise ValueError("El servidor usa una versión de sincronización incompatible")
                incoming = result.get("records", [])
                if not isinstance(incoming, list):
                    raise ValueError("El servidor devolvió un registro no válido")
                applied, _skipped, changed = self._merge_sync_records(incoming)
                self._schedule_sync_refresh(changed)
                message = (
                    f"Sincronización completada: {len(outgoing)} enviados, "
                    f"{len(incoming)} recibidos y {applied} cambios aplicados."
                )
                self.root.after(0, lambda: finish(message))
            except urllib.error.HTTPError as exc:
                try:
                    detail = json.loads(exc.read().decode("utf-8")).get("error", str(exc))
                except Exception:
                    detail = str(exc)
                message = f"Error de sincronización: {detail}"
                self.root.after(0, lambda: finish(message, True))
            except Exception as exc:
                message = f"Error de sincronización: {exc}"
                self.root.after(0, lambda: finish(message, True))

        threading.Thread(target=worker, daemon=True, name="nmn1m-sync-client").start()

    def _ensure_db_schema(self, conn: sqlite3.Connection):
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS qsos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT,
                timestamp_utc TEXT,
                call TEXT,
                band TEXT,
                mode TEXT,
                freq_hz INTEGER,
                country_name TEXT,
                country_iso TEXT,
                updated_at INTEGER NOT NULL DEFAULT 0,
                deleted_at INTEGER,
                revision INTEGER NOT NULL DEFAULT 0,
                device_id TEXT NOT NULL DEFAULT '',
                payload TEXT NOT NULL
            )
            """
        )
        existing_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(qsos)").fetchall()}
        additions = {
            "uuid": "TEXT",
            "updated_at": "INTEGER NOT NULL DEFAULT 0",
            "deleted_at": "INTEGER",
            "revision": "INTEGER NOT NULL DEFAULT 0",
            "device_id": "TEXT NOT NULL DEFAULT ''",
        }
        for column, definition in additions.items():
            if column not in existing_columns:
                conn.execute(f"ALTER TABLE qsos ADD COLUMN {column} {definition}")
        now_ms = int(time.time() * 1000)
        default_device = str(self.sync_device_id or "desktop")
        rows_to_migrate = conn.execute(
            """
            SELECT id, uuid, updated_at, revision, device_id FROM qsos
            WHERE uuid IS NULL OR uuid='' OR updated_at=0 OR revision=0 OR device_id=''
            """
        ).fetchall()
        for row in rows_to_migrate:
            record_uuid = str(row[1] or "").strip() or str(uuid.uuid4())
            updated_at = int(row[2] or 0) or now_ms
            revision = int(row[3] or 0) or updated_at
            device_id = str(row[4] or "").strip() or default_device
            conn.execute(
                "UPDATE qsos SET uuid=?, updated_at=?, revision=?, device_id=? WHERE id=?",
                (record_uuid, updated_at, revision, device_id, int(row[0])),
            )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_qsos_call ON qsos(call)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_qsos_band_mode ON qsos(band, mode)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_qsos_utc ON qsos(timestamp_utc)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_qsos_country ON qsos(country_name)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_qsos_uuid ON qsos(uuid)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_qsos_revision ON qsos(revision)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_qsos_deleted ON qsos(deleted_at)")
        conn.commit()

    def _next_sync_revision(self) -> int:
        with self._sync_lock:
            current = int(time.time() * 1000)
            self._last_revision = max(current, int(self._last_revision or 0) + 1)
            return self._last_revision

    def _db_connect(self, template_id: str) -> sqlite3.Connection:
        path = self._template_db_path(template_id)
        conn = self._db_connections.get(path)
        if conn is not None:
            return conn
        os.makedirs(LOGS_DIR, exist_ok=True)
        conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        self._ensure_db_schema(conn)
        self._db_connections[path] = conn
        return conn

    def _ensure_all_template_default_dbs(self):
        for tid in self.template_ids:
            path = self._template_db_path(tid)
            if os.path.exists(path):
                continue
            try:
                conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
                self._ensure_db_schema(conn)
                conn.close()
            except Exception:
                continue

    def _close_db_connection_path(self, path: str):
        conn = self._db_connections.pop(path, None)
        if conn is None:
            return
        try:
            conn.close()
        except Exception:
            pass

    def _db_payload_from_qso(self, qso: dict) -> str:
        safe = {k: v for k, v in qso.items() if not str(k).startswith("__")}
        return json.dumps(safe, ensure_ascii=False)

    def _db_insert_qso(self, template_id: str, qso: dict) -> int:
        country, iso = self._country_info_for_call(str(qso.get("call", "")), template_id)
        qso["country_name"] = country
        qso["country_iso"] = iso
        record_uuid = str(qso.get("uuid", "") or "").strip() or str(uuid.uuid4())
        revision = int(qso.get("revision", 0) or 0) or self._next_sync_revision()
        updated_at = int(qso.get("updated_at", 0) or 0) or revision
        device_id = str(qso.get("device_id", "") or "").strip() or str(self.sync_device_id or "desktop")
        deleted_at = qso.get("deleted_at")
        qso.update(
            uuid=record_uuid,
            revision=revision,
            updated_at=updated_at,
            device_id=device_id,
            deleted_at=deleted_at,
        )
        payload = self._db_payload_from_qso(qso)
        conn = self._db_connect(template_id)
        cur = conn.execute(
            """
            INSERT INTO qsos(
                uuid, timestamp_utc, call, band, mode, freq_hz, country_name, country_iso,
                updated_at, deleted_at, revision, device_id, payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_uuid,
                str(qso.get("timestamp_utc", "")),
                str(qso.get("call", "")),
                str(qso.get("band", "")),
                str(qso.get("mode", "")),
                int(qso.get("freq_hz", 0) or 0),
                str(qso.get("country_name", "")),
                str(qso.get("country_iso", "")),
                updated_at,
                deleted_at,
                revision,
                device_id,
                payload,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)

    def _db_update_qso(self, template_id: str, qso: dict):
        rowid = qso.get("__db_id")
        if not rowid:
            qso["__db_id"] = self._db_insert_qso(template_id, qso)
            return
        country, iso = self._country_info_for_call(str(qso.get("call", "")), template_id)
        qso["country_name"] = country
        qso["country_iso"] = iso
        conn = self._db_connect(template_id)
        existing = conn.execute("SELECT uuid FROM qsos WHERE id=?", (int(rowid),)).fetchone()
        existing_uuid = str(existing[0] or "").strip() if existing is not None else ""
        revision = self._next_sync_revision()
        qso["uuid"] = str(qso.get("uuid", "") or "").strip() or existing_uuid or str(uuid.uuid4())
        qso["updated_at"] = revision
        qso["revision"] = revision
        qso["deleted_at"] = None
        qso["device_id"] = str(self.sync_device_id or "desktop")
        payload = self._db_payload_from_qso(qso)
        conn.execute(
            """
            UPDATE qsos
            SET uuid=?, timestamp_utc=?, call=?, band=?, mode=?, freq_hz=?, country_name=?, country_iso=?,
                updated_at=?, deleted_at=NULL, revision=?, device_id=?, payload=?
            WHERE id=?
            """,
            (
                qso["uuid"],
                str(qso.get("timestamp_utc", "")),
                str(qso.get("call", "")),
                str(qso.get("band", "")),
                str(qso.get("mode", "")),
                int(qso.get("freq_hz", 0) or 0),
                str(qso.get("country_name", "")),
                str(qso.get("country_iso", "")),
                revision,
                revision,
                qso["device_id"],
                payload,
                int(rowid),
            ),
        )
        conn.commit()

    def _db_delete_qso(self, template_id: str, qso: dict):
        rowid = qso.get("__db_id")
        if not rowid:
            return
        revision = self._next_sync_revision()
        conn = self._db_connect(template_id)
        conn.execute(
            "UPDATE qsos SET deleted_at=?, updated_at=?, revision=?, device_id=? WHERE id=?",
            (revision, revision, revision, str(self.sync_device_id or "desktop"), int(rowid)),
        )
        conn.commit()

    def _load_template_log(self, template_id: str) -> list[dict]:
        conn = self._db_connect(template_id)
        out: list[dict] = []
        try:
            rows = conn.execute(
                """
                SELECT id, uuid, payload, timestamp_utc, call, band, mode, freq_hz, country_name, country_iso,
                       updated_at, deleted_at, revision, device_id
                FROM qsos
                WHERE deleted_at IS NULL
                ORDER BY id ASC
                """
            ).fetchall()
            for row in rows:
                try:
                    payload = json.loads(str(row["payload"] or "{}"))
                except Exception:
                    payload = {}
                if not isinstance(payload, dict):
                    continue
                payload["__db_id"] = int(row["id"])
                payload["uuid"] = str(row["uuid"] or "")
                payload["updated_at"] = int(row["updated_at"] or 0)
                payload["deleted_at"] = row["deleted_at"]
                payload["revision"] = int(row["revision"] or 0)
                payload["device_id"] = str(row["device_id"] or "")
                if not payload.get("timestamp_utc"):
                    payload["timestamp_utc"] = str(row["timestamp_utc"] or "")
                if not payload.get("call"):
                    payload["call"] = str(row["call"] or "")
                if not payload.get("band"):
                    payload["band"] = str(row["band"] or "")
                if not payload.get("mode"):
                    payload["mode"] = str(row["mode"] or "")
                if not payload.get("freq_hz"):
                    try:
                        payload["freq_hz"] = int(row["freq_hz"] or 0)
                    except Exception:
                        payload["freq_hz"] = 0
                c_name = str(payload.get("country_name") or row["country_name"] or "")
                c_iso = str(payload.get("country_iso") or row["country_iso"] or "")
                payload["country_name"] = c_name
                payload["country_iso"] = c_iso
                payload["__country_name"] = c_name
                payload["__country_iso"] = c_iso
                payload["__country_checked"] = bool(c_name or c_iso)
                out.append(payload)
        except Exception:
            pass

        # One-time migration from legacy JSON only if the DB has never contained
        # records. Tombstones must not make an old JSON log reappear.
        try:
            database_is_empty = int(conn.execute("SELECT COUNT(*) FROM qsos").fetchone()[0]) == 0
        except Exception:
            database_is_empty = False
        if database_is_empty:
            legacy = self._legacy_template_json_path(template_id)
            if os.path.isfile(legacy):
                try:
                    with open(legacy, "r", encoding="utf-8") as f:
                        old = json.load(f)
                    if isinstance(old, list):
                        for item in old:
                            if not isinstance(item, dict):
                                continue
                            rowid = self._db_insert_qso(template_id, item)
                            item["__db_id"] = rowid
                            out.append(item)
                except Exception:
                    pass
        return out

    def _save_template_log(self, template_id: str) -> None:
        # Persistence is handled per-row on create/update/delete.
        return

    def _get_template_qsos(self, template_id: str) -> list[dict]:
        if template_id not in self.logs_by_template:
            self.logs_by_template[template_id] = self._load_template_log(template_id)
        return self.logs_by_template[template_id]

    def _set_template(self, template_id: str, initialize: bool = False):
        template_id = str(template_id or "").strip().lower()
        if template_id not in self.templates:
            return

        old_id = self.current_template_id
        if old_id and old_id in self.templates:
            self._save_template_log(old_id)
        self.template_var.set(template_id)
        self._get_template_qsos(template_id)
        if old_id != template_id:
            self.selected_qso_index = None

        tpl = self.templates[template_id]
        self._build_dynamic_form(tpl)
        self._configure_tree_columns(tpl)
        self._rebuild_dupe_index()
        self._page_index = 0
        self._refresh_qso_table()
        self._recompute_next_serial()
        self._update_stats()

        if self.template_combo is not None:
            try:
                self.template_combo.set(tpl.TEMPLATE_NAME if template_id in self.main_template_ids else "")
            except tk.TclError:
                pass
        if self.contest_template_combo is not None:
            try:
                self.contest_template_combo.set(tpl.TEMPLATE_NAME if template_id in self.contest_template_ids else "")
            except tk.TclError:
                pass
        if self.log_ops_template_combo is not None:
            try:
                self.log_ops_template_combo.set(tpl.TEMPLATE_NAME if template_id in self.main_template_ids else "")
            except tk.TclError:
                pass
        if self.log_ops_contest_combo is not None:
            try:
                self.log_ops_contest_combo.set(tpl.TEMPLATE_NAME if template_id in self.contest_template_ids else "")
            except tk.TclError:
                pass
        self.log_ops_template_var.set(template_id)
        self._refresh_db_combo_values()

        if initialize:
            if not self.contest_var.get().strip():
                self.contest_var.set(str(getattr(tpl, "DEFAULT_CONTEST_TEXT", "") or ""))
        else:
            self.contest_var.set(str(getattr(tpl, "DEFAULT_CONTEST_TEXT", "") or ""))

        self._schedule_settings_save()
        self._update_template_header()
        self._refresh_template_menus()
        self._schedule_map_refresh(30)

    def _update_template_header(self):
        tid = self.current_template_id
        if tid in self.templates:
            name = str(self.templates[tid].TEMPLATE_NAME or tid)
        else:
            name = "-"
        self.template_header_var.set(name)

    def _build_dynamic_form(self, tpl):
        for child in self.form_fields_frame.winfo_children():
            child.destroy()
        self.field_vars.clear()
        self.field_entries.clear()

        row = 0
        for field in tpl.FORM_FIELDS:
            key = str(field.get("key") or "").strip()
            if not key:
                continue
            label = str(field.get("label") or key)
            default_value = str(field.get("default") or "")
            width = int(field.get("width", 26) or 26)
            var = tk.StringVar(value=default_value)
            self.field_vars[key] = var
            ttk.Label(self.form_fields_frame, text=label).grid(row=row, column=0, sticky="w", pady=2)
            entry = ttk.Entry(self.form_fields_frame, textvariable=var, width=width)
            entry.grid(row=row, column=1, sticky="ew", padx=4, pady=2)
            entry.bind("<Return>", self._on_qso_entry_return)
            self.field_entries[key] = entry
            if key == "call":
                entry.bind("<Return>", self._on_call_entry_return)
                var.trace_add("write", lambda *_: self.check_dupe())
                var.trace_add("write", lambda *_: self._on_call_filter_changed())
                var.trace_add("write", lambda *_: self._update_call_country_display())
                var.trace_add("write", lambda *_: self._schedule_hamqth_autolookup())
                var.trace_add("write", lambda *_: self._schedule_map_refresh(140))
                self.call_var = var
            if key == "rst_sent":
                var.trace_add("write", lambda *_: self._refresh_serial_fields())
            row += 1
        self.form_fields_frame.columnconfigure(1, weight=1)
        has_serial_sent = any(str(f.get("key") or "") == "serial_sent" for f in tpl.FORM_FIELDS)
        try:
            if has_serial_sent:
                self.auto_serial_check.grid()
                self.auto_serial_check.configure(state="normal")
            else:
                self.auto_serial_check.grid_remove()
        except tk.TclError:
            pass
        self._refresh_serial_fields()

    def _configure_tree_columns(self, tpl):
        ordered = list(tpl.TREE_COLUMNS)
        utc_cols = [c for c in ordered if str(c[0]) == "utc"]
        ordered = [c for c in ordered if str(c[0]) != "utc"] + utc_cols
        self._ordered_tree_base_cols = [str(c[0]) for c in ordered]
        cols = [c[0] for c in ordered]
        has_call_col = any(str(col_id) == "call" for col_id, _label, _width in ordered)
        self._tree_flag_icon_mode = False
        self.tree.configure(show="headings")
        if has_call_col:
            cols.extend(["__flag", "__country"])
        self.tree.configure(columns=cols)
        for col in cols:
            self.tree.heading(col, text="")
            self.tree.column(col, width=80, anchor="w")
        for col_id, label, width in ordered:
            self.tree.heading(col_id, text=label, command=lambda c=col_id: self._toggle_sort(c))
            self.tree.column(col_id, width=int(width), anchor="w")
        if has_call_col:
            self.tree.heading("__flag", text="Bandera", command=lambda c="__flag": self._toggle_sort(c))
            self.tree.column("__flag", width=64, anchor="center")
            self.tree.heading("__country", text="País", command=lambda c="__country": self._toggle_sort(c))
            self.tree.column("__country", width=170, anchor="w")

    def _toggle_sort(self, column_id: str):
        column_id = str(column_id or "").strip()
        if not column_id:
            return
        if self.sort_column_id == column_id:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_column_id = column_id
            self.sort_desc = False
        self._page_index = 0
        self._refresh_qso_table()

    def _on_qso_entry_return(self, _event=None):
        self.save_qso()
        return "break"

    def _parse_call_control_command(self, text: str):
        raw = str(text or "").strip()
        if not raw:
            return None
        upper = raw.upper()

        mode_aliases = {
            "USB": "USB",
            "LSB": "LSB",
            "CW": "CW",
            "AM": "AM",
            "FM": "FM",
            "DIGU": "DIGU",
            "DIGL": "DIGL",
            "FT8": "DIGU",
            "FT4": "DIGU",
        }
        if upper in mode_aliases:
            return ("mode", mode_aliases[upper])

        if re.fullmatch(r"\d{1,2}(?:[.,]\d{1,6})?", raw):
            mhz = float(raw.replace(",", "."))
            if 0.1 <= mhz <= 60.0:
                return ("freq", int(round(mhz * 1_000_000.0)))

        return None

    def _on_call_entry_return(self, _event=None):
        call_text = self.get_form_value("call")
        cmd = self._parse_call_control_command(call_text)
        if not cmd:
            return self._on_qso_entry_return(_event)
        if not self.client or not self.connected:
            self.status_var.set("No hay conexión con rigctld para aplicar el comando de Call")
            return "break"

        try:
            kind, value = cmd
            if kind == "freq":
                freq_hz = int(value)
                self.client.set_freq(freq_hz)
                self.current_freq_hz = freq_hz
                self.current_band = self.band_from_freq(freq_hz)
                self.freq_var.set(self.format_freq(freq_hz))
                self.band_var.set(self.current_band)
                self.status_var.set(f"Frecuencia ajustada desde Call: {freq_hz / 1_000_000:.3f} MHz")
            elif kind == "mode":
                mode = str(value).upper()
                self.client.set_mode(mode)
                self.current_mode = mode
                self.mode_var.set(mode)
                self.status_var.set(f"Modo ajustado desde Call: {mode}")
            self.root.after(180, lambda: self.poll_rig_once(silent=True))
            self.check_dupe()
        except Exception as exc:
            self.status_var.set(f"Error aplicando comando de Call: {exc}")
        return "break"

    def _is_editing_status_fields(self) -> bool:
        try:
            focused = self.root.focus_get()
            return focused in {self.freq_entry, self.band_entry, self.mode_entry}
        except Exception:
            return False

    def _is_editing_selected_call(self) -> bool:
        if self.selected_qso_index is None:
            return False
        try:
            call_entry = self.field_entries.get("call")
            if call_entry is None:
                return False
            focused = self.root.focus_get()
            return focused == call_entry
        except Exception:
            return False

    def _on_call_filter_changed(self):
        if self._suppress_call_filter_refresh:
            return
        # While editing CALL of an already selected QSO, do not trigger
        # live filter refresh, otherwise the row can be deselected mid-edit.
        if self._is_editing_selected_call():
            return
        self._map_location_filter = ""
        self._page_index = 0
        total = len(self.current_qsos)
        if total >= 5000:
            delay = 320
        elif total >= 2000:
            delay = 240
        elif total >= 800:
            delay = 170
        else:
            delay = 120
        self._schedule_qso_table_refresh(delay_ms=delay)

    def _schedule_qso_table_refresh(self, delay_ms: int = 120):
        try:
            if self._refresh_table_after_id is not None:
                self.root.after_cancel(self._refresh_table_after_id)
        except Exception:
            pass
        try:
            self._refresh_table_after_id = self.root.after(max(0, int(delay_ms)), self._refresh_qso_table)
        except Exception:
            self._refresh_qso_table()

    def _cancel_qso_table_render(self):
        try:
            if self._table_render_after_id is not None:
                self.root.after_cancel(self._table_render_after_id)
        except Exception:
            pass
        self._table_render_after_id = None
        self._table_render_token += 1
        self._table_render_rows = []
        self._table_render_pos = 0

    def _compute_filtered_rows(self, qsos_snapshot: list[dict], filter_text: str, sort_col: str | None, sort_desc: bool) -> list[tuple[int, dict]]:
        rows: list[tuple[int, dict]] = []
        loc_filter = str(getattr(self, "_map_location_filter", "") or "").strip().upper()
        if filter_text:
            for idx, qso in enumerate(qsos_snapshot):
                if filter_text not in str(qso.get("call", "")).lower():
                    continue
                if loc_filter and self._qso_locator(qso).upper() != loc_filter:
                    continue
                rows.append((idx, qso))
        else:
            for idx, qso in enumerate(qsos_snapshot):
                if loc_filter and self._qso_locator(qso).upper() != loc_filter:
                    continue
                rows.append((idx, qso))
        if sort_col:
            rows.sort(
                key=lambda pair: self._qso_value_for_column(pair[1], sort_col),
                reverse=bool(sort_desc),
            )
        return rows

    def _compute_filtered_rows_worker(
        self,
        token: int,
        qsos_snapshot: list[dict],
        filter_text: str,
        sort_col: str | None,
        sort_desc: bool,
        template_id: str,
    ):
        started = time.monotonic()
        rows = self._compute_filtered_rows(qsos_snapshot, filter_text, sort_col, sort_desc)
        elapsed_ms = int((time.monotonic() - started) * 1000.0)

        def _apply():
            if token != self._refresh_compute_token:
                return
            if template_id != self.current_template_id:
                return
            self._apply_filtered_rows(rows)
            try:
                if self.connected:
                    self.status_var.set(
                        f"Conectado | {self.current_band} | {self.current_mode} | {self.format_freq(self._safe_current_freq())} | Tabla {elapsed_ms} ms"
                    )
            except Exception:
                pass

        try:
            self.root.after(0, _apply)
        except Exception:
            pass

    def _apply_filtered_rows(self, rows: list[tuple[int, dict]]):
        self._all_filtered_rows = rows
        total_rows = len(rows)
        total_pages = max(1, (total_rows + self._page_size - 1) // self._page_size)
        if self._page_index >= total_pages:
            self._page_index = total_pages - 1
        if self._page_index < 0:
            self._page_index = 0
        start = self._page_index * self._page_size
        end = min(start + self._page_size, total_rows)
        page_rows = rows[start:end]
        # With pagination enabled, always resolve country/flag on-page for correctness.
        self._country_render_lite = False
        self._table_render_rows = page_rows
        self._table_render_pos = 0
        self._table_render_token += 1
        self._render_qso_rows_chunk(self._table_render_token)
        self.page_info_var.set(f"Página {self._page_index + 1}/{total_pages} ({total_rows} QSOs)")
        self._schedule_map_refresh(30)

    def _prev_page(self):
        if self._page_index <= 0:
            return
        self._page_index -= 1
        self._apply_filtered_rows(list(self._all_filtered_rows))

    def _next_page(self):
        total_rows = len(self._all_filtered_rows)
        total_pages = max(1, (total_rows + self._page_size - 1) // self._page_size)
        if self._page_index >= total_pages - 1:
            return
        self._page_index += 1
        self._apply_filtered_rows(list(self._all_filtered_rows))

    def _qso_value_for_column(self, qso: dict, column_id: str):
        if column_id in ("__flag", "__country"):
            country, _iso = self._country_info_for_qso_cached(qso)
            if column_id == "__flag":
                _country, iso = self._country_info_for_qso_cached(qso)
                return self._flag_from_iso(iso).lower()
            return country.lower()
        mapping = {
            "utc": "timestamp_utc",
            "call": "call",
            "band": "band",
            "mode": "mode",
            "freq": "freq_hz",
            "snt": "rst_sent",
            "sent": "serial_sent",
            "rcv": "rst_recv",
            "recv": "serial_recv",
            "name": "name",
            "qth": "qth",
            "grid": "grid",
            "notes": "notes",
        }
        key = mapping.get(column_id, column_id)
        value = qso.get(key, "")
        if key in ("freq_hz", "serial_sent") and str(value).strip():
            try:
                return int(value)
            except Exception:
                return str(value)
        return str(value).lower()

    def _country_info_for_qso_cached(self, qso: dict) -> tuple[str, str]:
        scheme = self._template_log_kind(self.current_template_id)
        cached_country = str(qso.get("__country_name", "") or qso.get("country_name", "") or "")
        cached_iso = str(qso.get("__country_iso", "") or qso.get("country_iso", "") or "")
        if bool(qso.get("__country_checked")) and qso.get("__country_scheme") == scheme:
            return cached_country, cached_iso
        country, iso = self._country_info_for_call(str(qso.get("call", "")), self.current_template_id)
        qso["__country_name"] = country
        qso["__country_iso"] = iso
        qso["__country_scheme"] = scheme
        qso["country_name"] = country
        qso["country_iso"] = iso
        qso["__country_checked"] = True
        return country, iso

    def _on_template_selected(self, _event=None):
        if self.template_combo is None:
            return
        selected_name = str(self.template_combo.get() or "").strip()
        template_id = self.template_name_to_id.get(selected_name)
        if not template_id:
            return
        self._set_template(template_id)

    def _on_contest_template_selected(self, _event=None):
        if self.contest_template_combo is None:
            return
        selected_name = str(self.contest_template_combo.get() or "").strip()
        template_id = self.template_name_to_id.get(selected_name)
        if template_id not in self.contest_template_ids:
            return
        self._set_template(template_id)

    def import_contest_template(self):
        path = filedialog.askopenfilename(
            title="Importar plantilla de concurso",
            filetypes=[("Plantilla Python", "*.py"), ("Todos los archivos", "*")],
        )
        if not path:
            return
        try:
            template_id, template_name, log_kind = _inspect_contest_template_file(path)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"La plantilla no es válida:\n{exc}")
            return
        existing_name_id = self.template_name_to_id.get(template_name)
        if existing_name_id is not None and existing_name_id != template_id:
            messagebox.showerror(APP_TITLE, f"Ya existe otra plantilla llamada '{template_name}'.")
            return
        destination = os.path.join(TEMPLATES_DIR, f"{template_id}.py")
        if os.path.exists(destination) and not messagebox.askyesno(
            APP_TITLE, f"La plantilla '{template_name}' ya existe. ¿Quieres reemplazarla?"
        ):
            return
        if not messagebox.askyesno(
            APP_TITLE,
            "Las plantillas son archivos Python ejecutables. Importa únicamente archivos de confianza.\n\n"
            f"Plantilla: {template_name}\nTipo: {'11 m' if log_kind == '11m' else 'HAM'}\n\n¿Continuar?",
        ):
            return
        try:
            module = _load_template_module(path)
            if module.TEMPLATE_ID != template_id or not bool(getattr(module, "IS_CONTEST", False)):
                raise ValueError("Los metadatos de la plantilla no son coherentes.")
            os.makedirs(TEMPLATES_DIR, exist_ok=True)
            if os.path.abspath(path) != os.path.abspath(destination):
                shutil.copy2(path, destination)
            self.templates[template_id] = module
            self._refresh_template_catalog()
            self._get_template_qsos(template_id)
            self._refresh_template_menus()
            if self.template_combo is not None:
                self.template_combo.configure(values=self.main_template_display_values)
            if self.contest_template_combo is not None:
                self.contest_template_combo.configure(values=self.contest_template_display_values)
            if self.log_ops_template_combo is not None:
                self.log_ops_template_combo.configure(values=self.main_template_display_values)
            if self.log_ops_contest_combo is not None:
                self.log_ops_contest_combo.configure(values=self.contest_template_display_values)
            self._set_template(template_id)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"No se pudo instalar la plantilla:\n{exc}")
            return
        messagebox.showinfo(
            APP_TITLE,
            f"Plantilla de concurso importada: {template_name}\nTipo de indicativos: {'11 m' if log_kind == '11m' else 'HAM'}",
        )

    def _schedule_settings_save(self):
        try:
            if self._settings_save_after_id is not None:
                self.root.after_cancel(self._settings_save_after_id)
        except Exception:
            pass
        try:
            self._settings_save_after_id = self.root.after(300, self._save_settings)
        except Exception:
            self._save_settings()

    def _on_auto_connect_changed(self, *_args):
        self._schedule_settings_save()
        if self.auto_connect_var.get():
            self._start_auto_connect_sequence(initial_delay_ms=120)
        else:
            self._cancel_auto_connect_retry()

    def _save_settings(self):
        self._settings_save_after_id = None
        window_geometry = str(self._last_window_geometry or "").strip()
        if not window_geometry:
            try:
                window_geometry = str(self.root.winfo_geometry() or "").strip()
            except Exception:
                window_geometry = ""
        payload = {
            "rig_host": self.host_var.get().strip() or DEFAULT_HOST,
            "rig_port": self.port_var.get().strip() or str(DEFAULT_PORT),
            "rig_auto_poll": bool(self.auto_poll_var.get()),
            "rig_auto_connect": bool(self.auto_connect_var.get()),
            "wsjtx_udp_enabled": bool(self.wsjtx_udp_enabled_var.get()),
            "wsjtx_udp_host": self.wsjtx_udp_host_var.get().strip() or DEFAULT_WSJTX_UDP_HOST,
            "wsjtx_udp_port": self.wsjtx_udp_port_var.get().strip() or str(DEFAULT_WSJTX_UDP_PORT),
            "wsjtx_udp_forward_enabled": bool(self.wsjtx_udp_forward_enabled_var.get()),
            "wsjtx_udp_forward_host": self.wsjtx_udp_forward_host_var.get().strip() or DEFAULT_WSJTX_FWD_HOST,
            "wsjtx_udp_forward_port": self.wsjtx_udp_forward_port_var.get().strip() or str(DEFAULT_WSJTX_FWD_PORT),
            "sync_server_enabled": bool(self.sync_server_enabled_var.get()),
            "sync_server_host": self.sync_server_host_var.get().strip() or DEFAULT_SYNC_HOST,
            "sync_server_port": self.sync_server_port_var.get().strip() or str(DEFAULT_SYNC_PORT),
            "sync_remote_host": self.sync_remote_host_var.get().strip(),
            "sync_remote_port": self.sync_remote_port_var.get().strip() or str(DEFAULT_SYNC_PORT),
            "sync_token": self.sync_token_var.get(),
            "sync_device_id": self.sync_device_id,
            "operator": self.operator_var.get().strip() or DEFAULT_OPERATOR,
            "operator_11": self.operator_11_var.get().strip(),
            "grid": self.grid_var.get().strip() or DEFAULT_GRID,
            "contest": self.contest_var.get().strip(),
            "hamqth_user": self.hamqth_user_var.get().strip(),
            "hamqth_pass": self.hamqth_pass_var.get().strip(),
            "auto_serial": bool(self.auto_serial_var.get()),
            "template_id": self.current_template_id,
            "log_ops_template_id": self._resolve_log_ops_template_id(),
            "template_db_map": self.template_db_map,
            "window_geometry": window_geometry,
        }
        try:
            os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            with contextlib.suppress(OSError):
                os.chmod(SETTINGS_FILE, 0o600)
        except Exception:
            return

    def _load_settings(self):
        try:
            if not os.path.isfile(SETTINGS_FILE):
                return
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return
            self.host_var.set(str(data.get("rig_host", DEFAULT_HOST) or DEFAULT_HOST))
            self.port_var.set(str(data.get("rig_port", DEFAULT_PORT) or DEFAULT_PORT))
            self.auto_poll_var.set(bool(data.get("rig_auto_poll", True)))
            self.auto_connect_var.set(bool(data.get("rig_auto_connect", False)))
            self.wsjtx_udp_enabled_var.set(bool(data.get("wsjtx_udp_enabled", False)))
            self.wsjtx_udp_host_var.set(str(data.get("wsjtx_udp_host", DEFAULT_WSJTX_UDP_HOST) or DEFAULT_WSJTX_UDP_HOST))
            self.wsjtx_udp_port_var.set(str(data.get("wsjtx_udp_port", DEFAULT_WSJTX_UDP_PORT) or DEFAULT_WSJTX_UDP_PORT))
            self.wsjtx_udp_forward_enabled_var.set(bool(data.get("wsjtx_udp_forward_enabled", False)))
            self.wsjtx_udp_forward_host_var.set(
                str(data.get("wsjtx_udp_forward_host", DEFAULT_WSJTX_FWD_HOST) or DEFAULT_WSJTX_FWD_HOST)
            )
            self.wsjtx_udp_forward_port_var.set(
                str(data.get("wsjtx_udp_forward_port", DEFAULT_WSJTX_FWD_PORT) or DEFAULT_WSJTX_FWD_PORT)
            )
            self.sync_server_enabled_var.set(bool(data.get("sync_server_enabled", False)))
            loaded_sync_host = str(data.get("sync_server_host", DEFAULT_SYNC_HOST) or DEFAULT_SYNC_HOST).strip()
            # Older configurations could bind the service to only one NIC. A PC
            # connected by cable and Wi-Fi would then reject clients entering by
            # the other valid LAN address. Listen on all interfaces by default.
            if loaded_sync_host not in {"127.0.0.1", "localhost", "::1"}:
                loaded_sync_host = DEFAULT_SYNC_HOST
            self.sync_server_host_var.set(loaded_sync_host)
            loaded_server_port = str(data.get("sync_server_port", DEFAULT_SYNC_PORT) or DEFAULT_SYNC_PORT)
            self.sync_server_port_var.set(str(DEFAULT_SYNC_PORT) if loaded_server_port == "8765" else loaded_server_port)
            self.sync_remote_host_var.set(str(data.get("sync_remote_host", "") or ""))
            loaded_remote_port = str(data.get("sync_remote_port", DEFAULT_SYNC_PORT) or DEFAULT_SYNC_PORT)
            self.sync_remote_port_var.set(str(DEFAULT_SYNC_PORT) if loaded_remote_port == "8765" else loaded_remote_port)
            self.sync_token_var.set(str(data.get("sync_token", "") or ""))
            stored_device_id = str(data.get("sync_device_id", "") or "").strip()
            try:
                self.sync_device_id = str(uuid.UUID(stored_device_id))
            except ValueError:
                pass
            self.sync_device_id_var.set(self.sync_device_id)
            self.operator_var.set(str(data.get("operator", DEFAULT_OPERATOR) or DEFAULT_OPERATOR))
            self.operator_11_var.set(str(data.get("operator_11", "") or ""))
            self.grid_var.set(str(data.get("grid", DEFAULT_GRID) or DEFAULT_GRID))
            self.contest_var.set(str(data.get("contest", "") or ""))
            self.hamqth_user_var.set(str(data.get("hamqth_user", "") or ""))
            self.hamqth_pass_var.set(str(data.get("hamqth_pass", "") or ""))
            self.auto_serial_var.set(bool(data.get("auto_serial", True)))
            self.template_var.set(str(data.get("template_id", "") or ""))
            self.log_ops_template_var.set(str(data.get("log_ops_template_id", "") or ""))
            db_map = data.get("template_db_map", {})
            if isinstance(db_map, dict):
                cleaned = {}
                for k, v in db_map.items():
                    tkid = str(k or "").strip().lower()
                    tv = str(v or "").strip()
                    if not tkid or not tv:
                        continue
                    if not tv.endswith(DEFAULT_DB_EXT):
                        continue
                    cleaned[tkid] = os.path.basename(tv)
                self.template_db_map = cleaned
            geometry = str(data.get("window_geometry", "") or "").strip()
            if geometry and re.match(r"^\d+x\d+\+\-?\d+\+\-?\d+$", geometry):
                self._pending_window_geometry = geometry
        except Exception:
            return

    def _restore_window_geometry(self):
        geometry = str(self._pending_window_geometry or "").strip()
        if not geometry:
            return

        def parse_geometry(text: str):
            m = re.match(r"^(\d+)x(\d+)\+(-?\d+)\+(-?\d+)$", text or "")
            if not m:
                return None
            return int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))

        parsed = parse_geometry(geometry)
        if parsed is None:
            return
        width, height, target_x, target_y = parsed

        def apply_geometry():
            try:
                req_x = int(target_x)
                req_y = int(target_y)
                # Some window managers add frame/title offsets. Compensate by measuring
                # where the window really lands and correcting request coordinates.
                for _ in range(3):
                    self.root.geometry(f"{width}x{height}+{req_x}+{req_y}")
                    self.root.update_idletasks()
                    real_x = int(self.root.winfo_x())
                    real_y = int(self.root.winfo_y())
                    dx = real_x - target_x
                    dy = real_y - target_y
                    if dx == 0 and dy == 0:
                        break
                    req_x -= dx
                    req_y -= dy
                self._last_window_geometry = geometry
            except Exception:
                pass
        self.root.after(0, apply_geometry)
        self.root.after(120, apply_geometry)

    def _on_main_window_configure(self, _event=None):
        try:
            if self.root.state() != "normal":
                return
            geometry = str(self.root.winfo_geometry() or "").strip()
        except Exception:
            return
        if re.match(r"^\d+x\d+\+\-?\d+\+\-?\d+$", geometry):
            if geometry != self._last_window_geometry:
                self._last_window_geometry = geometry
                # Persist geometry even if the process is terminated externally.
                self._schedule_settings_save()

    def _on_wsjtx_udp_cfg_changed(self):
        self._schedule_settings_save()
        try:
            if self._wsjtx_restart_after_id is not None:
                self.root.after_cancel(self._wsjtx_restart_after_id)
        except Exception:
            pass
        self._wsjtx_restart_after_id = self.root.after(500, self._apply_wsjtx_udp_settings)

    def _apply_wsjtx_udp_settings(self):
        self._wsjtx_restart_after_id = None
        self._ensure_wsjtx_udp_forward_socket()
        if not self.wsjtx_udp_enabled_var.get():
            self._stop_wsjtx_udp_listener()
            self.wsjtx_status_var.set("WSJT-X UDP: detenido")
            return
        host = self.wsjtx_udp_host_var.get().strip() or DEFAULT_WSJTX_UDP_HOST
        try:
            port = int(self.wsjtx_udp_port_var.get().strip())
        except ValueError:
            self.wsjtx_status_var.set("WSJT-X UDP: puerto inválido")
            return
        if self.wsjtx_thread and self.wsjtx_thread.is_alive() and self._wsjtx_bound == (host, port):
            self.wsjtx_status_var.set(f"WSJT-X UDP: escuchando en {host}:{port}")
            return
        self._start_wsjtx_udp_listener(host, port)

    def _start_wsjtx_udp_listener(self, host: str, port: int):
        self._stop_wsjtx_udp_listener()
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
            sock.settimeout(0.5)
        except Exception as exc:
            self.wsjtx_status_var.set(f"WSJT-X UDP error: {exc}")
            return

        self.wsjtx_sock = sock
        self.wsjtx_stop.clear()
        self._wsjtx_bound = (host, port)
        self.wsjtx_thread = threading.Thread(target=self._wsjtx_udp_loop, name="wsjtx-udp-listener", daemon=True)
        self.wsjtx_thread.start()
        if self.wsjtx_udp_forward_enabled_var.get():
            fhost = self.wsjtx_udp_forward_host_var.get().strip() or DEFAULT_WSJTX_FWD_HOST
            fport = self.wsjtx_udp_forward_port_var.get().strip() or str(DEFAULT_WSJTX_FWD_PORT)
            self.wsjtx_status_var.set(f"WSJT-X UDP: {host}:{port} -> {fhost}:{fport}")
        else:
            self.wsjtx_status_var.set(f"WSJT-X UDP: escuchando en {host}:{port}")

    def _ensure_wsjtx_udp_forward_socket(self):
        if self.wsjtx_fwd_sock is not None:
            try:
                self.wsjtx_fwd_sock.close()
            except Exception:
                pass
            self.wsjtx_fwd_sock = None
        if not self.wsjtx_udp_forward_enabled_var.get():
            return
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.wsjtx_fwd_sock = sock
        except Exception:
            self.wsjtx_fwd_sock = None

    def _stop_wsjtx_udp_listener(self):
        self.wsjtx_stop.set()
        sock = self.wsjtx_sock
        self.wsjtx_sock = None
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
        thread = self.wsjtx_thread
        self.wsjtx_thread = None
        if thread and thread.is_alive():
            thread.join(timeout=1.0)
        self._wsjtx_bound = None
        if self.wsjtx_fwd_sock is not None:
            try:
                self.wsjtx_fwd_sock.close()
            except Exception:
                pass
            self.wsjtx_fwd_sock = None

    def _wsjtx_udp_loop(self):
        while not self.wsjtx_stop.is_set():
            sock = self.wsjtx_sock
            if sock is None:
                return
            try:
                payload, _addr = sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            self._forward_wsjtx_udp_packet(payload)
            adif_text = self._extract_wsjtx_logged_adif(payload)
            if not adif_text:
                continue
            try:
                self.root.after(0, lambda txt=adif_text: self._ingest_wsjtx_adif(txt))
            except Exception:
                return

    def _forward_wsjtx_udp_packet(self, payload: bytes):
        if not self.wsjtx_udp_forward_enabled_var.get():
            return
        sock = self.wsjtx_fwd_sock
        if sock is None:
            return
        host = self.wsjtx_udp_forward_host_var.get().strip() or DEFAULT_WSJTX_FWD_HOST
        try:
            port = int(self.wsjtx_udp_forward_port_var.get().strip() or str(DEFAULT_WSJTX_FWD_PORT))
        except Exception:
            return
        # Avoid accidental loop if forwarding points to our own listener.
        try:
            in_host = self.wsjtx_udp_host_var.get().strip() or DEFAULT_WSJTX_UDP_HOST
            in_port = int(self.wsjtx_udp_port_var.get().strip() or str(DEFAULT_WSJTX_UDP_PORT))
            if port == in_port and host in ("127.0.0.1", "localhost", in_host):
                return
        except Exception:
            pass
        try:
            sock.sendto(payload, (host, port))
        except Exception:
            pass

    def _extract_wsjtx_logged_adif(self, payload: bytes) -> str | None:
        if len(payload) < 16:
            return None
        offset = 0
        magic, offset = self._read_u32(payload, offset)
        if magic != 0xADBCCBDA:
            return None
        _schema, offset = self._read_u32(payload, offset)
        msg_type, offset = self._read_u32(payload, offset)
        if msg_type != 12:
            return None
        _sender_id, offset = self._read_qbytearray_utf8(payload, offset)
        try:
            adif_text, offset = self._read_qbytearray_utf8(payload, offset)
        except Exception:
            adif_text = ""
        if adif_text:
            return adif_text
        if offset < len(payload):
            tail = payload[offset:].decode("utf-8", errors="ignore")
            if "<" in tail:
                return tail
        return None

    def _read_u32(self, data: bytes, offset: int) -> tuple[int, int]:
        if offset + 4 > len(data):
            raise ValueError("u32 fuera de rango")
        return int.from_bytes(data[offset : offset + 4], byteorder="big", signed=False), offset + 4

    def _read_qbytearray_utf8(self, data: bytes, offset: int) -> tuple[str, int]:
        length, offset = self._read_u32(data, offset)
        if length == 0xFFFFFFFF:
            return "", offset
        end = offset + length
        if end > len(data):
            raise ValueError("qbytearray fuera de rango")
        return data[offset:end].decode("utf-8", errors="ignore"), end

    def _ingest_wsjtx_adif(self, adif_text: str):
        records = self._parse_adif_records(adif_text or "")
        if not records:
            return
        existing = {self._qso_signature(q) for q in self.current_qsos}
        added = 0
        for rec in records:
            qso = self._qso_from_import_row(rec, adif=True)
            if not qso:
                continue
            sig = self._qso_signature(qso)
            if sig in existing:
                continue
            qso["__db_id"] = self._db_insert_qso(self.current_template_id, qso)
            self.current_qsos.append(qso)
            existing.add(sig)
            added += 1
        if added:
            self._save_template_log(self.current_template_id)
            self._refresh_qso_table()
            self._recompute_next_serial()
            self._update_stats()
            self.wsjtx_status_var.set(f"WSJT-X UDP: +{added} QSO(s) importados")

    def _qso_signature(self, qso: dict) -> tuple:
        call = str(qso.get("call", "")).strip().upper()
        band = str(qso.get("band", "")).strip().lower()
        mode = str(qso.get("mode", "")).strip().upper()
        ts = str(qso.get("timestamp_utc", "")).strip()
        freq = str(qso.get("freq_hz", "")).strip()
        return ts, call, band, mode, freq

    def _cancel_auto_connect_retry(self):
        try:
            if self._auto_connect_after_id is not None:
                self.root.after_cancel(self._auto_connect_after_id)
        except Exception:
            pass
        self._auto_connect_after_id = None

    def _start_auto_connect_sequence(self, initial_delay_ms: int = 250):
        self._cancel_auto_connect_retry()
        self._auto_connect_attempt = 0

        def _run():
            self._auto_connect_after_id = None
            self.connect_rig(silent=True, auto_retry=True)

        try:
            self._auto_connect_after_id = self.root.after(max(0, int(initial_delay_ms)), _run)
        except Exception:
            self.connect_rig(silent=True, auto_retry=True)

    def _schedule_auto_connect_retry(self):
        if self.connected:
            self._cancel_auto_connect_retry()
            return
        if not self.auto_connect_var.get():
            self._cancel_auto_connect_retry()
            return
        self._auto_connect_attempt = int(self._auto_connect_attempt or 0) + 1
        attempt = int(self._auto_connect_attempt)
        # Quick retries at startup, then slower backoff.
        if attempt <= 4:
            delay_ms = 1000
        elif attempt <= 10:
            delay_ms = 2500
        else:
            delay_ms = 5000

        self._cancel_auto_connect_retry()

        def _retry():
            self._auto_connect_after_id = None
            self.connect_rig(silent=True, auto_retry=True)

        try:
            self._auto_connect_after_id = self.root.after(delay_ms, _retry)
            self.status_var.set(f"rigctld: reintento {attempt}...")
        except Exception:
            pass

    def connect_rig(self, silent: bool = False, auto_retry: bool = False):
        host = self.host_var.get().strip()
        try:
            port = int(self.port_var.get().strip())
        except ValueError:
            if not silent:
                messagebox.showerror(APP_TITLE, "Puerto inválido")
            return
        try:
            self._cancel_auto_connect_retry()
            self.client = RigctldClient(host, port)
            self.client.connect()
            self.connected = True
            self._auto_connect_attempt = 0
            self.status_var.set(f"Conectado a {host}:{port}")
            self.poll_rig_once()
            self._schedule_poll()
        except Exception as exc:
            self.connected = False
            self.client = None
            self.status_var.set(f"Error de conexión: {exc}")
            if auto_retry and self.auto_connect_var.get():
                self._schedule_auto_connect_retry()
                return
            if not silent:
                messagebox.showerror(APP_TITLE, f"No se pudo conectar a rigctld:\n{exc}")

    def disconnect_rig(self):
        self._cancel_auto_connect_retry()
        self.polling = False
        self.connected = False
        self._poll_inflight = False
        if self.client:
            self.client.close()
        self.client = None
        self.status_var.set("Desconectado")

    def _schedule_poll(self):
        if self.auto_poll_var.get() and self.connected:
            self.polling = True
            self.root.after(POLL_MS, self._poll_loop)

    def _poll_loop(self):
        if not (self.connected and self.auto_poll_var.get()):
            self.polling = False
            return
        self.poll_rig_once(silent=True)
        self.root.after(POLL_MS, self._poll_loop)

    def poll_rig_once(self, silent: bool = False):
        if not self.client:
            if not silent:
                messagebox.showinfo(APP_TITLE, "No hay conexión con rigctld")
            return
        if self._poll_inflight:
            return
        self._poll_inflight = True

        def worker():
            freq = None
            mode = None
            ptt = None
            error = None
            try:
                if not self.client:
                    raise RuntimeError("Sin cliente rigctld")
                # During TX, keep this logger client passive to avoid adding
                # extra rigctld/CAT traffic while digital frames are on air.
                ptt = int(self.client.get_ptt())
                if ptt == 0:
                    freq = self.client.get_freq()
                    mode_raw = self.client.get_mode()
                    mode = MODE_MAP.get(mode_raw, mode_raw)
            except Exception as exc:
                error = exc

            def apply():
                self._poll_inflight = False
                if error is not None:
                    self.status_var.set(f"Error leyendo rigctld: {error}")
                    if not silent:
                        messagebox.showerror(APP_TITLE, f"Error leyendo radio:\n{error}")
                    return
                if int(ptt or 0) == 1:
                    self.status_var.set("Conectado | TX activo (lectura CAT en pausa)")
                    return
                if freq is None or mode is None:
                    return
                self.current_freq_hz = int(freq)
                self.current_mode = str(mode)
                self.current_band = self.band_from_freq(self.current_freq_hz)
                # While editing a selected QSO, do not overwrite user-entered
                # frequency/mode/band values with live rig polling.
                if self.selected_qso_index is None and not self._is_editing_status_fields():
                    self.freq_var.set(self.format_freq(self.current_freq_hz))
                    self.band_var.set(self.current_band)
                    self.mode_var.set(self.current_mode)
                self.status_var.set(
                    f"Conectado | {self.current_band} | {self.current_mode} | {self.format_freq(self.current_freq_hz)}"
                )
                self.check_dupe()

            try:
                self.root.after(0, apply)
            except Exception:
                self._poll_inflight = False

        threading.Thread(target=worker, daemon=True, name="lg-rig-poll").start()

    def band_from_freq(self, freq_hz: int) -> str:
        for low, high, band in BANDS:
            if low <= freq_hz <= high:
                return band
        return "?"

    def format_freq(self, freq_hz: int) -> str:
        return f"{int(freq_hz):,}".replace(",", ".")

    def parse_freq(self, text: str) -> int:
        cleaned = text.replace(".", "").replace(",", "").strip()
        return int(cleaned)

    def get_form_value(self, key: str) -> str:
        var = self.field_vars.get(key)
        return str(var.get() if var else "")

    def set_form_value(self, key: str, value: str):
        var = self.field_vars.get(key)
        if var is not None:
            var.set(str(value if value is not None else ""))

    def _has_field(self, key: str) -> bool:
        return key in self.field_vars

    def _refresh_serial_fields(self):
        if not self._has_field("serial_sent"):
            return
        if self.auto_serial_var.get() and not self.get_form_value("serial_sent").strip():
            self.set_form_value("serial_sent", f"{int(self.next_serial):03d}")

    def _recompute_next_serial(self):
        serials = []
        for q in self.current_qsos:
            value = q.get("serial_sent")
            if isinstance(value, int):
                serials.append(value)
            elif str(value or "").isdigit():
                serials.append(int(str(value)))
        self.next_serial = (max(serials) + 1) if serials else 1
        if self.auto_serial_var.get():
            self.set_form_value("serial_sent", f"{self.next_serial:03d}")

    def normalize_call(self, call: str) -> str:
        return str(call or "").strip().upper()

    def _rebuild_dupe_index(self):
        index: dict[tuple[str, str, str], int] = {}
        for q in self.current_qsos:
            call = self.normalize_call(q.get("call", ""))
            band = str(q.get("band", "") or "").strip()
            mode = str(q.get("mode", "") or "").strip()
            if not call or not band or not mode:
                continue
            key = (call, band, mode)
            index[key] = int(index.get(key, 0)) + 1
        self._dupe_index = index

    def check_dupe(self):
        if self._suppress_form_reactions:
            return
        if not self._has_field("call"):
            self.dupe_var.set("")
            return
        call = self.normalize_call(self.get_form_value("call"))
        if not call:
            self.dupe_var.set("")
            return
        band = self.band_var.get().strip() or self.current_band
        mode = self.mode_var.get().strip() or self.current_mode
        count = int(self._dupe_index.get((call, band, mode), 0))
        self.dupe_var.set(f"Duplicado en {band}/{mode}: {count}" if count else "Sin duplicado")

    def _template_ctx(self, timestamp_utc: str, original: dict | None = None) -> dict:
        return {
            "get": self.get_form_value,
            "band": self.band_var.get().strip() or self.current_band,
            "mode": self.mode_var.get().strip().upper() or self.current_mode,
            "freq_hz": self._safe_current_freq(),
            "next_serial": self.next_serial,
            "auto_serial": bool(self.auto_serial_var.get()),
            "timestamp_utc": timestamp_utc,
            "original": original,
        }

    def _safe_current_freq(self) -> int:
        try:
            return self.parse_freq(self.freq_var.get())
        except Exception:
            return int(self.current_freq_hz)

    def save_qso(self):
        tpl = self.current_template
        ctx = self._template_ctx(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
        try:
            qso = tpl.build_qso(ctx)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        qso["__db_id"] = self._db_insert_qso(self.current_template_id, qso)
        self.current_qsos.append(qso)
        key = (
            self.normalize_call(qso.get("call", "")),
            str(qso.get("band", "") or "").strip(),
            str(qso.get("mode", "") or "").strip(),
        )
        if all(key):
            self._dupe_index[key] = int(self._dupe_index.get(key, 0)) + 1
        self._save_template_log(self.current_template_id)
        self._refresh_qso_table()
        self._recompute_next_serial()
        self._update_stats()
        self.clear_entry(keep_report=True)

    def _refresh_qso_table(self):
        self._refresh_table_after_id = None
        self._cancel_qso_table_render()
        self._refresh_compute_token += 1
        self._country_render_lite = False
        for item in self.tree.get_children():
            self.tree.delete(item)
        filter_text = ""
        if self.call_var is not None:
            try:
                filter_text = str(self.call_var.get() or "").strip().lower()
            except Exception:
                filter_text = ""
        self._view_indices = []
        token = int(self._refresh_compute_token)
        qsos_snapshot = list(self.current_qsos)
        if len(qsos_snapshot) >= 700:
            self._refresh_worker_thread = threading.Thread(
                target=self._compute_filtered_rows_worker,
                args=(
                    token,
                    qsos_snapshot,
                    filter_text,
                    self.sort_column_id,
                    bool(self.sort_desc),
                    self.current_template_id,
                ),
                daemon=True,
                name="lg-table-refresh",
            )
            self._refresh_worker_thread.start()
            return
        filtered = self._compute_filtered_rows(
            qsos_snapshot,
            filter_text,
            self.sort_column_id,
            bool(self.sort_desc),
        )
        if token != self._refresh_compute_token:
            return
        self._apply_filtered_rows(filtered)

    def _render_qso_rows_chunk(self, token: int):
        if token != self._table_render_token:
            return
        rows = self._table_render_rows
        if not rows:
            self._table_render_after_id = None
            return
        tpl = self.current_template
        total = len(rows)
        if total >= 5000:
            batch_size = 20
        elif total >= 2500:
            batch_size = 28
        elif total >= 1200:
            batch_size = 40
        else:
            batch_size = 60
        start = int(self._table_render_pos)
        end = min(start + batch_size, len(rows))
        original_col_ids = [str(c[0]) for c in tpl.TREE_COLUMNS]
        ordered_col_ids = list(self._ordered_tree_base_cols) if self._ordered_tree_base_cols else original_col_ids
        with_flag = "__flag" in self.tree["columns"]
        with_country = "__country" in self.tree["columns"]
        for i in range(start, end):
            original_idx, qso = rows[i]
            original_values = list(tpl.row_values(qso))
            value_by_col: dict[str, str] = {}
            for j, col_id in enumerate(original_col_ids):
                value_by_col[col_id] = original_values[j] if j < len(original_values) else ""
            values = [value_by_col.get(col_id, "") for col_id in ordered_col_ids]
            if with_country or with_flag:
                if self._country_render_lite:
                    if with_flag:
                        values.append("")
                    if with_country:
                        values.append("")
                else:
                    country, iso2 = self._country_info_for_qso_cached(qso)
                    if with_flag:
                        values.append(self._flag_cell_text(iso2))
                    if with_country:
                        values.append(country)
            self.tree.insert("", "end", values=tuple(values))
            self._view_indices.append(original_idx)
        self._table_render_pos = end
        if end < len(rows):
            try:
                self._table_render_after_id = self.root.after(1, lambda t=token: self._render_qso_rows_chunk(t))
            except Exception:
                self._table_render_after_id = None
                self._table_render_pos = len(rows)
        else:
            self._table_render_after_id = None
            # Once first full paint finishes, re-enable country/flag details on demand.
            if self._country_render_lite:
                self._country_render_lite = False
                self._refresh_visible_country_columns()

    def _refresh_visible_country_columns(self):
        try:
            cols = set(self.tree["columns"])
        except Exception:
            return
        if "__country" not in cols and "__flag" not in cols:
            return
        children = self.tree.get_children()
        for row_idx, item in enumerate(children):
            if row_idx >= len(self._view_indices):
                break
            src_idx = self._view_indices[row_idx]
            if src_idx < 0 or src_idx >= len(self.current_qsos):
                continue
            qso = self.current_qsos[src_idx]
            country, iso2 = self._country_info_for_qso_cached(qso)
            if "__flag" in cols:
                try:
                    self.tree.set(item, "__flag", self._flag_cell_text(iso2))
                except Exception:
                    pass
            if "__country" in cols:
                try:
                    self.tree.set(item, "__country", country)
                except Exception:
                    pass

    def _on_qso_tree_select(self, _event=None):
        selection = self.tree.selection()
        if not selection:
            self.selected_qso_index = None
            self._schedule_map_refresh(20)
            return
        idx = self.tree.index(selection[0])
        if idx < 0 or idx >= len(self._view_indices):
            self.selected_qso_index = None
            return
        source_idx = self._view_indices[idx]
        if source_idx < 0 or source_idx >= len(self.current_qsos):
            self.selected_qso_index = None
            return
        self.selected_qso_index = source_idx
        q = self.current_qsos[source_idx]
        try:
            q_freq = int(q.get("freq_hz", 0) or 0)
        except Exception:
            q_freq = 0
        if q_freq > 0:
            try:
                self.freq_var.set(self.format_freq(q_freq))
            except Exception:
                pass
        q_band = str(q.get("band", "") or "").strip()
        if q_band:
            try:
                self.band_var.set(q_band)
            except Exception:
                pass
        q_mode = str(q.get("mode", "") or "").strip().upper()
        if q_mode:
            try:
                self.mode_var.set(q_mode)
            except Exception:
                pass
        # Keep live rig status intact when selecting rows from the log table.
        # Selection is used to load/edit form fields, not to override current radio state.
        self._suppress_call_filter_refresh = True
        self._suppress_form_reactions = True
        try:
            for key, var in self.field_vars.items():
                value = q.get(key, "")
                if key == "serial_sent" and isinstance(value, int):
                    value = f"{value:03d}"
                var.set(str(value))
        finally:
            self._suppress_form_reactions = False
            self._suppress_call_filter_refresh = False
        self.check_dupe()
        self._update_call_country_display()
        self._schedule_hamqth_autolookup(force=True)
        self._schedule_map_refresh(20)

    def _schedule_hamqth_autolookup(self, force: bool = False):
        if self._suppress_form_reactions:
            return
        call = self.normalize_call(self.get_form_value("call")) if self._has_field("call") else ""
        if not call:
            return
        if not force and call == self._hamqth_last_call:
            return
        try:
            if self._hamqth_after_id is not None:
                self.root.after_cancel(self._hamqth_after_id)
        except Exception:
            pass
        delay_ms = 120 if force else 700
        self._hamqth_after_id = self.root.after(delay_ms, lambda c=call: self.lookup_hamqth(silent=True, expected_call=c))

    def _schedule_map_refresh(self, delay_ms: int = 80):
        try:
            if self._map_render_after_id is not None:
                self.root.after_cancel(self._map_render_after_id)
        except Exception:
            pass
        try:
            self._map_render_after_id = self.root.after(max(0, int(delay_ms)), self._refresh_map_view)
        except Exception:
            self._refresh_map_view()

    def _map_zoom_step(self, factor: float, cx: float | None = None, cy: float | None = None):
        canvas = self._map_canvas
        if canvas is None:
            return
        try:
            width = max(1, int(canvas.winfo_width()))
            height = max(1, int(canvas.winfo_height()))
        except Exception:
            return
        old_zoom = float(self._map_zoom)
        new_zoom = max(1.0, min(220.0, old_zoom * float(factor)))
        if abs(new_zoom - old_zoom) < 1e-6:
            return
        if cx is None:
            cx = width / 2.0
        if cy is None:
            cy = height / 2.0
        wx = (float(cx) - self._map_pan_x) / old_zoom
        wy = (float(cy) - self._map_pan_y) / old_zoom
        self._map_zoom = new_zoom
        self._map_pan_x = float(cx) - wx * new_zoom
        self._map_pan_y = float(cy) - wy * new_zoom
        self._schedule_map_refresh(10)

    def _on_map_mousewheel(self, event):
        delta = getattr(event, "delta", 0)
        if delta == 0:
            return
        factor = 1.6 if delta > 0 else (1 / 1.6)
        self._map_zoom_step(factor, getattr(event, "x", None), getattr(event, "y", None))

    def _on_map_scroll_linux(self, event):
        num = int(getattr(event, "num", 0) or 0)
        if num == 4:
            self._map_zoom_step(1.6, getattr(event, "x", None), getattr(event, "y", None))
        elif num == 5:
            self._map_zoom_step(1 / 1.6, getattr(event, "x", None), getattr(event, "y", None))

    def _on_map_drag_start(self, event):
        self._map_drag_start = (int(getattr(event, "x", 0)), int(getattr(event, "y", 0)))
        self._map_drag_moved = False

    def _on_map_drag_move(self, event):
        if self._map_drag_start is None:
            return
        x0, y0 = self._map_drag_start
        x1 = int(getattr(event, "x", x0))
        y1 = int(getattr(event, "y", y0))
        if abs(x1 - x0) > 2 or abs(y1 - y0) > 2:
            self._map_drag_moved = True
        self._map_pan_x += (x1 - x0)
        self._map_pan_y += (y1 - y0)
        self._map_drag_start = (x1, y1)
        self._schedule_map_refresh(10)

    def _on_map_drag_end(self, _event=None):
        self._map_drag_start = None
        self._map_drag_moved = False

    def _on_map_left_release(self, event):
        moved = bool(self._map_drag_moved)
        self._on_map_drag_end(event)
        if not moved:
            self._on_map_station_click(event)

    def _on_map_station_click(self, event):
        if not self._map_station_points:
            return
        ex = float(getattr(event, "x", 0.0))
        ey = float(getattr(event, "y", 0.0))
        best_call = ""
        best_loc = ""
        best_d2 = 1e18
        for x, y, call, loc in self._map_station_points:
            dx = x - ex
            dy = y - ey
            d2 = dx * dx + dy * dy
            if d2 < best_d2:
                best_d2 = d2
                best_call = call
                best_loc = str(loc or "").strip().upper()
        if not best_call or not best_loc or best_d2 > (20.0 * 20.0):
            return
        if self._has_field("call"):
            try:
                try:
                    for item in self.tree.selection():
                        self.tree.selection_remove(item)
                except Exception:
                    pass
                self.selected_qso_index = None
                self._map_location_filter = best_loc
                self.set_form_value("call", best_call)
                self.check_dupe()
                self._update_call_country_display()
                self._refresh_qso_table()
                self._schedule_map_refresh(20)
            except Exception:
                pass

    def _on_map_reset_view(self, _event=None):
        self._map_zoom = 1.0
        self._map_pan_x = 0.0
        self._map_pan_y = 0.0
        self._map_location_filter = ""
        self._schedule_map_refresh(10)

    def _dynamic_theme_accent(self) -> str:
        cfg_path = os.fspath(poorsdr_paths.config_file())
        try:
            mtime = os.path.getmtime(cfg_path)
        except Exception:
            return self._theme_accent_cached or THEME_ACCENT
        if mtime != self._theme_accent_mtime:
            self._theme_accent_mtime = mtime
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                ui_cfg = cfg.get("ui", {}) if isinstance(cfg.get("ui"), dict) else {}
                bg = str(
                    ui_cfg.get("background_image", cfg.get("Imagen_Fondo", "back.jpg"))
                    or "back.jpg"
                ).strip()
                self._theme_accent_cached = THEME_ACCENT_BY_BACKGROUND.get(bg, THEME_ACCENT)
            except Exception:
                self._theme_accent_cached = THEME_ACCENT
        return self._theme_accent_cached or THEME_ACCENT

    def _draw_station_antenna(self, canvas: tk.Canvas, x: float, y: float, selected: bool = False):
        accent = self._dynamic_theme_accent()
        mast = accent
        base = "#1a1a1a"
        # New station icon: diamond beacon + short mast + base.
        # Keep existing colors to preserve visual meaning.
        size = 5 if selected else 4
        stem_w = 3 if selected else 2
        canvas.create_polygon(
            x, y - size - 3,
            x + size, y - 3,
            x, y + size - 3,
            x - size, y - 3,
            fill=accent,
            outline=accent,
        )
        canvas.create_line(x, y + 1, x, y + 6, fill=mast, width=stem_w)
        canvas.create_oval(x - 3, y + 5, x + 3, y + 9, fill=base, outline=base)

    def _load_offline_world_land(self):
        if self._map_land_loaded:
            return
        self._map_land_loaded = True
        self._map_land_polygons = []
        try:
            if not os.path.isfile(WORLD_MAP_GEOJSON):
                return
            with open(WORLD_MAP_GEOJSON, "r", encoding="utf-8") as f:
                data = json.load(f)
            features = data.get("features", []) if isinstance(data, dict) else []
            for feat in features:
                geom = feat.get("geometry", {}) if isinstance(feat, dict) else {}
                gtype = str(geom.get("type", "") or "")
                coords = geom.get("coordinates", [])
                if gtype == "Polygon":
                    for ring in coords:
                        poly = self._valid_lonlat_ring(ring)
                        if poly:
                            self._map_land_polygons.append(poly)
                elif gtype == "MultiPolygon":
                    for polycoords in coords:
                        if not polycoords:
                            continue
                        ring = polycoords[0]
                        poly = self._valid_lonlat_ring(ring)
                        if poly:
                            self._map_land_polygons.append(poly)
        except Exception:
            self._map_land_polygons = []

    def _load_offline_world_countries(self):
        if self._map_countries_loaded:
            return
        self._map_countries_loaded = True
        self._map_country_polygons = []
        self._map_country_labels = []
        try:
            if not os.path.isfile(WORLD_COUNTRIES_GEOJSON):
                return
            with open(WORLD_COUNTRIES_GEOJSON, "r", encoding="utf-8") as f:
                data = json.load(f)
            features = data.get("features", []) if isinstance(data, dict) else []
            for feat in features:
                if not isinstance(feat, dict):
                    continue
                props = feat.get("properties", {}) if isinstance(feat.get("properties", {}), dict) else {}
                name = str(props.get("NAME", "") or props.get("ADMIN", "") or "").strip()
                if not name:
                    continue
                try:
                    mapcolor = int(props.get("MAPCOLOR7", 0) or 0)
                except Exception:
                    mapcolor = 0
                geom = feat.get("geometry", {}) if isinstance(feat.get("geometry", {}), dict) else {}
                gtype = str(geom.get("type", "") or "")
                coords = geom.get("coordinates", [])
                label_set = False
                if gtype == "Polygon":
                    for i, ring in enumerate(coords):
                        poly = self._valid_lonlat_ring(ring)
                        if not poly:
                            continue
                        self._map_country_polygons.append((name, mapcolor, poly))
                        if i == 0 and not label_set:
                            ll = self._ring_label_center(poly)
                            if ll is not None:
                                self._map_country_labels.append((name, ll[0], ll[1]))
                                label_set = True
                elif gtype == "MultiPolygon":
                    best: list[tuple[float, float]] | None = None
                    best_area = -1.0
                    for polycoords in coords:
                        if not polycoords:
                            continue
                        ring = polycoords[0]
                        poly = self._valid_lonlat_ring(ring)
                        if not poly:
                            continue
                        self._map_country_polygons.append((name, mapcolor, poly))
                        area = self._ring_bbox_area(poly)
                        if area > best_area:
                            best_area = area
                            best = poly
                    if best:
                        ll = self._ring_label_center(best)
                        if ll is not None:
                            self._map_country_labels.append((name, ll[0], ll[1]))
        except Exception:
            self._map_country_polygons = []
            self._map_country_labels = []

    def _load_offline_world_places(self):
        if self._map_places_loaded:
            return
        self._map_places_loaded = True
        self._map_places = []
        try:
            # Preferred source: GeoNames cities500 (global, updated, richer admin hierarchy).
            if os.path.isfile(WORLD_GEONAMES_CITIES_FILE) or os.path.isfile(WORLD_GEONAMES_CITIES_ZIP):
                with _open_geonames_cities() as f:
                    for line in f:
                        cols = line.rstrip("\n").split("\t")
                        if len(cols) < 15:
                            continue
                        name = str(cols[1] or cols[2] or "").strip()
                        if not name:
                            continue
                        try:
                            lat = float(cols[4])
                            lon = float(cols[5])
                        except Exception:
                            continue
                        if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
                            continue
                        feat_class = str(cols[6] or "").strip().upper()
                        feat_code = str(cols[7] or "").strip().upper()
                        if feat_class != "P":
                            continue
                        try:
                            pop_max = int(cols[14] or 0)
                        except Exception:
                            pop_max = 0
                        is_capital = feat_code == "PPLC"
                        is_prov_capital = feat_code.startswith("PPLA")
                        # Build rank where smaller means more important (for declutter priority).
                        if is_capital:
                            scalerank = 1
                        elif feat_code == "PPLA":
                            scalerank = 2
                        elif feat_code == "PPLA2":
                            scalerank = 3
                        elif feat_code == "PPLA3":
                            scalerank = 4
                        elif feat_code == "PPLA4":
                            scalerank = 5
                        else:
                            if pop_max >= 2_000_000:
                                scalerank = 3
                            elif pop_max >= 700_000:
                                scalerank = 5
                            elif pop_max >= 200_000:
                                scalerank = 7
                            elif pop_max >= 50_000:
                                scalerank = 9
                            else:
                                scalerank = 12
                        self._map_places.append((name, feat_code, lat, lon, scalerank, pop_max, is_capital, is_prov_capital))
            elif os.path.isfile(WORLD_PLACES_GEOJSON):
                # Fallback source: Natural Earth populated places.
                with open(WORLD_PLACES_GEOJSON, "r", encoding="utf-8") as f:
                    data = json.load(f)
                features = data.get("features", []) if isinstance(data, dict) else []
                for feat in features:
                    if not isinstance(feat, dict):
                        continue
                    geom = feat.get("geometry", {}) if isinstance(feat.get("geometry", {}), dict) else {}
                    if str(geom.get("type", "") or "") != "Point":
                        continue
                    coords = geom.get("coordinates", [])
                    if not isinstance(coords, (list, tuple)) or len(coords) < 2:
                        continue
                    try:
                        lon = float(coords[0])
                        lat = float(coords[1])
                    except Exception:
                        continue
                    if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
                        continue
                    props = feat.get("properties", {}) if isinstance(feat.get("properties", {}), dict) else {}
                    name = str(props.get("NAME", "") or props.get("name", "") or "").strip()
                    if not name:
                        continue
                    fclass = str(props.get("FEATURECLA", "") or "").strip()
                    try:
                        scalerank = int(props.get("SCALERANK", 10) or 10)
                    except Exception:
                        scalerank = 10
                    try:
                        pop_max = int(float(props.get("POP_MAX", 0) or 0))
                    except Exception:
                        pop_max = 0
                    adm0cap = str(props.get("ADM0CAP", "") or "").strip()
                    adm1cap = str(props.get("ADM1CAP", "") or "").strip()
                    capin = str(props.get("CAPIN", "") or "").strip()
                    adm0cap_i = 0
                    adm1cap_i = 0
                    capin_i = 0
                    try:
                        adm0cap_i = int(float(adm0cap or 0))
                    except Exception:
                        pass
                    try:
                        adm1cap_i = int(float(adm1cap or 0))
                    except Exception:
                        pass
                    try:
                        capin_i = int(float(capin or 0))
                    except Exception:
                        pass
                    is_capital = adm0cap_i > 0 or capin_i > 0 or "capital" in fclass.lower() or scalerank <= 2
                    is_prov_capital = adm1cap_i > 0
                    self._map_places.append((name, fclass, lat, lon, scalerank, pop_max, is_capital, is_prov_capital))
            existing = {str(p[0]).strip().lower() for p in self._map_places}
            for name, lat, lon, pop_est, is_nat_cap, is_prov_cap in MAP_PLACE_OVERRIDES:
                key = str(name).strip().lower()
                if not key or key in existing:
                    continue
                # scalerank low value forces visibility at broader zoom levels.
                scalerank = 3 if is_nat_cap else (4 if is_prov_cap else 10)
                self._map_places.append(
                    (name, "Override", float(lat), float(lon), scalerank, int(pop_est), bool(is_nat_cap), bool(is_prov_cap))
                )
                existing.add(key)
        except Exception:
            self._map_places = []

    def _ring_bbox_area(self, ring: list[tuple[float, float]]) -> float:
        if not ring:
            return 0.0
        lons = [p[0] for p in ring]
        lats = [p[1] for p in ring]
        return max(0.0, (max(lons) - min(lons)) * (max(lats) - min(lats)))

    def _ring_label_center(self, ring: list[tuple[float, float]]) -> tuple[float, float] | None:
        if not ring:
            return None
        lons = [p[0] for p in ring]
        lats = [p[1] for p in ring]
        lon = (min(lons) + max(lons)) / 2.0
        lat = (min(lats) + max(lats)) / 2.0
        return (lat, lon)

    def _sample_ring_for_zoom(self, ring: list[tuple[float, float]], zoom: float) -> list[tuple[float, float]]:
        n = len(ring)
        if n <= 8:
            return ring
        if zoom < 1.3:
            step = 10
        elif zoom < 2.0:
            step = 6
        elif zoom < 3.0:
            step = 3
        else:
            step = 1
        if step <= 1:
            return ring
        sampled = [ring[i] for i in range(0, n, step)]
        if sampled[-1] != ring[-1]:
            sampled.append(ring[-1])
        return sampled if len(sampled) >= 3 else ring

    def _visible_lonlat_bounds(
        self, width: int, height: int, ox: float, oy: float, map_w: float, map_h: float
    ) -> tuple[float, float, float, float]:
        # Inverse projection for current zoom/pan to cull geometry outside viewport.
        z = max(0.001, float(self._map_zoom))
        px0 = (0.0 - self._map_pan_x) / z
        px1 = (float(width) - self._map_pan_x) / z
        py0 = (0.0 - self._map_pan_y) / z
        py1 = (float(height) - self._map_pan_y) / z
        lon0 = ((min(px0, px1) - ox) / max(1.0, map_w)) * 360.0 - 180.0
        lon1 = ((max(px0, px1) - ox) / max(1.0, map_w)) * 360.0 - 180.0
        lat1 = 90.0 - ((min(py0, py1) - oy) / max(1.0, map_h)) * 180.0
        lat0 = 90.0 - ((max(py0, py1) - oy) / max(1.0, map_h)) * 180.0
        return (
            max(-180.0, min(180.0, lon0)),
            max(-180.0, min(180.0, lon1)),
            max(-90.0, min(90.0, lat0)),
            max(-90.0, min(90.0, lat1)),
        )

    def _valid_lonlat_ring(self, ring) -> list[tuple[float, float]]:
        out: list[tuple[float, float]] = []
        if not isinstance(ring, list):
            return out
        for pair in ring:
            if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                continue
            try:
                lon = float(pair[0])
                lat = float(pair[1])
            except Exception:
                continue
            if -180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0:
                out.append((lon, lat))
        return out if len(out) >= 3 else []

    def _grid_to_latlon(self, locator: str) -> tuple[float, float] | None:
        raw = str(locator or "").strip().upper()
        if len(raw) < 4:
            return None
        chars = [c for c in raw if c.isalnum()]
        if len(chars) < 4:
            return None
        s = "".join(chars[:8])
        try:
            lon = -180.0 + (ord(s[0]) - ord("A")) * 20.0
            lat = -90.0 + (ord(s[1]) - ord("A")) * 10.0
            lon += int(s[2]) * 2.0
            lat += int(s[3]) * 1.0
            lon_size = 2.0
            lat_size = 1.0
            if len(s) >= 6 and s[4].isalpha() and s[5].isalpha():
                lon += (ord(s[4]) - ord("A")) * (5.0 / 60.0)
                lat += (ord(s[5]) - ord("A")) * (2.5 / 60.0)
                lon_size = 5.0 / 60.0
                lat_size = 2.5 / 60.0
            if len(s) >= 8 and s[6].isdigit() and s[7].isdigit():
                lon += int(s[6]) * (0.5 / 60.0)
                lat += int(s[7]) * (0.25 / 60.0)
                lon_size = 0.5 / 60.0
                lat_size = 0.25 / 60.0
            return (lat + lat_size / 2.0, lon + lon_size / 2.0)
        except Exception:
            return None

    def _haversine_km(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        r = 6371.0
        p1 = math.radians(lat1)
        p2 = math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * (math.sin(dlon / 2.0) ** 2)
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return r * c

    def _qso_locator(self, qso: dict) -> str:
        for key in ("grid", "gridsquare", "locator"):
            val = str(qso.get(key, "") or "").strip()
            if val:
                return val
        return ""

    def _form_locator(self) -> str:
        for key in ("grid", "gridsquare", "locator"):
            if self._has_field(key):
                val = str(self.get_form_value(key) or "").strip()
                if val:
                    return val
        return ""

    def _selected_callsign_for_map(self) -> str:
        if self._has_field("call"):
            try:
                form_call = self.normalize_call(self.get_form_value("call"))
            except Exception:
                form_call = ""
            if form_call:
                return form_call
        selection = self.tree.selection()
        if not selection:
            return ""
        try:
            idx = self.tree.index(selection[0])
        except Exception:
            return ""
        if idx < 0 or idx >= len(self._view_indices):
            return ""
        src_idx = self._view_indices[idx]
        if src_idx < 0 or src_idx >= len(self.current_qsos):
            return ""
        return self.normalize_call(self.current_qsos[src_idx].get("call", ""))

    def _refresh_map_view(self):
        self._map_render_after_id = None
        canvas = self._map_canvas
        if canvas is None:
            return
        try:
            width = max(1, int(canvas.winfo_width()))
            height = max(1, int(canvas.winfo_height()))
        except Exception:
            return
        canvas.delete("all")
        self._map_station_points = []
        self._load_offline_world_land()
        self._load_offline_world_countries()
        self._load_offline_world_places()

        margin = 10
        w = max(10, width - margin * 2)
        h = max(10, height - margin * 2)
        map_h = min(h, int(w / 2.0))
        map_w = int(map_h * 2.0)
        if map_w > w:
            map_w = w
            map_h = int(map_w / 2.0)
        ox = margin + (w - map_w) // 2
        oy = margin + (h - map_h) // 2

        def project(lat: float, lon: float) -> tuple[float, float]:
            x = ox + ((lon + 180.0) / 360.0) * map_w
            y = oy + ((90.0 - lat) / 180.0) * map_h
            x = x * self._map_zoom + self._map_pan_x
            y = y * self._map_zoom + self._map_pan_y
            return (x, y)

        v_lon0, v_lon1, v_lat0, v_lat1 = self._visible_lonlat_bounds(width, height, ox, oy, map_w, map_h)

        canvas.create_rectangle(ox, oy, ox + map_w, oy + map_h, fill="#0f1b2b", outline="#2c3f55", width=1)
        canvas.create_text(ox + map_w * 0.18, oy + map_h * 0.42, text="PACIFIC OCEAN", fill="#32506c", font=("TkDefaultFont", 9))
        canvas.create_text(ox + map_w * 0.50, oy + map_h * 0.43, text="ATLANTIC OCEAN", fill="#32506c", font=("TkDefaultFont", 9))
        canvas.create_text(ox + map_w * 0.83, oy + map_h * 0.45, text="PACIFIC OCEAN", fill="#32506c", font=("TkDefaultFont", 9))
        canvas.create_text(ox + map_w * 0.67, oy + map_h * 0.23, text="ARCTIC OCEAN", fill="#32506c", font=("TkDefaultFont", 9))
        for lat in (-60, -30, 0, 30, 60):
            y = oy + ((90.0 - lat) / 180.0) * map_h
            canvas.create_line(ox, y, ox + map_w, y, fill="#1f3248")
        for lon in (-120, -60, 0, 60, 120):
            x = ox + ((lon + 180.0) / 360.0) * map_w
            canvas.create_line(x, oy, x, oy + map_h, fill="#1f3248")

        map_palette = {
            1: "#3a4a3b",
            2: "#35483e",
            3: "#4a4338",
            4: "#33494a",
            5: "#4b3a41",
            6: "#3a4152",
            7: "#4b4a3a",
        }
        min_area = 0.9 if self._map_zoom < 1.2 else (0.2 if self._map_zoom < 2.0 else 0.02)
        for _name, mapcolor, ring in self._map_country_polygons:
            if self._ring_bbox_area(ring) < min_area:
                continue
            ring2 = self._sample_ring_for_zoom(ring, self._map_zoom)
            pts: list[float] = []
            for lon, lat in ring2:
                x, y = project(lat, lon)
                pts.extend((x, y))
            if len(pts) >= 6:
                try:
                    fill_color = map_palette.get(int(mapcolor), "#3c3f37")
                    border = "#58606a" if self._map_zoom < 2.0 else "#6c7682"
                    canvas.create_polygon(pts, fill=fill_color, outline=border, width=1)
                except Exception:
                    pass

        if self._map_zoom >= 1.0:
            used_cells: set[tuple[int, int]] = set()
            for name, lat, lon in self._map_country_labels:
                if lon < v_lon0 or lon > v_lon1 or lat < v_lat0 or lat > v_lat1:
                    continue
                x, y = project(lat, lon)
                if x < 0 or x > width or y < 0 or y > height:
                    continue
                cell_w = 120 if self._map_zoom < 1.8 else 85
                cell_h = 34 if self._map_zoom < 1.8 else 24
                cell = (int((x - ox) // cell_w), int((y - oy) // cell_h))
                if cell in used_cells:
                    continue
                used_cells.add(cell)
                canvas.create_text(
                    x,
                    y,
                    text=name.upper() if self._map_zoom >= 2.5 else name,
                    fill="#d7dde5",
                    font=("TkDefaultFont", 8 if self._map_zoom < 2.5 else 9, "bold"),
                )

        # Layers: countries -> capitals -> populations.
        # Countries are drawn above; capitals/populations are zoom-gated here.
        if self._map_zoom >= 5.0:
            # Strict progressive levels:
            # 5.0-10.0  -> capitals only
            # 10.0-13.0 -> add large populations
            # 13.0-17.0 -> add medium populations
            # 17.0+     -> add small populations
            if self._map_zoom < 10.0:
                mode = "capitals"
                pop_threshold = 10**9
                place_cell_w, place_cell_h = 220, 56
                max_labels = 120
            elif self._map_zoom < 13.0:
                mode = "large"
                pop_threshold = 700_000
                place_cell_w, place_cell_h = 145, 38
                max_labels = 150
            elif self._map_zoom < 17.0:
                mode = "medium"
                pop_threshold = 250_000
                place_cell_w, place_cell_h = 105, 27
                max_labels = 240
            else:
                mode = "small"
                pop_threshold = 50_000
                place_cell_w, place_cell_h = 74, 19
                max_labels = 360

            def _norm_lon(lon: float) -> float:
                while lon < -180.0:
                    lon += 360.0
                while lon > 180.0:
                    lon -= 360.0
                return lon

            def _lon_in_view(lon: float, min_lon: float, max_lon: float) -> bool:
                ln = _norm_lon(lon)
                a = _norm_lon(min_lon)
                b = _norm_lon(max_lon)
                if a <= b:
                    return a <= ln <= b
                return ln >= a or ln <= b

            lat_margin = 1.0
            lon_margin = 1.5
            lat_min = v_lat0 - lat_margin
            lat_max = v_lat1 + lat_margin
            lon_min = v_lon0 - lon_margin
            lon_max = v_lon1 + lon_margin

            visible_places = [
                p
                for p in self._map_places
                if lat_min <= p[2] <= lat_max and _lon_in_view(p[3], lon_min, lon_max)
            ]

            place_cells: set[tuple[int, int]] = set()
            # Prioritize important places first so decluttering keeps capitals/major cities.
            ordered_places = sorted(
                visible_places,
                key=lambda p: (
                    0 if p[6] else (1 if p[7] else 2),  # national, provincial, then others
                    p[4],              # then lower scalerank (more important)
                    -int(p[5]),        # then larger population
                    p[0],              # stable name order
                ),
            )
            drawn_labels = 0
            for name, fclass, lat, lon, scalerank, pop_max, is_capital, is_prov_capital in ordered_places:
                if mode == "capitals":
                    if not (is_capital or is_prov_capital or scalerank <= 4):
                        continue
                elif mode == "large":
                    if not (is_capital or is_prov_capital or pop_max >= pop_threshold):
                        continue
                elif mode == "medium":
                    if not (is_capital or is_prov_capital or pop_max >= pop_threshold):
                        continue
                else:
                    if not (is_capital or is_prov_capital or pop_max >= pop_threshold):
                        continue

                x, y = project(lat, lon)
                if x < 0 or x > width or y < 0 or y > height:
                    continue
                cell = (int(x // place_cell_w), int(y // place_cell_h))
                if cell in place_cells:
                    continue
                place_cells.add(cell)
                if drawn_labels >= max_labels:
                    break
                dot_color = "#ff6b7a" if is_capital else ("#ffb37d" if is_prov_capital else "#7db7ff")
                text_color = "#f3f6fa" if is_capital else ("#ffe9d6" if is_prov_capital else "#d6e3f3")
                if self._map_zoom >= 20.0:
                    font = ("TkDefaultFont", 7, "bold") if (is_capital or is_prov_capital) else ("TkDefaultFont", 7)
                else:
                    font = ("TkDefaultFont", 8, "bold") if (is_capital or is_prov_capital) else ("TkDefaultFont", 8)
                r = 2 if (is_capital or is_prov_capital) else 1
                canvas.create_oval(x - r, y - r, x + r, y + r, fill=dot_color, outline=dot_color)
                canvas.create_text(x + 4, y - 2, text=name, anchor="w", fill=text_color, font=font)
                drawn_labels += 1

        selected_call = self._selected_callsign_for_map()
        points: list[tuple[str, str, float, float]] = []
        for q in self.current_qsos:
            call = self.normalize_call(q.get("call", ""))
            if selected_call and call != selected_call:
                continue
            loc = self._qso_locator(q)
            ll = self._grid_to_latlon(loc)
            if ll is None:
                continue
            lat, lon = ll
            points.append((call, loc.upper(), lat, lon))

        # Live preview from the form: lets us show map location for a new/unsaved call
        # as soon as a valid locator is available (manual or auto lookup).
        if selected_call:
            form_loc = self._form_locator()
            form_ll = self._grid_to_latlon(form_loc)
            if form_ll is not None:
                points.append((selected_call, form_loc.upper(), form_ll[0], form_ll[1]))

        if not points:
            canvas.create_text(
                ox + map_w / 2,
                oy + map_h / 2,
                text="Sin coordenadas (GRID) en los contactos.",
                fill="#e6eef5",
                font=("TkDefaultFont", 11, "bold"),
            )
            self._map_status_var.set("Sin datos para mostrar en el mapa.")
            return

        unique: dict[tuple[str, str], tuple[str, str, float, float]] = {}
        for p in points:
            unique[(p[0], p[1])] = p
        draw_points = list(unique.values())

        my_ll = self._grid_to_latlon(self.grid_var.get().strip())
        my_xy = None
        if my_ll is not None:
            my_xy = project(my_ll[0], my_ll[1])
            mx, my = my_xy
            canvas.create_oval(mx - 5, my - 5, mx + 5, my + 5, fill="#ffea00", outline="#101010", width=1)
            canvas.create_text(mx + 8, my - 8, text="Mi QTH", anchor="w", fill="#ffea00", font=("TkDefaultFont", 9, "bold"))

        for call, loc, lat, lon in draw_points:
            x, y = project(lat, lon)
            self._draw_station_antenna(canvas, x, y, selected=bool(selected_call))
            self._map_station_points.append((x, y, call, loc))
            if selected_call:
                canvas.create_text(x + 8, y - 8, text=f"{call} {loc}", anchor="w", fill="#ffffff", font=("TkDefaultFont", 9))
            if selected_call and my_xy is not None:
                mx, my = my_xy
                canvas.create_line(mx, my, x, y, fill="#ffd166", width=2)
                km = self._haversine_km(my_ll[0], my_ll[1], lat, lon) if my_ll is not None else 0.0
                tx = (mx + x) / 2.0
                ty = (my + y) / 2.0
                canvas.create_text(tx + 4, ty - 4, text=f"{km:.0f} km", anchor="w", fill="#ffd166", font=("TkDefaultFont", 9, "bold"))

        if selected_call:
            self._map_status_var.set(
                f"Mapa top offline 10m | zoom {self._map_zoom:.2f}x | {selected_call} ({len(draw_points)} ubicación(es))."
            )
        else:
            self._map_status_var.set(
                f"Mapa top offline 10m | zoom {self._map_zoom:.2f}x | todas las estaciones ({len(draw_points)} ubicación(es))."
            )

    def _normalize_country_name(self, name: str) -> str:
        text = str(name or "").strip().lower()
        if not text:
            return ""
        text = unicodedata.normalize("NFKD", text)
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        text = text.replace("&", " and ")
        text = re.sub(r"[^a-z0-9]+", " ", text).strip()
        return text

    def _load_country_iso_index(self):
        self._country_name_to_iso = {}
        try:
            if not os.path.isfile(self.country_meta_json):
                return
            with open(self.country_meta_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                return
            for row in data:
                if not isinstance(row, dict):
                    continue
                code = str(row.get("code", "") or "").strip().upper()
                name = str(row.get("name", "") or "").strip()
                if len(code) != 2 or not name:
                    continue
                key = self._normalize_country_name(name)
                if key:
                    self._country_name_to_iso[key] = code
            aliases = {
                "england": "GB",
                "northern ireland": "GB",
                "scotland": "GB",
                "wales": "GB",
                "czech republic": "CZ",
                "north macedonia": "MK",
                "south korea": "KR",
                "ivory coast": "CI",
                "cape verde": "CV",
                "laos": "LA",
                "syria": "SY",
                "vatican": "VA",
                "republic of the congo": "CG",
                "democratic republic of the congo": "CD",
                "bosnia and herzegovina": "BA",
                "united states": "US",
                "russia": "RU",
                "moldova": "MD",
                "macau": "MO",
                "eswatini": "SZ",
                "taiwan": "TW",
                # DXCC entities / common contest labels from cty.csv
                "african italy": "IT",
                "agalega st brandon": "MU",
                "alaska": "US",
                "amsterdam st paul is": "TF",
                "andaman nicobar is": "IN",
                "annobon island": "GQ",
                "asiatic russia": "RU",
                "asiatic turkey": "TR",
                "austral islands": "PF",
                "aves island": "VE",
                "azores": "PT",
                "baker howland islands": "UM",
                "balearic islands": "ES",
                "banaba island": "KI",
                "bear island": "SJ",
                "bonaire": "BQ",
                "bouvet": "BV",
                "british virgin islands": "VG",
                "cape verde": "CV",
                "central kiribati": "KI",
                "ceuta melilla": "ES",
                "chagos islands": "IO",
                "chatham islands": "NZ",
                "cocos island": "CC",
                "conway reef": "FJ",
                "corsica": "FR",
                "crete": "GR",
                "crozet island": "TF",
                "dpr of korea": "KP",
                "dem rep of the congo": "CD",
                "desecheo island": "PR",
                "dodecanese": "GR",
                "ducie island": "PN",
                "east malaysia": "MY",
                "easter island": "CL",
                "european russia": "RU",
                "european turkey": "TR",
                "fed rep of germany": "DE",
                "fernando de noronha": "BR",
                "franz josef land": "RU",
                "galapagos islands": "EC",
                "glorioso islands": "TF",
                "guantanamo bay": "CU",
                "hawaii": "US",
                "heard island": "HM",
                "jan mayen": "SJ",
                "johnston island": "UM",
                "juan fernandez islands": "CL",
                "juan de nova europa": "TF",
                "kaliningrad": "RU",
                "kerguelen islands": "TF",
                "kermadec islands": "NZ",
                "kingdom of eswatini": "SZ",
                "kure island": "US",
                "lakshadweep islands": "IN",
                "lord howe island": "AU",
                "macquarie island": "AU",
                "madeira islands": "PT",
                "malpelo island": "CO",
                "mariana islands": "MP",
                "market reef": "FI",
                "marquesas islands": "PF",
                "midway island": "UM",
                "minami torishima": "JP",
                "mount athos": "GR",
                "n z subantarctic is": "NZ",
                "navassa island": "UM",
                "north cook islands": "CK",
                "ogasawara": "JP",
                "palestine": "PS",
                "palmyra jarvis islands": "UM",
                "peter 1 island": "AQ",
                "pitcairn island": "PN",
                "pr edward marion is": "ZA",
                "pratas island": "TW",
                "republic of korea": "KR",
                "republic of kosovo": "XK",
                "republic of south sudan": "SS",
                "reunion island": "RE",
                "revillagigedo": "MX",
                "rodriguez island": "MU",
                "rotuma island": "FJ",
                "saba st eustatius": "BQ",
                "sable island": "CA",
                "san andres providencia": "CO",
                "san felix san ambrosio": "CL",
                "sardinia": "IT",
                "scarborough reef": "PH",
                "shetland islands": "GB",
                "sicily": "IT",
                "slovak republic": "SK",
                "south cook islands": "CK",
                "south georgia island": "GS",
                "south orkney islands": "AQ",
                "south sandwich islands": "GS",
                "south shetland islands": "AQ",
                "sov mil order of malta": "MT",
                "spratly islands": "PH",
                "st barthelemy": "BL",
                "st helena": "SH",
                "st kitts nevis": "KN",
                "st lucia": "LC",
                "st martin": "MF",
                "st paul island": "US",
                "st peter st paul": "BR",
                "st pierre miquelon": "PM",
                "st vincent": "VC",
                "svalbard": "SJ",
                "swains island": "AS",
                "tokelau islands": "TK",
                "trindade martim vaz": "BR",
            }
            for k, v in aliases.items():
                self._country_name_to_iso.setdefault(self._normalize_country_name(k), v)
        except Exception:
            self._country_name_to_iso = {}

    def _country_to_iso(self, country_name: str) -> str:
        key = self._normalize_country_name(country_name)
        if not key:
            return ""
        direct = self._country_name_to_iso.get(key, "")
        if direct:
            return direct
        # Heuristic fallback: try matching known country names inside DX labels.
        for known, iso in sorted(self._country_name_to_iso.items(), key=lambda kv: len(kv[0]), reverse=True):
            if len(known) < 4:
                continue
            if re.search(rf"(^| ){re.escape(known)}($| )", key):
                return iso
        return ""

    def _load_world_prefixes(self):
        self._world_prefixes = []
        self._world_exact_calls = {}
        path = self.world_prefix_csv
        if not os.path.isfile(path):
            return
        parsed: list[tuple[str, str, str]] = []
        parsed_exact: dict[str, tuple[str, str]] = {}
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) < 2:
                        continue
                    country = str(row[1] or "").strip()
                    if not country:
                        continue
                    iso = self._country_to_iso(country)
                    raw_prefixes = ""
                    if len(row) >= 10:
                        raw_prefixes = str(row[9] or "").strip()
                    # Guard for alternate CSV layouts: prefixes are usually the last field.
                    if not raw_prefixes and row:
                        raw_prefixes = str(row[-1] or "").strip()
                    if not raw_prefixes:
                        continue
                    for token in raw_prefixes.split():
                        tok = token.strip().rstrip(";").upper()
                        if not tok:
                            continue
                        is_exact = tok.startswith("=")
                        tok = re.sub(r"\(.*?\)", "", tok)
                        tok = re.sub(r"\[.*?\]", "", tok)
                        tok = re.sub(r"<.*?>", "", tok)
                        tok = tok.lstrip("=*")
                        tok = "".join(ch for ch in tok if ch.isalnum() or ch == "/")
                        tok = tok.strip("/")
                        if not tok:
                            continue
                        if is_exact:
                            key = tok.replace("/", "")
                            if key:
                                parsed_exact.setdefault(key, (country, iso))
                            continue
                        prefix = tok.replace("/", "")
                        if not prefix:
                            continue
                        parsed.append((prefix, country, iso))
        except Exception:
            self._world_prefixes = []
            self._world_exact_calls = {}
            return
        unique: dict[tuple[str, str], tuple[str, str, str]] = {}
        for prefix, country, iso in parsed:
            key = (prefix, country)
            if key not in unique:
                unique[key] = (prefix, country, iso)
        self._world_prefixes = sorted(unique.values(), key=lambda it: len(it[0]), reverse=True)
        self._world_exact_calls = parsed_exact

    def _country_from_world_prefixes(self, token: str) -> tuple[str, str] | None:
        t = str(token or "").strip().upper()
        if not t:
            return None
        exact = self._world_exact_calls.get(t.replace("/", ""))
        if exact is not None:
            return exact
        for prefix, country, iso in self._world_prefixes:
            if t.startswith(prefix):
                return country, iso
        return None

    def _normalize_callsign_token(self, token: str) -> str:
        raw = str(token or "").strip().upper()
        if not raw:
            return ""
        raw = re.sub(r"[^A-Z0-9/]", "", raw)
        if not raw:
            return ""
        parts = [p for p in raw.split("/") if p]
        if not parts:
            return raw.replace("/", "")
        ignored_suffixes = {"P", "M", "MM", "AM", "QRP", "QRPP", "LH", "A", "B", "MOBILE", "PORTABLE"}
        parts = [p for p in parts if p not in ignored_suffixes] or parts
        best = max(parts, key=lambda p: (sum(ch.isalnum() for ch in p), len(p)))
        return best

    def _call_for_country_lookup(self, call: str) -> str:
        raw = str(call or "").strip().upper()
        if "/" not in raw:
            return self._normalize_callsign_token(raw)
        parts = [p for p in raw.split("/") if p]
        if not parts:
            return self._normalize_callsign_token(raw)
        ignored_suffixes = {"P", "M", "MM", "AM", "QRP", "LH", "QRPP", "A"}
        candidates = [p for p in parts if p not in ignored_suffixes]
        if not candidates:
            candidates = parts
        scored: list[tuple[int, str]] = []
        for idx, part in enumerate(candidates):
            score = 0
            has_alpha = any(ch.isalpha() for ch in part)
            has_digit = any(ch.isdigit() for ch in part)
            if has_alpha and has_digit:
                score += 30
            if len(part) <= 4:
                score += 15
            info = self._country_info_for_token(part)
            if info is not None:
                score += 100
            if idx == 0 or idx == len(candidates) - 1:
                score += 5
            scored.append((score, part))
        scored.sort(key=lambda it: (it[0], len(it[1])), reverse=True)
        return self._normalize_callsign_token(scored[0][1] if scored else parts[0])

    def _country_info_for_11m_division(self, call: str) -> tuple[str, str] | None:
        raw = str(call or "").strip().upper()
        if not raw:
            return None
        cleaned = re.sub(r"[^A-Z0-9/]+", "", raw)
        candidates = [cleaned]
        if "/" in cleaned:
            parts = [p for p in cleaned.split("/") if p]
            if parts:
                candidates.extend(parts)
        division: int | None = None
        for cand in candidates:
            m = re.match(r"^(\d{1,3})", cand)
            if m:
                try:
                    division = int(m.group(1))
                    break
                except Exception:
                    pass
        if division is None:
            # Fallback for odd formats: find division token at start or after slash.
            m2 = re.search(r"(?:^|/)(\d{1,3})(?=[A-Z])", cleaned)
            if not m2:
                return None
            try:
                division = int(m2.group(1))
            except Exception:
                return None
        if division in self.dx11_divisions:
            return self.dx11_divisions[division]
        return (f"División {division}", "")

    def _flag_from_iso(self, iso2: str) -> str:
        code = str(iso2 or "").strip().upper()
        if len(code) != 2 or not code.isalpha():
            return ""
        return chr(0x1F1E6 + ord(code[0]) - ord("A")) + chr(0x1F1E6 + ord(code[1]) - ord("A"))

    def _flag_cell_text(self, iso2: str) -> str:
        code = str(iso2 or "").strip().upper()
        if len(code) != 2 or not code.isalpha():
            return ""
        return code

    def _country_info_for_token(self, token: str) -> tuple[str, str] | None:
        t = self._normalize_callsign_token(token)
        if not t:
            return None
        world = self._country_from_world_prefixes(t)
        if world is not None:
            return world
        # Fallback patterns for UI when cty.csv does not cover edge cases.
        for pattern, country, iso2 in CALL_COUNTRY_PATTERNS:
            try:
                if re.match(pattern, t):
                    return country, iso2
            except re.error:
                continue
        return None

    def _country_info_for_call(self, call: str, template_id: str | None = None) -> tuple[str, str]:
        normalized = self.normalize_call(call)
        if not normalized:
            return "", ""
        tid = str(template_id if template_id is not None else self.current_template_id).strip().lower()
        scheme = self._template_log_kind(tid)
        cache_key = (scheme, normalized)
        cached = self._call_country_cache.get(cache_key)
        if cached is not None:
            return cached

        # Division numbers and amateur-radio prefixes are different naming
        # systems and must never be used as mutual fallbacks.
        if scheme == "11m":
            info_11m = self._country_info_for_11m_division(normalized)
            result = info_11m if info_11m is not None else ("Desconocido", "")
            self._call_country_cache[cache_key] = result
            return result

        token = self._call_for_country_lookup(normalized)
        if not token:
            return "", ""
        info = self._country_info_for_token(token)
        if info is not None:
            self._call_country_cache[cache_key] = info
            return info
        fallback = ("Desconocido", "")
        self._call_country_cache[cache_key] = fallback
        return fallback

    def _load_flag_image(self, iso2: str, width: int, height: int) -> tk.PhotoImage | None:
        code = str(iso2 or "").strip().lower()
        if len(code) != 2:
            return None
        key = (code, int(width), int(height))
        if key in self._flag_image_cache:
            return self._flag_image_cache[key]
        svg_path = os.path.join(self.flags_svg_dir, f"{code}.svg")
        if not os.path.isfile(svg_path):
            return None
        png_path = os.path.join(self.flags_png_cache_dir, f"{code}_{int(width)}x{int(height)}.png")
        if not os.path.isfile(png_path):
            try:
                subprocess.run(
                    [
                        "rsvg-convert",
                        "-w",
                        str(int(width)),
                        "-h",
                        str(int(height)),
                        "-o",
                        png_path,
                        svg_path,
                    ],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                return None
        if not os.path.isfile(png_path):
            return None
        try:
            image = tk.PhotoImage(file=png_path)
        except Exception:
            return None
        self._flag_image_cache[key] = image
        return image

    def _update_call_country_display(self):
        if not self._has_field("call"):
            self.country_var.set("")
            if self._country_label is not None:
                self._country_label.configure(image="")
            self._country_flag_image = None
            return
        call = self.normalize_call(self.get_form_value("call"))
        if not call:
            self.country_var.set("")
            if self._country_label is not None:
                self._country_label.configure(image="")
            self._country_flag_image = None
            return
        country, iso2 = self._country_info_for_call(call, self.current_template_id)
        self.country_var.set(country)
        icon = self._load_flag_image(iso2, 28, 19)
        self._country_flag_image = icon
        if self._country_label is not None:
            self._country_label.configure(image=icon if icon is not None else "")

    def _hamqth_clean_text(self, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        parts = [p.strip() for p in re.split(r"\s*,\s*", text) if p.strip()]
        unique: list[str] = []
        seen: set[str] = set()
        for part in parts:
            key = part.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(part)
        cleaned = ", ".join(unique)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,")
        return cleaned

    def _hamqth_log(self, message: str):
        try:
            os.makedirs(LOGS_DIR, exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(HAMQTH_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] {message}\n")
        except Exception:
            pass

    def _hamqth_fetch(self, call: str, user: str, pwd: str) -> dict:
        self._hamqth_log(f"lookup start call={call} user={user}")

        def strip_ns(root_node):
            for elem in root_node.iter():
                tag = getattr(elem, "tag", "")
                if isinstance(tag, str) and "}" in tag:
                    elem.tag = tag.split("}", 1)[1]
            return root_node

        def fetch_xml(url: str, form: dict | None = None) -> bytes:
            headers = {"User-Agent": "PoorSDR4/1.0"}
            data = None
            if form is not None:
                data = urllib.parse.urlencode(form).encode("utf-8")
                headers["Content-Type"] = "application/x-www-form-urlencoded"
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as resp:
                return resp.read()

        def parse_session(xml_bytes: bytes) -> tuple[str, str]:
            root_node = strip_ns(ET.fromstring(xml_bytes))
            return (
                (root_node.findtext("./session/session_id") or "").strip(),
                (root_node.findtext("./session/error") or "").strip(),
            )

        login_q = urllib.parse.urlencode({"u": user, "p": pwd, "prg": "PoorSDR4"})
        login_url = f"https://www.hamqth.com/xml.php?{login_q}"
        xml_login = fetch_xml(login_url, form=None)
        try:
            session_id, err = parse_session(xml_login)
        except Exception as exc:
            sample = xml_login[:300].decode("utf-8", errors="replace")
            self._hamqth_log(f"login xml parse error: {exc} sample={sample!r}")
            raise RuntimeError("HamQTH devolvió una respuesta inválida al iniciar sesión.")
        if not session_id:
            try:
                xml_login_post = fetch_xml("https://www.hamqth.com/xml.php", form={"u": user, "p": pwd, "prg": "PoorSDR4"})
                session_id_post, err_post = parse_session(xml_login_post)
                if session_id_post:
                    session_id = session_id_post
                    err = ""
                elif err_post:
                    err = err_post
            except Exception as exc:
                self._hamqth_log(f"login post fallback failed: {exc}")
        if not session_id:
            self._hamqth_log(f"login failed: error={err!r}")
            raise RuntimeError(err or "HamQTH: no se pudo obtener session_id")

        lookup_q = urllib.parse.urlencode({"id": session_id, "callsign": call, "prg": "PoorSDR4"})
        lookup_url = f"https://www.hamqth.com/xml.php?{lookup_q}"
        xml_lookup = fetch_xml(lookup_url, form=None)
        try:
            root2 = strip_ns(ET.fromstring(xml_lookup))
        except Exception as exc:
            sample = xml_lookup[:300].decode("utf-8", errors="replace")
            self._hamqth_log(f"lookup xml parse error: {exc} sample={sample!r}")
            raise RuntimeError("HamQTH devolvió una respuesta inválida en la consulta.")
        err2 = (root2.findtext("./session/error") or "").strip()
        if err2:
            self._hamqth_log(f"lookup failed: error={err2!r}")
            raise RuntimeError(f"HamQTH: {err2}")
        cs = root2.find("./search")
        if cs is None:
            self._hamqth_log("lookup empty search node")
            raise RuntimeError("HamQTH: respuesta vacía para ese indicativo")

        data = {
            "nick": (cs.findtext("nick") or "").strip(),
            "adr_name": (cs.findtext("adr_name") or "").strip(),
            "qth": (cs.findtext("qth") or "").strip(),
            "district": (cs.findtext("district") or "").strip(),
            "state": (cs.findtext("state") or "").strip(),
            "us_state": (cs.findtext("us_state") or "").strip(),
            "adr_city": (cs.findtext("adr_city") or "").strip(),
            "adr_zip": (cs.findtext("adr_zip") or "").strip(),
            "adr_country": (cs.findtext("adr_country") or "").strip(),
            "grid": (cs.findtext("grid") or "").strip(),
        }
        self._hamqth_log(
            "lookup ok "
            + ", ".join(
                [
                    f"nick={data.get('nick','')!r}",
                    f"qth={data.get('qth','')!r}",
                    f"city={data.get('adr_city','')!r}",
                    f"grid={data.get('grid','')!r}",
                ]
            )
        )
        return data

    def lookup_hamqth(self, silent: bool = False, expected_call: str | None = None):
        call = self.normalize_call(self.get_form_value("call")) if self._has_field("call") else ""
        if expected_call is not None and call != self.normalize_call(expected_call):
            return
        if not call:
            if not silent:
                messagebox.showinfo(APP_TITLE, "Introduce un indicativo en el campo CALL.")
            return
        user = str(self.hamqth_user_var.get() or "").strip()
        pwd = str(self.hamqth_pass_var.get() or "").strip()
        if not user or not pwd:
            if not silent:
                messagebox.showerror(APP_TITLE, "Configura usuario y clave de HamQTH en Ajustes > Estación / actividad.")
            self._hamqth_log("lookup skipped: missing user/password")
            return

        def apply_data(data: dict):
            try:
                op_name = self._hamqth_clean_text(data.get("nick") or data.get("adr_name") or "")
                if op_name:
                    if self._has_field("name"):
                        self.set_form_value("name", op_name)
                    elif self._has_field("operator_name"):
                        self.set_form_value("operator_name", op_name)
                qth_chunks = [
                    data.get("qth", ""),
                    data.get("district", ""),
                    data.get("state", ""),
                    data.get("us_state", ""),
                    data.get("adr_city", ""),
                    data.get("adr_zip", ""),
                    data.get("adr_country", ""),
                ]
                qth_raw = ", ".join([str(x).strip() for x in qth_chunks if str(x).strip()])
                qth = self._hamqth_clean_text(qth_raw)
                if qth and self._has_field("qth"):
                    self.set_form_value("qth", qth)
                grid = str(data.get("grid") or "").strip().upper()
                if grid and self._has_field("grid"):
                    self.set_form_value("grid", grid)
                self._schedule_settings_save()
                self._hamqth_last_call = call
                if not silent:
                    messagebox.showinfo(APP_TITLE, f"HamQTH: datos cargados para {call}.")
            except Exception as exc:
                if not silent:
                    messagebox.showerror(APP_TITLE, f"HamQTH: error al aplicar datos:\n{exc}")
                self._hamqth_log(f"apply_data failed: {exc}")

        def worker():
            try:
                data = self._hamqth_fetch(call, user, pwd)
            except Exception as exc:
                try:
                    if not silent:
                        self.root.after(0, lambda e=exc: messagebox.showerror(APP_TITLE, f"Consulta HamQTH fallida:\n{e}"))
                    else:
                        self._hamqth_log(f"auto lookup failed for {call}: {exc}")
                except Exception:
                    pass
                return
            try:
                self.root.after(0, lambda: apply_data(data))
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True, name="hamqth-lookup").start()

    def update_selected_qso(self):
        idx = self.selected_qso_index
        if idx is None or not (0 <= idx < len(self.current_qsos)):
            messagebox.showinfo(APP_TITLE, "Selecciona un QSO en la tabla para editar.")
            return
        original = self.current_qsos[idx]
        tpl = self.current_template
        ctx = self._template_ctx(original.get("timestamp_utc", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")), original=original)
        try:
            updated = tpl.build_qso(ctx)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        self.current_qsos[idx] = updated
        updated["__db_id"] = original.get("__db_id")
        self._db_update_qso(self.current_template_id, updated)
        self._rebuild_dupe_index()
        self._save_template_log(self.current_template_id)
        self._refresh_qso_table()
        if idx in self._view_indices:
            view_idx = self._view_indices.index(idx)
            children = self.tree.get_children()
            if 0 <= view_idx < len(children):
                self.tree.selection_set(children[view_idx])
                self.tree.focus(children[view_idx])
        self._recompute_next_serial()
        self._update_stats()
        self.check_dupe()

    def delete_selected_qso(self):
        idx = self.selected_qso_index
        if idx is None or not (0 <= idx < len(self.current_qsos)):
            messagebox.showinfo(APP_TITLE, "Selecciona un QSO en la tabla para eliminar.")
            return
        q = self.current_qsos[idx]
        if not messagebox.askyesno(APP_TITLE, f"¿Eliminar QSO {q.get('call', '')} {q.get('band', '')} {q.get('mode', '')}?"):
            return
        self._db_delete_qso(self.current_template_id, q)
        self.current_qsos.pop(idx)
        self._rebuild_dupe_index()
        self._save_template_log(self.current_template_id)
        self.selected_qso_index = None
        self._refresh_qso_table()
        self._recompute_next_serial()
        self._update_stats()
        self.clear_entry(keep_report=True)

    def clear_entry(self, keep_report: bool = False):
        self.selected_qso_index = None
        for field in self.current_template.FORM_FIELDS:
            key = field.get("key")
            if not key:
                continue
            if keep_report and key in ("rst_sent", "rst_recv"):
                continue
            default = str(field.get("default") or "")
            self.set_form_value(key, default)
        self.dupe_var.set("")
        self._refresh_serial_fields()

    def _station_snapshot(self, template_id: str | None = None) -> dict:
        tid = template_id if template_id in self.templates else self.current_template_id
        operator = self.operator_var.get().strip()
        if self._template_log_kind(tid) == "11m":
            op11 = self.operator_11_var.get().strip()
            if op11:
                operator = op11
        return {
            "operator": operator,
            "my_grid": self.grid_var.get().strip(),
            "contest": self.contest_var.get().strip(),
            "template_id": tid,
            "template_name": self.templates[tid].TEMPLATE_NAME,
        }

    def _update_stats(self):
        self.rate_var.set(f"QSOs: {len(self.current_qsos)}")
        prefixes = {self.prefix_of(str(q.get("call", ""))) for q in self.current_qsos if self.prefix_of(str(q.get("call", "")))}
        self.mult_var.set(f"Multiplicadores: {len(prefixes)}")

    def prefix_of(self, call: str) -> str:
        call = call.upper().strip()
        if not call:
            return ""
        prefix = []
        for ch in call:
            prefix.append(ch)
            if ch.isdigit():
                break
        return "".join(prefix)

    def export_csv(self):
        template_id = self._resolve_log_ops_template_id()
        template_name = self.templates[template_id].TEMPLATE_NAME
        qsos = self._get_template_qsos(template_id)
        if not qsos:
            messagebox.showinfo(APP_TITLE, f"No hay QSOs para exportar en la plantilla '{template_name}'.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=f"{template_name}.csv",
            filetypes=[("CSV", "*.csv")],
        )
        if not path:
            return
        keys = sorted({k for q in qsos for k in q.keys()})
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            for qso in qsos:
                writer.writerow({k: qso.get(k, "") for k in keys})
        messagebox.showinfo(APP_TITLE, f"CSV exportado ({template_name}) en:\n{path}")

    def open_logs_directory(self):
        try:
            os.makedirs(LOGS_DIR, exist_ok=True)
            if os.name == "nt":
                os.startfile(LOGS_DIR)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", LOGS_DIR])
            else:
                subprocess.Popen(["xdg-open", LOGS_DIR])
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"No se pudo abrir la carpeta de logs:\n{exc}")

    def import_log(self):
        template_id = self._resolve_log_ops_template_id()
        template_name = self.templates[template_id].TEMPLATE_NAME
        path = filedialog.askopenfilename(
            title="Importar log",
            filetypes=[
                ("Logs compatibles", "*.csv *.adi *.adif"),
                ("CSV", "*.csv"),
                ("ADIF", "*.adi *.adif"),
                ("Todos", "*.*"),
            ],
        )
        if not path:
            return
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext == ".csv":
                added = self._import_csv(path, template_id)
            elif ext in (".adi", ".adif"):
                added = self._import_adif(path, template_id)
            else:
                messagebox.showerror(APP_TITLE, "Formato no soportado. Usa CSV o ADIF.")
                return
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"No se pudo importar el log:\n{exc}")
            return

        self._save_template_log(template_id)
        if template_id == self.current_template_id:
            self._refresh_qso_table()
            self._recompute_next_serial()
            self._update_stats()
            self.check_dupe()
        messagebox.showinfo(APP_TITLE, f"Importación completada en '{template_name}'. QSOs añadidos: {added}")

    def _backup_filename_for_template(self, template_id: str) -> str:
        template_name = str(self.templates.get(template_id).TEMPLATE_NAME if template_id in self.templates else template_id)
        safe_name = self._sanitize_db_basename(template_name) or self._safe_template_id(template_id)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{safe_name}_backup_{stamp}{DEFAULT_DB_EXT}"

    def _build_backup_path(self, template_id: str) -> str | None:
        template_name = str(self.templates.get(template_id).TEMPLATE_NAME if template_id in self.templates else template_id)
        initial = self._backup_filename_for_template(template_id)
        return filedialog.asksaveasfilename(
            title=f"Guardar copia de seguridad de {template_name}",
            defaultextension=DEFAULT_DB_EXT,
            initialfile=initial,
            filetypes=[("Base de datos SQLite", f"*{DEFAULT_DB_EXT}"), ("Todos", "*.*")],
        )

    def _backup_template_database(self, template_id: str, prompt: bool = True) -> str | None:
        template_id = str(template_id or "").strip().lower()
        if template_id not in self.templates:
            messagebox.showerror(APP_TITLE, "Plantilla no válida para la copia de seguridad.")
            return None
        source_path = self._template_db_path(template_id)
        if not os.path.isfile(source_path):
            messagebox.showinfo(APP_TITLE, "No hay base de datos existente para copiar.")
            return None
        dest_path = self._build_backup_path(template_id) if prompt else ""
        if not dest_path:
            return None
        dest_path = os.path.abspath(dest_path)
        if os.path.abspath(source_path) == dest_path:
            messagebox.showerror(APP_TITLE, "La copia de seguridad no puede guardarse sobre la propia base.")
            return None
        if os.path.exists(dest_path):
            if not messagebox.askyesno(APP_TITLE, f"El archivo ya existe.\n\n¿Sobrescribirlo?\n{dest_path}"):
                return None
        os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
        try:
            source_conn = self._db_connect(template_id)
            with sqlite3.connect(dest_path, timeout=10, check_same_thread=False) as backup_conn:
                self._ensure_db_schema(backup_conn)
                source_conn.backup(backup_conn)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"No se pudo crear la copia de seguridad:\n{exc}")
            return None
        return dest_path

    def backup_current_database(self):
        template_id = self.current_template_id
        if template_id not in self.templates:
            messagebox.showerror(APP_TITLE, "No hay plantilla activa para copiar.")
            return
        path = self._backup_template_database(template_id, prompt=True)
        if path:
            messagebox.showinfo(APP_TITLE, f"Copia de seguridad creada en:\n{path}")

    def _qso_exists_in_template_db(self, template_id: str, qso: dict) -> bool:
        try:
            conn = self._db_connect(template_id)
            row = conn.execute(
                """
                SELECT 1
                FROM qsos
                WHERE timestamp_utc=? AND call=? AND band=? AND mode=? AND freq_hz=?
                LIMIT 1
                """,
                (
                    str(qso.get("timestamp_utc", "")),
                    str(qso.get("call", "")),
                    str(qso.get("band", "")),
                    str(qso.get("mode", "")),
                    int(qso.get("freq_hz", 0) or 0),
                ),
            ).fetchone()
            return row is not None
        except Exception:
            return False

    def _find_matching_qso_row_in_template_db(self, template_id: str, qso: dict):
        try:
            conn = self._db_connect(template_id)
            rows = conn.execute(
                """
                SELECT id, timestamp_utc, payload
                FROM qsos
                WHERE call=? AND band=? AND mode=? AND freq_hz=?
                ORDER BY id ASC
                """,
                (
                    str(qso.get("call", "")),
                    str(qso.get("band", "")),
                    str(qso.get("mode", "")),
                    int(qso.get("freq_hz", 0) or 0),
                ),
            ).fetchall()
            if not rows:
                return None
            target_ts = str(qso.get("timestamp_utc", "") or "").strip()
            for row in rows:
                row_ts = str(row["timestamp_utc"] or "").strip()
                if row_ts == target_ts:
                    return row
            return rows[0]
        except Exception:
            return None

    def _update_qso_timestamp_in_template_db(self, template_id: str, qso: dict):
        row = self._find_matching_qso_row_in_template_db(template_id, qso)
        if row is None:
            return False
        rowid = int(row["id"])
        country, iso = self._country_info_for_call(str(qso.get("call", "")), template_id)
        qso["country_name"] = country
        qso["country_iso"] = iso
        payload = self._db_payload_from_qso(qso)
        conn = self._db_connect(template_id)
        conn.execute(
            """
            UPDATE qsos
            SET timestamp_utc=?, call=?, band=?, mode=?, freq_hz=?, country_name=?, country_iso=?, payload=?
            WHERE id=?
            """,
            (
                str(qso.get("timestamp_utc", "")),
                str(qso.get("call", "")),
                str(qso.get("band", "")),
                str(qso.get("mode", "")),
                int(qso.get("freq_hz", 0) or 0),
                str(qso.get("country_name", "")),
                str(qso.get("country_iso", "")),
                payload,
                rowid,
            ),
        )
        conn.commit()
        qso["__db_id"] = rowid
        return True

    def _adif_row_from_existing_qso(self, qso: dict) -> dict:
        timestamp = str(qso.get("timestamp_utc", "") or "").strip()
        qso_date = ""
        time_on = ""
        if len(timestamp) >= 19 and timestamp[4] == "-" and timestamp[7] == "-" and timestamp[10] == " ":
            qso_date = timestamp[0:10].replace("-", "")
            time_on = timestamp[11:19].replace(":", "")
        return {
            "CALL": str(qso.get("call", "") or "").strip().upper(),
            "QSO_DATE": qso_date,
            "TIME_ON": time_on,
            "BAND": str(qso.get("band", "") or "").strip(),
            "MODE": str(qso.get("mode", "") or "").strip(),
            "FREQ": f"{float(qso.get('freq_hz', 0) or 0) / 1_000_000:.6f}",
            "RST_SENT": str(qso.get("rst_sent", "") or "").strip(),
            "RST_RCVD": str(qso.get("rst_recv", "") or "").strip(),
            "NAME": str(qso.get("name", "") or "").strip(),
            "QTH": str(qso.get("qth", "") or "").strip(),
            "GRIDSQUARE": str(qso.get("grid", "") or "").strip(),
            "COMMENT": str(qso.get("notes", "") or "").strip(),
        }

    def _preview_import_to_general(self, source_template_id: str) -> tuple[int, int, int, str]:
        dest_template_id = self._main_log_id_for(source_template_id)
        source_qsos = list(self._get_template_qsos(source_template_id))
        target_count = len(self._get_template_qsos(dest_template_id))
        insert_count = 0
        update_count = 0
        skip_count = 0
        for source_qso in source_qsos:
            candidate = self._qso_from_import_row(
                self._adif_row_from_existing_qso(source_qso),
                adif=True,
                template_id=dest_template_id,
            )
            if candidate is None:
                skip_count += 1
                continue
            match = self._find_matching_qso_row_in_template_db(dest_template_id, candidate)
            if match is None:
                insert_count += 1
                continue
            match_ts = str(match["timestamp_utc"] or "").strip()
            if match_ts == str(candidate.get("timestamp_utc", "") or "").strip():
                skip_count += 1
            else:
                update_count += 1
        lines = [
            f"Origen: {self.templates[source_template_id].TEMPLATE_NAME}",
            f"Destino: {self.templates[dest_template_id].TEMPLATE_NAME}",
            f"QSOs en origen: {len(source_qsos)}",
            f"QSOs ya en destino: {target_count}",
            f"Se añadirán: {insert_count}",
            f"Se corregirán: {update_count}",
            f"Se omitirán: {skip_count}",
        ]
        return insert_count, update_count, skip_count, "\n".join(lines)

    def import_current_log_to_general(self):
        source_template_id = self.current_template_id
        if source_template_id not in self.templates:
            messagebox.showerror(APP_TITLE, "No hay plantilla activa para importar.")
            return
        if self._is_main_log_template(source_template_id):
            messagebox.showinfo(APP_TITLE, "El log activo ya es un libro principal.")
            return

        dest_template_id = self._main_log_id_for(source_template_id)
        if dest_template_id not in self.templates:
            messagebox.showerror(APP_TITLE, "No existe el libro principal correspondiente.")
            return

        insert_count, update_count, skip_count, preview_text = self._preview_import_to_general(source_template_id)
        if not messagebox.askyesno(
            APP_TITLE,
            preview_text + "\n\n¿Quieres continuar con la copia de seguridad y el volcado al libro principal?",
        ):
            return

        backup_path = self._backup_template_database(source_template_id, prompt=True)
        if not backup_path:
            return

        source_qsos = list(self._get_template_qsos(source_template_id))
        if not source_qsos:
            messagebox.showinfo(APP_TITLE, "La base actual está vacía, no hay nada para importar.")
            return

        target_qsos = self._get_template_qsos(dest_template_id)
        added = 0
        updated = 0
        skipped = 0
        for source_qso in source_qsos:
            candidate = self._qso_from_import_row(
                self._adif_row_from_existing_qso(source_qso),
                adif=True,
                template_id=dest_template_id,
            )
            if candidate is None:
                skipped += 1
                continue
            match = self._find_matching_qso_row_in_template_db(dest_template_id, candidate)
            if match is not None:
                match_ts = str(match["timestamp_utc"] or "").strip()
                candidate_ts = str(candidate.get("timestamp_utc", "") or "").strip()
                if match_ts == candidate_ts:
                    skipped += 1
                    continue
                candidate["__db_id"] = int(match["id"])
                self._db_update_qso(dest_template_id, candidate)
                for idx, existing in enumerate(target_qsos):
                    if int(existing.get("__db_id", -1)) == int(match["id"]):
                        target_qsos[idx] = candidate
                        break
                updated += 1
                continue
            candidate["__db_id"] = self._db_insert_qso(dest_template_id, candidate)
            target_qsos.append(candidate)
            added += 1

        if dest_template_id in self.logs_by_template:
            self.logs_by_template[dest_template_id] = target_qsos
        if dest_template_id == self.current_template_id:
            self._refresh_qso_table()
            self._recompute_next_serial()
            self._update_stats()
            self.check_dupe()
        messagebox.showinfo(
            APP_TITLE,
            (
                f"Volcado a {self.templates[dest_template_id].TEMPLATE_NAME} completado.\n"
                f"Backup: {backup_path}\n"
                f"QSOs añadidos: {added}\n"
                f"QSOs corregidos: {updated}\n"
                f"QSOs omitidos por duplicado o error: {skipped}"
            ),
        )

    def _import_csv(self, path: str, template_id: str) -> int:
        added = 0
        target_qsos = self._get_template_qsos(template_id)
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                qso = self._qso_from_import_row(row, adif=False, template_id=template_id)
                if qso is None:
                    continue
                qso["__db_id"] = self._db_insert_qso(template_id, qso)
                target_qsos.append(qso)
                added += 1
        if template_id == self.current_template_id and added:
            self._rebuild_dupe_index()
        return added

    def _import_adif(self, path: str, template_id: str) -> int:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        records = self._parse_adif_records(text)
        added = 0
        target_qsos = self._get_template_qsos(template_id)
        for rec in records:
            qso = self._qso_from_import_row(rec, adif=True, template_id=template_id)
            if qso is None:
                continue
            qso["__db_id"] = self._db_insert_qso(template_id, qso)
            target_qsos.append(qso)
            added += 1
        if template_id == self.current_template_id and added:
            self._rebuild_dupe_index()
        return added

    def _parse_adif_records(self, text: str) -> list[dict]:
        records = []
        chunks = re.split(r"(?is)<\s*eor\s*>", text or "")
        for chunk in chunks:
            raw = chunk.strip()
            if not raw:
                continue
            rec = {}
            idx = 0
            upper = raw.upper()
            while idx < len(raw):
                start = upper.find("<", idx)
                if start == -1:
                    break
                end = upper.find(">", start + 1)
                if end == -1:
                    break
                token = raw[start + 1 : end]
                parts = token.split(":")
                if len(parts) < 2:
                    idx = end + 1
                    continue
                key = parts[0].strip().upper()
                try:
                    length = int(parts[1])
                except ValueError:
                    idx = end + 1
                    continue
                value_start = end + 1
                value_end = value_start + length
                value = raw[value_start:value_end]
                rec[key] = value
                idx = value_end
            if rec:
                records.append(rec)
        return records

    def _qso_from_import_row(self, row: dict, adif: bool = False, template_id: str | None = None) -> dict | None:
        if not isinstance(row, dict):
            return None
        data = {str(k).strip(): ("" if v is None else str(v).strip()) for k, v in row.items()}
        data_l = {str(k).strip().lower(): v for k, v in data.items()}
        upper = {k.upper(): v for k, v in data.items()}
        tid = template_id if template_id in self.templates else self.current_template_id
        tpl = self.templates[tid]

        def first_non_empty(source: dict[str, str], keys: list[str]) -> str:
            for key in keys:
                key_l = str(key or "").strip().lower()
                val = source.get(key_l, "")
                if str(val or "").strip():
                    return str(val).strip()
            return ""

        def parse_csv_freq_hz(raw: str) -> int:
            text = str(raw or "").strip().replace(",", ".")
            if not text:
                return 0
            try:
                value = float(text)
            except ValueError:
                return 0
            if value <= 0:
                return 0
            # Common CSV conventions:
            # - Hz (e.g. 27575000)
            # - kHz (e.g. 27575)
            # - MHz (e.g. 27.575)
            if value >= 1_000_000:
                return int(round(value))
            if value >= 1_000:
                return int(round(value * 1_000))
            return int(round(value * 1_000_000))

        def parse_csv_timestamp(default_ts: str) -> str:
            date_raw = first_non_empty(
                data_l,
                ["date", "fecha", "qso_date", "timestamp_utc", "timestamp", "utc_date", "datetime"],
            )
            time_raw = first_non_empty(data_l, ["utc", "time_on", "time", "hora", "utc_time"])
            if not date_raw and not time_raw:
                return default_ts
            parsed_date: datetime | None = None
            for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d"):
                try:
                    parsed_date = datetime.strptime(date_raw, fmt)
                    break
                except Exception:
                    continue
            if parsed_date is None:
                return default_ts
            hh, mm, ss = "00", "00", "00"
            t = str(time_raw or "").strip()
            if t:
                m = re.match(r"^\s*(\d{1,2})[:h]?(\d{2})(?::?(\d{2}))?\s*$", t)
                if m:
                    hh = f"{int(m.group(1)):02d}"
                    mm = f"{int(m.group(2)):02d}"
                    ss = f"{int(m.group(3)) if m.group(3) else 0:02d}"
            return f"{parsed_date.year:04d}-{parsed_date.month:02d}-{parsed_date.day:02d} {hh}:{mm}:{ss}"

        csv_aliases: dict[str, list[str]] = {
            "call": ["call", "dx", "callsign", "indicativo"],
            "rst_sent": ["rst_sent", "rst_tx", "snt", "rst"],
            "rst_recv": ["rst_recv", "rst_rcvd", "rst_rx", "rcv", "rst"],
            "name": ["name", "nombre"],
            "operator_name": ["operator_name", "operator", "submitter"],
            "qth": ["qth", "location"],
            "grid": ["grid", "gridsquare", "locator"],
            "power_w": ["power_w", "tx_pwr", "power", "pwr"],
            "serial_sent": ["serial_sent", "stx", "sent", "tx_serial"],
            "serial_recv": ["serial_recv", "srx", "recv", "rx_serial"],
            "notes": ["notes", "comment", "remarks", "qsl_info", "path", "wkd"],
            "mode": ["mode"],
            "band": ["band"],
            "freq": ["freq_hz", "frequency_hz", "freq", "frequency"],
        }

        def get_value(key: str) -> str:
            if adif:
                mapping = {
                    "call": "CALL",
                    "rst_sent": "RST_SENT",
                    "rst_recv": "RST_RCVD",
                    "name": "NAME",
                    "operator_name": "OPERATOR",
                    "qth": "QTH",
                    "grid": "GRIDSQUARE",
                    "power_w": "TX_PWR",
                    "serial_sent": "STX",
                    "serial_recv": "SRX",
                    "notes": "COMMENT",
                }
                adif_key = mapping.get(key, "")
                return upper.get(adif_key, "")
            aliases = csv_aliases.get(key, [key])
            return first_non_empty(data_l, aliases)

        freq_hz = 0
        if adif:
            freq_raw = upper.get("FREQ", "")
            if freq_raw:
                try:
                    freq_hz = int(round(float(freq_raw.replace(",", ".")) * 1_000_000))
                except ValueError:
                    freq_hz = 0
        else:
            freq_raw = first_non_empty(data_l, csv_aliases["freq"])
            freq_hz = parse_csv_freq_hz(freq_raw)
        if freq_hz <= 0:
            freq_hz = self._safe_current_freq()

        band = upper.get("BAND", "") if adif else first_non_empty(data_l, csv_aliases["band"])
        if band:
            band = band.lower().replace("m", "m")
            if not band.endswith("m"):
                band = f"{band}m"
        if not band:
            band = self.band_from_freq(freq_hz)
        if self._template_log_kind(tid) == "11m" and (not band or band == "?"):
            band = "11m"

        mode = upper.get("MODE", "") if adif else first_non_empty(data_l, csv_aliases["mode"])
        mode = MODE_MAP.get(mode.upper(), mode.upper()) if mode else self.current_mode

        qso_date = upper.get("QSO_DATE", "") if adif else ""
        time_on = upper.get("TIME_ON", "") if adif else ""
        timestamp_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        if qso_date and len(qso_date) == 8:
            hh = "00"
            mm = "00"
            ss = "00"
            if len(time_on) >= 4:
                hh = time_on[0:2]
                mm = time_on[2:4]
                if len(time_on) >= 6:
                    ss = time_on[4:6]
            timestamp_utc = f"{qso_date[0:4]}-{qso_date[4:6]}-{qso_date[6:8]} {hh}:{mm}:{ss}"
        elif not adif:
            timestamp_utc = parse_csv_timestamp(timestamp_utc)

        # Split imported RST patterns like "5/9" into sent/recv when available.
        if not adif:
            rst_raw = first_non_empty(data_l, ["rst"])
            if rst_raw and "/" in rst_raw:
                left, right = [p.strip() for p in rst_raw.split("/", 1)]
                if left and not first_non_empty(data_l, ["rst_sent", "rst_tx", "snt"]):
                    data_l["rst_sent"] = left
                if right and not first_non_empty(data_l, ["rst_recv", "rst_rcvd", "rst_rx", "rcv"]):
                    data_l["rst_recv"] = right

        ctx = {
            "timestamp_utc": timestamp_utc,
            "band": band,
            "mode": mode,
            "freq_hz": freq_hz,
            "next_serial": self.next_serial,
            "auto_serial": False,
            "original": None,
            "get": get_value,
        }
        try:
            return tpl.build_qso(ctx)
        except Exception:
            return None

    def export_adif(self):
        template_id = self._resolve_log_ops_template_id()
        template_name = self.templates[template_id].TEMPLATE_NAME
        qsos = self._get_template_qsos(template_id)
        if not qsos:
            messagebox.showinfo(APP_TITLE, f"No hay QSOs para exportar en la plantilla '{template_name}'.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".adi",
            initialfile=f"{template_name}.adi",
            filetypes=[("ADIF", "*.adi")],
        )
        if not path:
            return
        station = self._station_snapshot(template_id)
        tpl = self.templates[template_id]
        with open(path, "w", encoding="utf-8") as f:
            f.write("Generado por NMN1M <EOH>\n")
            for q in qsos:
                adif = tpl.adif_fields(q, station)
                line = ""
                for key, value in adif.items():
                    if value is None:
                        continue
                    text = str(value)
                    if not text:
                        continue
                    line += f"<{key}:{len(text)}>{text}"
                f.write(line + " <EOR>\n")
        messagebox.showinfo(APP_TITLE, f"ADIF exportado ({template_name}) en:\n{path}")

    def export_cabrillo(self):
        template_id = self._resolve_log_ops_template_id()
        template_name = self.templates[template_id].TEMPLATE_NAME
        qsos = self._get_template_qsos(template_id)
        if not qsos:
            messagebox.showinfo(APP_TITLE, f"No hay QSOs para exportar en la plantilla '{template_name}'.")
            return
        tpl = self.templates[template_id]
        if not bool(getattr(tpl, "ALLOW_CABRILLO", False)) or not hasattr(tpl, "cabrillo_header") or not hasattr(tpl, "cabrillo_qso_line"):
            messagebox.showinfo(APP_TITLE, "La plantilla actual no tiene exportación Cabrillo.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".log",
            initialfile=f"{template_name}.log",
            filetypes=[("Cabrillo", "*.log")],
        )
        if not path:
            return
        station = self._station_snapshot(template_id)
        with open(path, "w", encoding="utf-8") as f:
            for line in tpl.cabrillo_header(station):
                f.write(line.rstrip("\n") + "\n")
            for q in qsos:
                f.write(tpl.cabrillo_qso_line(q, station).rstrip("\n") + "\n")
            f.write("END-OF-LOG:\n")
        messagebox.showinfo(APP_TITLE, f"Cabrillo exportado ({template_name}) en:\n{path}")

    def on_close(self):
        self._cancel_auto_connect_retry()
        self._stop_sync_server()
        for template_id in list(self.logs_by_template.keys()):
            self._save_template_log(template_id)
        for path in list(self._db_connections.keys()):
            self._close_db_connection_path(path)
        self._save_settings()
        self._stop_wsjtx_udp_listener()
        self.disconnect_rig()
        self.root.destroy()


def _apply_theme(root: tk.Tk):
    selected_bg = THEME_SELECTED_BG
    try:
        cfg_path = os.fspath(poorsdr_paths.config_file())
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        ui_cfg = cfg.get("ui", {}) if isinstance(cfg.get("ui"), dict) else {}
        bg = str(
            ui_cfg.get("background_image", cfg.get("Imagen_Fondo", "back.jpg"))
            or "back.jpg"
        ).strip()
        selected_bg = THEME_ACCENT_BY_BACKGROUND.get(bg, THEME_SELECTED_BG)
    except Exception:
        selected_bg = THEME_SELECTED_BG

    accent = selected_bg  # acento del tema activo de la consola
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    root.configure(bg=THEME_BG)

    style.configure(
        ".", background=THEME_PANEL, foreground=THEME_TEXT, fieldbackground=THEME_INPUT,
        bordercolor=THEME_BORDER, lightcolor=THEME_PANEL, darkcolor=THEME_PANEL,
        troughcolor=THEME_BG, focuscolor=accent, insertcolor=THEME_TEXT, arrowcolor=THEME_TEXT,
    )
    style.configure("TFrame", background=THEME_BG)
    style.configure("Panel.TFrame", background=THEME_PANEL)
    style.configure("TLabel", background=THEME_PANEL, foreground=THEME_TEXT)
    style.configure("Muted.TLabel", background=THEME_PANEL, foreground=THEME_MUTED)

    style.configure("TLabelframe", background=THEME_PANEL, bordercolor=THEME_BORDER, borderwidth=1)
    style.configure("TLabelframe.Label", background=THEME_PANEL, foreground=THEME_MUTED)

    style.configure("TNotebook", background=THEME_BG, borderwidth=0, tabmargins=(4, 4, 4, 0))
    style.configure("TNotebook.Tab", background=THEME_PANEL, foreground=THEME_MUTED,
                    padding=(14, 6), borderwidth=0)
    style.map("TNotebook.Tab",
              background=[("selected", THEME_BG)],
              foreground=[("selected", accent), ("active", THEME_TEXT)])

    style.configure("TButton", background=THEME_PANEL, foreground=THEME_TEXT, borderwidth=1,
                    padding=(12, 5), relief="flat")
    style.map("TButton",
              background=[("pressed", THEME_BG), ("active", THEME_INPUT_HOVER)],
              bordercolor=[("active", accent), ("focus", accent)],
              foreground=[("disabled", THEME_MUTED)])
    style.configure("Accent.TButton", background=accent, foreground=THEME_BG, borderwidth=0)
    style.map("Accent.TButton", background=[("active", accent), ("pressed", accent)])

    style.configure("TCheckbutton", background=THEME_PANEL, foreground=THEME_TEXT, padding=3)
    style.map("TCheckbutton",
              background=[("active", THEME_PANEL)], foreground=[("active", THEME_TEXT)],
              indicatorcolor=[("selected", accent), ("!selected", THEME_INPUT)])
    style.configure("TRadiobutton", background=THEME_PANEL, foreground=THEME_TEXT, padding=3)
    style.map("TRadiobutton",
              indicatorcolor=[("selected", accent), ("!selected", THEME_INPUT)])

    style.configure("TEntry", fieldbackground=THEME_INPUT, foreground=THEME_TEXT, borderwidth=1,
                    padding=4)
    style.map("TEntry", bordercolor=[("focus", accent)])

    style.configure("TCombobox", fieldbackground=THEME_INPUT, foreground=THEME_TEXT,
                    background=THEME_PANEL, borderwidth=1, padding=3,
                    selectbackground=accent, selectforeground=THEME_BG)
    style.map("TCombobox",
              fieldbackground=[("readonly", THEME_INPUT), ("disabled", THEME_PANEL)],
              foreground=[("disabled", THEME_MUTED)],
              bordercolor=[("focus", accent)])

    style.configure("TSpinbox", fieldbackground=THEME_INPUT, foreground=THEME_TEXT, borderwidth=1,
                    padding=3)
    style.map("TSpinbox", bordercolor=[("focus", accent)])

    style.configure("Treeview", background=THEME_INPUT, foreground=THEME_TEXT,
                    fieldbackground=THEME_INPUT, bordercolor=THEME_BORDER, rowheight=22)
    style.map("Treeview",
              background=[("selected", accent)],
              foreground=[("selected", THEME_BG)])
    style.configure("Treeview.Heading", background=THEME_PANEL, foreground=THEME_MUTED,
                    bordercolor=THEME_BORDER, relief="flat", padding=(6, 4))
    style.map("Treeview.Heading",
              background=[("active", THEME_INPUT_HOVER)],
              foreground=[("active", THEME_TEXT)])

    style.configure("Vertical.TScrollbar", background=THEME_PANEL, troughcolor=THEME_BG,
                    bordercolor=THEME_BG, arrowcolor=THEME_MUTED)
    style.configure("Horizontal.TScrollbar", background=THEME_PANEL, troughcolor=THEME_BG,
                    bordercolor=THEME_BG, arrowcolor=THEME_MUTED)

    # Lista desplegable de los Combobox (Listbox tk clásico).
    for opt, val in (
        ("*TCombobox*Listbox.background", THEME_INPUT),
        ("*TCombobox*Listbox.foreground", THEME_TEXT),
        ("*TCombobox*Listbox.selectBackground", accent),
        ("*TCombobox*Listbox.selectForeground", THEME_BG),
        ("*TCombobox*Listbox.borderWidth", "0"),
    ):
        root.option_add(opt, val)


def main():
    root = tk.Tk()
    _apply_theme(root)
    app = ContestLoggerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
