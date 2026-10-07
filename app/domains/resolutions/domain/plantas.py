"""Lista fija de nombres de planta, idéntica a
frontend/src/domains/resolutions/utils/plantasCatalog.js (PLANTAS_RESUMEN) —
son los mismos nombres (33 de la plantilla + TERRAZA, que algunos planos traen) que `RESUMEN!B12:B44` busca por VLOOKUP en el
Excel final. Se valida acá tambien para no guardar en la base un valor que
después no calce con ninguna fila de RESUMEN."""

PLANTAS_RESUMEN = (
    "PLANTA SOTANO",
    "PLANTA SEMISOTANO",
    "PLANTA BAJA",
    *[f"PLANTA {i}º PISO" for i in range(1, 31)],
    "PLANTA TERRAZA",
)
