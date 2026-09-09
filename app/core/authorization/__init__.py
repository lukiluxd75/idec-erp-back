"""
Resolución de permisos internos (RBAC/ABAC) del ERP, transversal a todos los dominios.
Pendiente de implementación — ver ARQUITECTURA.md §6 y CLAUDE.md §5.
No confundir con `domains/seguridad`, que es dueño de los DATOS de roles/permisos;
este paquete es donde vivirá la dependencia `require_permission(...)` que cualquier
dominio usa para proteger sus propios endpoints.
"""
