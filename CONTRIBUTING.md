# Contribuir a NMN1M (Nunca Más, Ni Una Más)

Gracias por contribuir. NMN1M acepta informes de errores y propuestas sin
formalidades, pero toda aportación de código, documentación, plantillas de
concurso o recursos destinada a incorporarse al proyecto requiere aceptar
previamente el acuerdo `CLA.md`.

## Plantillas de concurso

Las plantillas de concurso (`contest-templates/`) son la forma más sencilla de
contribuir sin tocar el núcleo de la aplicación: un solo archivo Python
autocontenido. Ver
[`src/poorsdr_libro_guardia/templates/README.md`](src/poorsdr_libro_guardia/templates/README.md)
para el contrato que debe cumplir (`TEMPLATE_ID`, `FORM_FIELDS`, `build_qso()`...).

## Proceso

1. Abra una incidencia describiendo los cambios grandes antes de implementarlos.
2. Mantenga cada contribución enfocada y acompañada de pruebas cuando proceda.
3. Confirme en el pull request que ha leído y acepta la versión vigente de
   `CLA.md`. El mantenedor debe conservar un registro verificable de la
   aceptación antes de fusionar la aportación.
4. Declare expresamente cualquier código, dato o recurso de terceros y facilite
   su origen, versión y licencia.
5. No incluya claves, certificados privados, credenciales, logs, indicativos
   propios ni datos de usuarios reales.

Las aportaciones realizadas por cuenta de una empresa requieren autorización de
esa empresa. El mantenedor puede solicitar un acuerdo corporativo adicional.

## Licencias

El CLA permite a Acuantico Power incluir las contribuciones al código propio en
las ediciones no comercial y comercial. El colaborador conserva el copyright de
su aportación.

Las aportaciones que toquen datos de terceros (GeoNames, flag-icons...) deben
enviarse identificando su origen y mantener la licencia del componente
correspondiente. El CLA de NMN1M no relicencia código de terceros.
