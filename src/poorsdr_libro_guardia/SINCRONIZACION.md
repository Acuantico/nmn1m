# Sincronización de NMN1M

NMN1M sincroniza los libros General HAM, 11 m y las plantillas de concurso entre varios PC y dispositivos Android dentro de la misma red local.

## Configurar el equipo servidor

1. Abra **Ajustes > Sincronización** en el libro de escritorio que conservará el servidor.
2. Mantenga **Escuchar en** como `0.0.0.0`, elija un puerto (por defecto `8080`) y escriba una clave compartida.
3. Active **Servidor de sincronización** y pulse **Aplicar**.
4. Anote una de las IP locales que muestra la pantalla.

Si el sistema operativo pregunta por el cortafuegos, permita el puerto sólo en redes privadas. El servidor está pensado para una LAN doméstica; no se recomienda publicar el puerto en Internet.

## Configurar otro PC

En **Ajustes > Sincronización**, escriba la IP del servidor, el puerto y la misma clave. Pulse **Sincronizar ahora**. Un PC puede ser cliente aunque su propio servidor esté desactivado.

## Configurar Android

En **Ajustes**, escriba la IP/nombre del PC servidor, el puerto y la clave compartida. Guarde los ajustes, abra **Sincronizar** y pulse **Sincronizar ahora**. Android debe estar conectado a la misma red Wi‑Fi que el PC.

## Comportamiento

- Cada QSO tiene un UUID estable y no se duplica al repetir una sincronización.
- Las altas, modificaciones y eliminaciones se intercambian en ambos sentidos.
- Si el mismo QSO cambia en dos dispositivos, se conserva la revisión más reciente.
- General y 11 m permanecen separados.
- En cada plantilla se sincroniza la base de datos que esté seleccionada en ese momento.
- Una plantilla de concurso sólo se sincroniza si está instalada con el mismo identificador en el dispositivo receptor.
- La sincronización no sustituye las copias de seguridad ADIF/CSV.

Si cambia la IP del servidor, actualícela en todos los clientes. Si falla la conexión, compruebe que el servidor figure como activo, que IP, puerto y clave coincidan y que el cortafuegos permita el puerto elegido.
