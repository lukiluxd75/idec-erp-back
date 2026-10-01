"""`security` domain: authentication (Keycloak), the institutional directory
(Zentyal/LDAP) and the internal RBAC model that backs `require_permission`.

This file was missing while every sibling domain had one. Imports worked anyway
via implicit namespace packages, so the gap was invisible -- except to test
discovery, which skipped `tests/test_keycloak_adapter.py` and
`tests/test_use_cases.py` (13 tests) and still reported OK.
"""
