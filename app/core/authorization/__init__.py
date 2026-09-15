"""
Internal permission resolution (RBAC/ABAC) for the ERP, shared across all domains.
Pending implementation — see ARQUITECTURA.md §6 and CLAUDE.md §5.
Do not confuse with `domains/security`, which owns the role/permission DATA;
this package is where the `require_permission(...)` dependency will live so any
domain can use it to protect its own endpoints.
"""
