# Detección de construcciones — resumen de lo implementado

Este documento resume, de forma funcional, todo lo que se construyó para la
integración del pipeline de detección de cambios (GPU) con el ERP: qué guarda
la base de datos, qué endpoints existen, y qué puede hacer un arquitecto desde
el frontend. Está pensado como contexto rápido para cualquiera que retome este
módulo — no es una referencia línea por línea del código.

## 1. Qué hace el módulo

El dominio `detection` (`app/domains/detection/`) conecta el motor GPU externo
(`10.0.0.30:8100`, ver `DETECTION_ENGINE_URL`) con la base de datos
`detection_results` (esquema completo en `doc/bdd.sql`). El ERP actúa como
BFF: dispara el job en el motor, sondea su progreso, y cuando termina persiste
el resultado en Postgres/PostGIS siguiendo arquitectura hexagonal (dominio /
aplicación / infraestructura / presentación, ver `CLAUDE.md`).

## 2. Persistencia del pipeline

Cuando un job de detección termina, `IngestDetectionResultUseCase` guarda de
forma **idempotente** (se puede sondear el mismo resultado varias veces sin
duplicar datos):

- **`processed_sector`**: el área procesada, con su polígono, años comparados
  (A→B), estado (`awaiting_validation`, `awaiting_manual_alignment`,
  `completed`, etc.) y contadores (`n_affected_parcels`, `n_new_parcels`,
  `n_removed_parcels`, `n_changed_parcels`).
- **`alignment`** / **`control_point`**: cada alineación entre ortofotos
  (automática `auto_ecc` o manual `manual_gcp` con puntos de control), con su
  calidad (`cc`, `residual_m`, `quality_level`). Cuando hay más de una
  alineación para el mismo sector, `is_accepted` marca cuál es la "mejor"
  (menor `residual_m`) — es solo contabilidad, no afecta qué corrida se
  muestra en el UI (eso siempre es la más reciente).
- **`processing_run`**: cada corrida de detección sobre un sector (la primera
  automática, y una nueva por cada realineación manual que el arquitecto
  aplique). Una realineación manual **no sobreescribe** la corrida anterior:
  crea una corrida nueva y sus propios `detection`/`affected_parcel`, así que
  el historial completo queda disponible.
- **`detection`**: cada cambio detectado por el modelo (polígono en WGS84,
  probabilidad, área en m², tipo new/removed/modified).
- **`affected_parcel`**: el predio afectado por cada detección, con su
  `codigo_catastral`, el **polígono catastral real del predio**
  (`parcel_geom`, MULTIPOLYGON WGS84 — no el bbox del cambio) cuando hubo
  cruce catastral, y su estado de validación.
- **`sector_artifact`**: rutas a las imágenes/artefactos que devuelve el
  motor para ese sector (reescritas a `/api/detection/engine/...` para
  servirlas a través del ERP).
- **`campaign`**: agrupador opcional de sectores (código, nombre, período),
  con contadores denormalizados `n_sectors`/`n_affected_parcels` que se
  recalculan cuando cambian sus sectores.
- **`processing_history`**: bitácora de etapas del pipeline por sector.

`shadow_removal` existe en el esquema pero **nunca se llena** — el motor no
entrega esa información hoy.

## 3. Validación del arquitecto (`architect_review`)

Flujo final, **sin retroalimentación al modelo** (ver sección 4): el
arquitecto solo tiene dos acciones sobre cada `affected_parcel` pendiente,
expuestas como dos íconos en cada fila de la tabla de hallazgos:

- **Confirmar** (✓ verde): valida que el cambio es real y **clasifica qué
  tipo de construcción es**, eligiendo de un catálogo fijo
  (`ReviewAffectedParcelUseCase.ALLOWED_CONSTRUCTION_TYPES`):
  `nueva_construccion`, `ampliacion`, `cambio_techo`, `muro_nuevo`,
  `demolicion`, `otro`. Se guarda en `affected_parcel.construction_type`.
- **Rechazar** (✗ rojo): marca el predio como sin cambio real, con un
  comentario **opcional** que solo queda como registro de auditoría (por qué
  se rechazó esa detección) — no dispara ningún flujo adicional.

Cada acción queda registrada en `architect_review` (quién, cuándo, acción,
comentario). Cuando ya no quedan predios `pending` en la corrida más reciente
de un sector, `processed_sector.status` pasa automáticamente a `completed`
(ver `_maybe_complete_sector` en `SqlAffectedParcelReviewRepository`).

Endpoint: `POST /api/detection/affected-parcels/{id}/review`
(`{action: "confirm"|"reject", construction_type?, comment?}`).

## 4. Retroalimentación al modelo — descartada

Originalmente existía un tercer flujo ("enviar para retroalimentación": subía
recortes/chips de las ortofotos A/B al dataset de reentrenamiento). **Se
eliminó por completo** porque la alineación entre ortofotos no es lo
suficientemente confiable como para recortar chips útiles. Se borró todo el
código asociado (entidad `ModelFeedback`, puerto `ChipGeneratorPort`, caso de
uso, adaptador, endpoints de envío y de servido de chips, y la configuración
`DETECTION_CHIPS_DIR`). La tabla `model_feedback` sigue existiendo en el DDL
(`doc/bdd.sql`) por compatibilidad, pero nada en este backend escribe en ella.

## 5. Historial ("Historial" en el frontend)

Pestaña de solo lectura (`GET /api/detection/sectors`,
`GET /api/detection/sectors/{id}`) para navegar todo lo ya procesado, con dos
vistas:

- **Mapa**: cada sector procesado se dibuja como un polígono cuyo color
  refleja el resultado de validación de su corrida más reciente (no su
  estado de pipeline):
  - 🟢 verde: todo lo encontrado fue confirmado.
  - 🔴 rojo: todo lo encontrado fue rechazado (el modelo se equivocó ahí).
  - 🟠 naranja: mezcla de confirmados y rechazados.
  - ⚪ gris: todavía sin revisar (o en proceso/error).

  Cuando varios sectores se superponen en el mapa, un clic no depende de cuál
  capa esté "encima": se hace una prueba propia de punto-en-polígono contra
  todos los sectores renderizados (`processedSectorsLayer.js`) y, si hay más
  de uno, se muestra un selector para elegir cuál ver.

- **Tabla**: listado navegable de sectores con quién los procesó, cuándo, y
  cuántos cambios tuvo.

Ningún botón de "Reprocesar" aparece aquí a propósito — esa acción solo existe
en "Mapa y detección" (el detalle de un sector, `ProcessedSectorDetailModal`,
se comparte entre ambas pestañas vía la prop `allowReprocess`).

### Ver un predio validado en el mapa

Desde el detalle de un sector, cualquier predio ya validado que tenga
polígono catastral (`parcel_geom_geojson`) es clickeable: cierra el modal,
dibuja ese polígono en el mapa (capa dedicada, `parcelHighlightLayer.js`) y
hace zoom/centra la vista sobre él.

## 6. Frontend — resumen de pantallas

- `DetectionPage` ("Mapa y detección"): dibuja el área, dispara la detección,
  muestra resultados con selector/creador de campaña, y valida cada hallazgo
  desde la propia tabla (`ParcelValidationButtons` → `ParcelValidationModal`).
- `HistorialPage`: la pestaña de solo lectura descrita arriba.
- `ProcessedSectorDetailModal`: detalle compartido de un sector (corridas,
  alineaciones, predios, quién validó cada uno, y ahora el predio clickeable
  para resaltarlo en el mapa).
- `ParcelValidationModal`: único modal de validación, con dos modos
  (`confirm`/`reject`) según qué ícono se presionó.

## 7. Otras correcciones relevantes hechas en el camino

- Bug real: el WKT de polígonos generado le faltaba el paréntesis exterior
  (`POLYGON(...)` vs `POLYGON...`) — corregido y verificado contra datos
  reales.
- Bug real: la alineación automática se etiquetaba mal como `manual_gcp` en
  algunos casos — ahora se determina por el flujo de código que la crea, no
  por texto libre del motor.
- Bug real: tras una realineación manual nunca se creaba una segunda corrida
  (`processing_run`) — el sector simplemente no re-ingería nada. Corregido
  con detección de "alineación manual pendiente de ingesta".
- Los modales de la app usaban `z-50`, por debajo de los paneles de Leaflet
  (`z-index` hasta 1000+) — se subió a `z-[2000]` en el componente `Modal`
  compartido, corrigiendo todos los modales de la aplicación, no solo los de
  detección.

## 8. Limpieza de datos (2026-09-28)

Se depuró `detection_results` para dejar solo los últimos 4 sectores
**completados** como datos de referencia (ids 22, 24, 25 y 28) y se
eliminaron los 16 sectores restantes (incluyendo los que estaban pendientes
de validación), con cascada a todas sus tablas hijas
(`alignment`/`control_point`/`processing_run`/`detection`/`affected_parcel`/
`sector_artifact`/`architect_review`/`processing_history`). Los contadores
denormalizados de `campaign` (`n_sectors`, `n_affected_parcels`) se
recalcularon a partir de lo que quedó.
