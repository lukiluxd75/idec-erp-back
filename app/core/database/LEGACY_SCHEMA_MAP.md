# Schema map — `idec_erp` (English physical names)

Physical PostgreSQL names were migrated to English via:

`scripts/migrate_schema_to_english.py` (executed against `172.16.66.103` / `idec_erp`).

ORM attributes and `__tablename__` / column names now match the live database.

## Public RBAC

| Table | Notes |
|-------|--------|
| `systems` | was `sistema` |
| `subsystems` | was `subsistema` |
| `resources` | was `recurso` |
| `permissions` | was `permiso` (`action` was `accion`) |
| `internal_roles` | was `rol_interno` |
| `role_permissions` | was `rol_permiso` |
| `users` | was `usuario` (`email` was `correo`) — not `user` (SQL reserved) |
| `areas` | was `area` (`area_type` was `tipo`) |
| `user_role_areas` | was `usuario_rol_area` |
| `access_audits` | was `auditoria_acceso` |
| `geoocr_audits` | was `auditoria_geoocr` |

Timestamps: `created_at` / `updated_at` (was `fecha_creacion` / `fecha_actualizacion`).
Flags: `is_active` (was `activo`).

## GIS module

| Schema | Was |
|--------|-----|
| `detection` | `deteccion` |
| `detection_cfg` | `deteccion_cfg` (may be absent if never seeded) |

Key tables: `campaigns`, `work_areas`, `jobs`, `job_artifacts`, `manual_alignments`,
`parcel_analyses`, `change_detections`, `validation_events`, `parcel_change_layers`,
`change_geometries`.

Views: `pub.v_parcel_changes`, `pub.v_change_geometries`, `pub.v_processed_areas`.

## Permission codes

`ver`/`editar` → `view`/`edit`; module ids → `detection`, `security`, `geoextraction`, `resolutions`.

## Already English (unchanged)

- Schema `resolutions` / `resolution_pages`
- GPU engine paths (out of scope)

## Re-run

Script is idempotent. Safe to re-run after restore from Spanish backup.
