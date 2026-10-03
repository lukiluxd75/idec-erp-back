-- Permiso "folder-analysis.admin" del RBAC interno de IDEC.
--
-- Qué habilita: buscar en "Carpetas registradas" por nombre de carpeta entre las
-- carpetas de TODOS los usuarios, y no solo entre las propias. Una carpeta
-- física la escanea quien la tiene en la mano, así que hasta ahora el resto no
-- tenía forma de volver a encontrarla; con este permiso, quien administra el
-- módulo la encuentra escribiendo su número.
--
-- Qué NO habilita: ver las carpetas ajenas en la lista (solo aparecen cuando se
-- las busca por nombre), ni editarlas, ni borrarlas, ni sacarles documentos.
-- Todo lo que escribe sigue exigiendo ser el dueño de la carpeta.
--
-- Ejecutar en PostgreSQL contra el esquema del RBAC (tablas resources y
-- permissions). Es idempotente: si el permiso ya está, no hace nada. Después
-- hay que asignarlo a un rol desde Seguridad -> Roles, como cualquier otro.

INSERT INTO permissions (resource_id, action, description)
SELECT r.id, 'admin', 'Buscar carpetas registradas de otros usuarios por nombre'
FROM resources r
WHERE r.name = 'folder-analysis'
  AND NOT EXISTS (
      SELECT 1
      FROM permissions p
      WHERE p.resource_id = r.id
        AND p.action = 'admin'
  );

-- Comprobación: tiene que devolver una fila por cada acción del módulo
-- (view, edit y ahora admin).
-- SELECT r.name || '.' || p.action AS codigo, p.description
-- FROM permissions p
-- JOIN resources r ON r.id = p.resource_id
-- WHERE r.name = 'folder-analysis'
-- ORDER BY p.action;
