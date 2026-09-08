# Nunca Más, Ni Una Más (NMN1M)

Cuaderno de estación / contest logger para radioafición y CB: registro de
QSO, cascada de bandas, mapa de contactos, sincronización LAN entre varios
equipos y funciones de concurso mediante plantillas instalables.

Funciona **solo** o **integrado con [PoorSDR4All](https://acuanticopower.com/poorsdr4all)**
(añade un botón «Log» a su consola). Es el mismo programa en ambos casos.

## Instalación

### Independiente

```bash
python -m pip install .
poorsdr-libro-guardia
```

Sin más dependencias que las de este mismo paquete — no hace falta tener
PoorSDR4All instalado.

### Integrado con PoorSDR4All

Instala este repositorio en el mismo entorno donde tengas PoorSDR4All:

```bash
python -m pip install /ruta/a/este/repositorio
```

Al arrancar `python -m poorsdr`, la consola descubre el plugin (entry point
`poorsdr.plugins`) y añade el botón «Log». Corriendo integrado, NMN1M también
recoge el tema visual de la consola automáticamente.

## Plantillas de concurso

`General` (HAM) y `11m` (CB) son los dos libros principales y van siempre
instalados. Las plantillas de **concurso** (CQ-WPX, IARU HF, SM...) se
distribuyen sueltas en [`contest-templates/`](contest-templates/): descarga
solo la que necesites e instálala desde **Concursos → Importar plantilla...**
dentro de la propia aplicación.

## Datos del usuario

Ajustes, registros y copias de seguridad se guardan en los directorios de
datos del sistema (`~/.config/poorsdr/libro-guardia`,
`~/.local/share/poorsdr/libro-guardia` en Linux; equivalentes en Windows/macOS)
— nunca dentro del paquete instalado, y nunca se incluyen en este repositorio.

## Sincronización

Ver [`src/poorsdr_libro_guardia/SINCRONIZACION.md`](src/poorsdr_libro_guardia/SINCRONIZACION.md)
para sincronizar los libros entre varios PC y Android en una misma red local.

## Licencias

El código propio se distribuye bajo PolyForm Noncommercial 1.0.0 — ver
`LICENSE`. Hay una licencia comercial separada disponible (`COMMERCIAL-LICENSE.md`).
El paquete también contiene datos de GeoNames (CC BY 4.0) y recursos de
flag-icons (MIT); consulta `LICENSES/` y `DATA_PROVENANCE.md` para las
condiciones y atribuciones completas.

Contribuciones: ver `CONTRIBUTING.md` y `CLA.md`.
