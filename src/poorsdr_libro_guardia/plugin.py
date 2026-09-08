"""Enganche del plugin: añade el botón "Log" a la consola y lanza el
Libro de Guardia (aplicación Tkinter grande) como subproceso.

``Libro-Guardia.py`` viaja junto a este módulo como recurso del paquete; se
puede apuntar a otra copia con la variable de entorno
``POORSDR_LIBRO_GUARDIA``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from poorsdr.plugins import PluginContext

_BUNDLED = Path(__file__).with_name("Libro-Guardia.py")


def _script_path() -> Path:
    override = os.environ.get("POORSDR_LIBRO_GUARDIA")
    return Path(override).expanduser() if override else _BUNDLED


class LibroGuardiaPlugin:
    id = "libro_guardia"
    name = "Nunca Más, Ni Una Más (NMN1M)"

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None

    def register(self, ctx: PluginContext) -> None:  # noqa: ARG002 - contexto sin uso
        ctx.add_console_button("libro", "Log", self.launch)

    def launch(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return  # ya está abierto
        script = _script_path()
        if not script.is_file():
            return
        self._proc = subprocess.Popen(  # noqa: S603
            [sys.executable, str(script)], cwd=str(script.parent), start_new_session=True
        )

    def shutdown(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()


PLUGIN = LibroGuardiaPlugin()


def run_standalone() -> int:
    """Entry point ``poorsdr-libro-guardia`` para abrirlo sin PoorSDR."""
    script = _script_path()
    if not script.is_file():
        print(f"No se encontró {script}", file=sys.stderr)
        return 1
    return subprocess.call([sys.executable, str(script)], cwd=str(script.parent))
