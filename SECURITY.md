# Seguridad

## Comunicar una vulnerabilidad

No publiques inicialmente detalles explotables en una incidencia pública.
Envía el informe mediante el canal privado **Security advisories** del
repositorio de GitHub. Incluye versión afectada, plataforma, impacto y pasos
mínimos para reproducirlo.

Si el repositorio aún no dispone de avisos privados, utiliza el formulario
https://acuanticopower.com/contacto/ indicando "NMN1M security".

Se acusará recibo tan pronto como sea posible. No se promete un plazo fijo para
una Alpha, pero se publicará una corrección y un aviso coordinados cuando el
problema esté confirmado.

## Alcance de soporte

Solo la versión más reciente recibe correcciones.

El servidor de sincronización LAN (ver
[`src/poorsdr_libro_guardia/SINCRONIZACION.md`](src/poorsdr_libro_guardia/SINCRONIZACION.md))
está pensado para una red doméstica de confianza — no lo expongas directamente
a Internet.

Las plantillas de concurso (propias o de `contest-templates/`) son código
Python que se ejecuta dentro de la aplicación: instala solo las que procedan
de una fuente de confianza.
