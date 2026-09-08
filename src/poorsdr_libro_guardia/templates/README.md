# Plantillas de log

Los archivos de esta carpeta son plantillas Python ejecutables. `general.py`
(HAM) y `m11.py` (11 m, `TEMPLATE_ID = "11m"`) son los dos libros principales:
van siempre instalados y no se pueden sustituir por una importación.

Las plantillas de **concurso** (CQ-WPX, IARU HF, SM...) no viven aquí — se
distribuyen sueltas en [`../contest-templates/`](../contest-templates/) para
que cada usuario descargue e instale solo las que necesite, sin cargar la
instalación principal con concursos que no vaya a usar. Se instalan igual
desde **Concursos > Importar plantilla...**.

Toda plantilla importable debe declarar:

```python
TEMPLATE_ID = "identificador_unico"
TEMPLATE_NAME = "Nombre visible"
LOG_KIND = "ham"  # o "11m"
IS_CONTEST = True
```

También debe incluir las listas `FORM_FIELDS` y `TREE_COLUMNS`, y las funciones `build_qso()`, `row_values()` y `adif_fields()`. `LOG_KIND` determina qué sistema se usa para identificar el país: prefijos DXCC en HAM o divisiones en 11 m.

Los identificadores `general` y `11m` están reservados para los dos libros principales y no pueden ser reemplazados mediante una importación.

Importa únicamente plantillas procedentes de una fuente de confianza, ya que su código se ejecuta dentro de la aplicación.
