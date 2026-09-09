"""
Bus de eventos in-process para comunicar dominios sin acoplarlos directamente.
Pendiente de implementación — ver ARQUITECTURA.md §8 y CLAUDE.md §7.
Úsalo cuando un dominio necesite notificar algo a otro sin esperar una respuesta
(ej. Catastro emite `PredioCreado`, Documentación se suscribe sin que Catastro lo sepa).
"""
