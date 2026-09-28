# Procedure types available to the cartography unit in all districts.
DEFAULT_PROCEDURE_TYPES = (2009, 2010, 2012, 3002, 3003, 3004, 3005, 3006)

PROCEDURE_TYPE_METADATA = {
    2009: {"label": "Certificación técnica Ley 247", "group": "Certificaciones", "shortLabel": "Ley 247"},
    2010: {"label": "Certificación para usucapión", "group": "Certificaciones", "shortLabel": "Usucapión"},
    2012: {"label": "Certificación de datos técnicos", "group": "Certificaciones", "shortLabel": "Datos técnicos"},
    3002: {"label": "Registro catastral nuevo", "group": "Registros catastrales", "shortLabel": "RC nuevo"},
    3003: {"label": "Registro catastral de división y partición", "group": "Registros catastrales", "shortLabel": "División"},
    3004: {"label": "Registro catastral de anexión", "group": "Registros catastrales", "shortLabel": "Anexión"},
    3005: {"label": "Registro catastral de actualización", "group": "Registros catastrales", "shortLabel": "Actualización"},
    3006: {"label": "Registro catastral por cambio de titular", "group": "Registros catastrales", "shortLabel": "Cambio de titular"},
}

PROCEDURE_TYPE_PALETTE = (
    "#341A67",
    "#009ED0",
    "#7C3AED",
    "#0E7490",
    "#584291",
    "#0284C7",
    "#6D28D9",
    "#155E75",
)

PALETTE = (
    "#341A67",
    "#009ED0",
    "#584291",
    "#0E7490",
    "#7C3AED",
    "#0284C7",
    "#6D28D9",
    "#155E75",
    "#4C1D95",
    "#0891B2",
    "#5B21B6",
    "#0369A1",
    "#8B5CF6",
    "#22D3EE",
    "#312E81",
    "#67E8F9",
    "#A78BFA",
    "#164E63",
    "#C4B5FD",
    "#38BDF8",
)


def color_at(index: int) -> str:
    return PALETTE[index % len(PALETTE)]


def procedure_type_label(procedure_type_id: int, raw_label: str = "") -> str:
    meta = PROCEDURE_TYPE_METADATA.get(int(procedure_type_id))
    if meta:
        return meta["label"]
    message = " ".join((raw_label or "").replace("_", " ").split())
    return message[:1].upper() + message[1:].lower() if message else "Otro trámite"


def procedure_type_group(procedure_type_id: int) -> str:
    meta = PROCEDURE_TYPE_METADATA.get(int(procedure_type_id))
    return meta["group"] if meta else "Otros"


def procedure_type_color(procedure_type_id: int) -> str:
    try:
        return PROCEDURE_TYPE_PALETTE[DEFAULT_PROCEDURE_TYPES.index(int(procedure_type_id))]
    except ValueError:
        return color_at(int(procedure_type_id))
