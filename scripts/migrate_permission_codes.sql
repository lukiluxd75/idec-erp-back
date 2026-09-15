-- Migrate RBAC permission / resource codes from Spanish to English.
-- Run against idec_erp AFTER deploying ERP back+front that expect English codes.
-- Review and backup before executing in production.

BEGIN;

-- Module id prefixes on permission codes (recurso.accion style strings stored in app).
-- Adjust column names if your seed stores codes differently (permiso vs recurso.nombre).

-- Example pattern when codes live as 'modulo.accion' text columns:
UPDATE public.permiso
SET accion = CASE accion
  WHEN 'ver' THEN 'view'
  WHEN 'editar' THEN 'edit'
  ELSE accion
END
WHERE accion IN ('ver', 'editar');

-- Resource / module names used to build 'modulo.accion'
UPDATE public.recurso
SET nombre = CASE nombre
  WHEN 'deteccion' THEN 'detection'
  WHEN 'seguridad' THEN 'security'
  WHEN 'geoextraccion' THEN 'geoextraction'
  WHEN 'resoluciones' THEN 'resolutions'
  ELSE nombre
END
WHERE nombre IN ('deteccion', 'seguridad', 'geoextraccion', 'resoluciones');

-- If codes are stored denormalized as full strings elsewhere, add UPDATEs here, e.g.:
-- UPDATE ... SET codigo = replace(codigo, 'deteccion.ver', 'detection.view');

COMMIT;

-- Rollback reference (do not run unless reverting a bad deploy):
-- BEGIN;
-- UPDATE public.permiso SET accion = CASE accion WHEN 'view' THEN 'ver' WHEN 'edit' THEN 'editar' ELSE accion END;
-- UPDATE public.recurso SET nombre = CASE nombre
--   WHEN 'detection' THEN 'deteccion' WHEN 'security' THEN 'seguridad'
--   WHEN 'geoextraction' THEN 'geoextraccion' WHEN 'resolutions' THEN 'resoluciones'
--   ELSE nombre END;
-- COMMIT;
