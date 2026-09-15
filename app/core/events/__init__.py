"""
In-process event bus to communicate domains without coupling them directly.
Pending implementation — see ARQUITECTURA.md §8 and CLAUDE.md §7.
Use when one domain needs to notify another without waiting for a response
(e.g. Cadastre emits `PredioCreado`, Documentation subscribes without Cadastre knowing).
"""
