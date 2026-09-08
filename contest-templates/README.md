# Plantillas de concurso para NMN1M

Plantillas de concurso opcionales para **Nunca Más, Ni Una Más** (NMN1M),
el cuaderno de estación / contest logger de este repositorio. No van
incluidas en la instalación principal — descarga solo la que necesites e
instálala desde la propia aplicación.

## Instalación

1. Descarga el archivo `.py` del concurso que quieras (p. ej. `cq_wpx.py`).
2. En NMN1M: **Concursos → Importar plantilla...**
3. Elige el archivo descargado. La aplicación lo copia a su carpeta de
   plantillas instalada; no hace falta reiniciar.

Instala únicamente plantillas de una fuente de confianza: su código se
ejecuta dentro de la aplicación.

## Disponibles en este repositorio

| Archivo | Concurso | Tipo |
|---|---|---|
| `cq_wpx.py` | CQ WPX | HAM |
| `iaru_hf.py` | IARU HF | HAM |
| `sm.py` | SM | HAM |

## Crear una plantilla propia

Ver [`../src/poorsdr_libro_guardia/templates/README.md`](../src/poorsdr_libro_guardia/templates/README.md)
para el contrato que debe cumplir un archivo de plantilla (`TEMPLATE_ID`,
`FORM_FIELDS`, `build_qso()`...). Los pull request con plantillas nuevas son
bienvenidos — mismas condiciones del CLA que el resto del proyecto.
