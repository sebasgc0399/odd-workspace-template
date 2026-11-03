---
name: capa-{{capa}}
description: "Reglas, convenciones y moldes de la capa {{capa}} de esta instancia. La precargan writer-{{capa}} y revisor-{{capa}}; la edita el usuario."
user-invocable: false
---
CENTINELA capa-{{capa}} {{fecha}}

# Capa {{capa}}

Reglas de la capa `{{capa}}`. Es contenido de la instancia: se edita libremente y odd-ws no la regenera.
Los criterios que valen para todas las capas están en `criterios`; acá solo va lo propio de esta capa.

<!-- no-negociables -->
Aquí van las reglas no negociables de la capa {{capa}}, una por línea: lo que un cambio nunca puede
romper. Este bloque se le recuerda al agente la primera vez que toca un archivo de la capa. Mientras
esté así, la capa no tiene reglas.
<!-- /no-negociables -->

## Convenciones

Debajo del bloque, lo que un writer y un revisor de la capa necesitan leer completo:

- cómo se nombran y se organizan los archivos;
- cómo se manejan los errores, la configuración y los datos;
- qué se prueba y cómo se corre.

## Moldes

Un archivo vigente de la capa que sirve de modelo para lo nuevo, con su ruta, y qué se calca de él y qué
no. Si no hay molde, se anota aquí.
