---
name: criterios
description: "Criterios transversales de esta instancia: el Paso 0 antes de escribir, el alcance mínimo, la evidencia ruta:línea y el contrato de reporte con severidades. Los precargan los writers y los revisores."
user-invocable: false
---
CENTINELA criterios {{fecha}}

# Criterios transversales

Valen para todas las capas. Las reglas propias de cada una están en su skill `capa-<capa>`. Es contenido
de la instancia: se edita libremente y odd-ws no la regenera.

## Paso 0: antes de escribir

Antes de la primera línea de una pieza nueva, anótalo en la carpeta del ticket:

- **El hermano vigente:** un archivo que hoy resuelve algo equivalente, con su ruta. Lo nuevo calca su
  forma; lo que difiere se justifica. Si no hay hermano, anota con qué lo buscaste.
- **El consumidor de cada dato nuevo:** dónde se lee o se usa. Un dato sin consumidor en este flujo no se
  agrega, aunque el hermano lo tenga.

## Alcance mínimo

El encargo es el encargo. Antes de editar algo compartido, cuenta sus consumidores (con Grep, citando el
comando y la salida): con uno solo hay libertad; con dos o más, el cambio va por configuración, no por
estructura, y los nombres no se cambian de paso. Si la solución correcta excede el encargo, se dice y se
hace lo pedido.

## Evidencia

Toda afirmación sobre el código cita `ruta:línea`. Un «no existe» o un «nadie lo usa» no vale hasta probar
que la búsqueda sabe encontrarlo.

## Contrato de reporte

Un hallazgo por línea: `[SEVERIDAD] ruta:línea — qué viola — cómo debe quedar`.

- **CRITICAL**: rompe un contrato, la seguridad o los datos.
- **WARNING**: viola una convención o un criterio con impacto real.
- **SUGGESTION**: mejora sin riesgo.

Cierra con **Alcance y límites**: qué se revisó y qué no se pudo verificar. Un límite declarado no es un
hallazgo.
