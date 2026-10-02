import logging
from typing import Any, Dict, List, Optional, Sequence

from app.domains.folder_analysis.domain.exceptions import (
    CadastralGisUnavailableException,
    CadastralLookupFailedException,
    FolderAnalysisException,
    CadastralParcelNotFoundException,
)
from app.domains.folder_analysis.domain.ports import CadastralGisPort
from app.domains.folder_analysis.infrastructure import croquis_composer
from app.domains.folder_analysis.domain.services import cadastral_code, plan_checks, plan_survey
from app.domains.folder_analysis.domain.services.parcel_geometry import (
    STREET_REACH_M,
    Ring,
    analyze_parcel,
    polygon_of,
)
from app.domains.folder_analysis.domain.services.utm import utm_to_wgs84

logger = logging.getLogger("uvicorn.error")

# How far from the predio to look for the ones next to it: the cadastre never
# lines two lots up to the centimetre.
NEIGHBOUR_REACH_M = 3.0
# A bit more than the street reach, so the street a side faces is never cut off
# by the query itself.
STREET_QUERY_M = STREET_REACH_M + 10.0
CROQUIS_LAYERS = ("usoSueloCertificado", "manzanasCertificado", "prediosCertificado1", "viasCertificado")


def _latlng(ring: Sequence[Sequence[float]]) -> List[List[float]]:
    return [list(utm_to_wgs84(p[0], p[1])) for p in ring]


class LookupCadastralParcelUseCase:
    """Places a predio on the map from its code catastral and reads, from the GIS
    geometry, what a poseedores sheet asks of the IDE: who is on each side of it,
    which streets it faces and its surface.

    When the text of the plano is given, what the plano says about its own lot --
    the vertices of its UTM table and the surface it declares -- comes back next to
    the GIS numbers, so the architect sees where the two disagree (the usual case
    of a regularization plano) instead of finding out later.
    """

    def __init__(self, gis: CadastralGisPort):
        self._gis = gis

    def execute(self, code: str, plan_text: Optional[str] = None) -> Dict[str, Any]:
        try:
            return self._lookup(code, plan_text)
        except FolderAnalysisException:
            raise
        except Exception as exc:  # noqa: BLE001 -- see CadastralLookupFailedException
            logger.exception("Folder analysis: falló la búsqueda del predio %s", code)
            raise CadastralLookupFailedException(
                f"Error inesperado al buscar el predio en el IDE ({exc.__class__.__name__}). "
                "Intente de nuevo o avise al administrador."
            ) from exc

    def _lookup(self, code: str, plan_text: Optional[str]) -> Dict[str, Any]:
        gis_code = cadastral_code.to_gis_code(code)
        parcel = self._gis.find_parcel(gis_code)
        if parcel is None:
            raise CadastralParcelNotFoundException(
                f"El código {cadastral_code.printed(gis_code)} no existe en el GIS catastral. "
                "Revise que el código esté bien leído."
            )
        neighbours = self._gis.parcels_around(parcel.ring, NEIGHBOUR_REACH_M)
        streets = self._gis.streets_around(parcel.ring, STREET_QUERY_M)
        analysis = analyze_parcel(parcel.ring, gis_code, neighbours, streets)
        attributes = parcel.attributes
        land_use, block = self._surroundings(parcel.ring)

        result: Dict[str, Any] = {
            "code": gis_code,
            "printed_code": cadastral_code.printed(gis_code),
            "property_number": str(attributes.get("Nro_predio") or "").strip(),
            "block": str(attributes.get("Nro_manzan") or "").strip(),
            "subdistrict_number": str(attributes.get("Sbdist_Nro") or "").strip(),
            "subdistrict": str(attributes.get("Sbdistrito") or "").strip(),
            "district": attributes.get("distrito"),
            "commune": str(attributes.get("comuna") or "").strip(),
            **analysis.as_dict(),
            "land_use": land_use,
            "block_info": block,
            "map": self._map(parcel.ring, gis_code, neighbours, streets, analysis),
            "plan": None,
        }
        if plan_text:
            result["plan"] = self._plan(plan_text, analysis.area_m2, result, streets)
        return result

    def _surroundings(self, ring: Ring):
        """Land use and manzana of the predio, read at a point that is surely inside
        it. They complete the answer but are not the answer: when the GIS cannot give
        them the lookup still stands."""
        inside = polygon_of(ring).representative_point()
        point = (inside.x, inside.y)
        try:
            use = self._gis.land_use_at(point)
        except CadastralGisUnavailableException:
            use = {}
        try:
            block = self._gis.block_at(point)
        except CadastralGisUnavailableException:
            block = {}
        restriction = use.get("Retriccion")
        return (
            {
                "use": str(use.get("Uso_Suelo") or "").strip() or None,
                "restriction": restriction,
                "district": use.get("Distritos"),
                "subdistrict": str(use.get("Sbdistrito") or "").strip() or None,
            }
            if use
            else None,
            {
                "number": str(block.get("Manzanas") or "").strip() or None,
                "area_m2": _rounded(block.get("Shape.STArea()")),
                "perimeter_m": _rounded(block.get("Shape.STLength()")),
                "subdistrict": str(block.get("Nombre_SD") or "").strip() or None,
                "commune": str(block.get("Comuna") or "").strip() or None,
            }
            if block
            else None,
        )

    @staticmethod
    def _map(ring: Ring, gis_code: str, neighbours, streets, analysis) -> Dict[str, Any]:
        """Everything the screen draws, already in latitude/longitude."""
        return {
            "parcel": _latlng(ring),
            "neighbours": [
                {"code": n.code, "number": n.number, "ring": _latlng(n.ring)}
                for n in neighbours
                if n.code != gis_code
            ],
            "streets": [
                {"name": s.label, "paths": [_latlng(path) for path in s.paths]} for s in streets
            ],
            "sides": [
                {
                    "index": side.index,
                    "point": side.point,
                    "abbreviation": side.abbreviation,
                    "kind": side.kind,
                    "name": side.name,
                    "length_m": round(side.length_m, 2),
                    "line": _latlng([side.start, side.end]),
                }
                for side in analysis.sides
            ],
        }

    @staticmethod
    def _plan(text: str, gis_area: float, gis: Dict[str, Any], streets: Sequence[Any] = ()) -> Dict[str, Any]:
        reading = plan_survey.read_plan(text)
        # The box under the croquis, line by line against what the GIS says.
        location = plan_checks.read_location_block(text)
        reading["location"] = location
        reading["checks"] = plan_checks.cross_check(
            location,
            {
                "zone": gis["subdistrict"],
                "district": gis["district"],
                "subdistrict": gis["subdistrict_number"],
                "block": gis["block"],
                "lot": gis["property_number"],
            },
        )
        survey = reading["survey"]
        reading["survey_vertices_latlng"] = (
            _latlng([[v["east"], v["north"]] for v in survey["vertices"]]) if survey else []
        )
        # What the architect compares: the surface of the plano (its vertices, and
        # what it prints) against the GIS one.
        area_plan = (survey or {}).get("area_m2") or reading["declared_area_m2"]
        # Frente and fondos from the vertices, once the GIS says which side is on the
        # street. Empty (with the reason) when the figures cannot be trusted.
        reading["measures"] = plan_survey.measures(
            survey, [path for street in streets for path in street.paths], reading["declared_area_m2"]
        )
        reading["area_difference_m2"] = round(area_plan - gis_area, 2) if area_plan is not None else None
        return reading


def _rounded(value: Any) -> Optional[float]:
    return round(float(value), 2) if isinstance(value, (int, float)) else None


# The croquis is a square this many pixels wide, showing this many times the
# predio, and never less than this half-width in metres around it (so the circle
# of 50 m around the predio is not cut off on a small lot).
CROQUIS_PIXELS = 600
CROQUIS_TIMES = 4.0
CROQUIS_MIN_HALF_M = 60.0


class GenerateCadastralCroquisUseCase:
    """The picture of the croquis de ubicación of a predio: the layers of the GIS
    stacked, the predio in grey, a red circle around it and its number."""

    def __init__(self, gis: CadastralGisPort):
        self._gis = gis

    def execute(self, code: str) -> bytes:
        try:
            return self._draw(code)
        except FolderAnalysisException:
            raise
        except Exception as exc:  # noqa: BLE001 -- see CadastralLookupFailedException
            logger.exception("Folder analysis: falló el croquis del predio %s", code)
            raise CadastralLookupFailedException(
                f"Error inesperado al generar el croquis ({exc.__class__.__name__})."
            ) from exc

    def _draw(self, code: str) -> bytes:
        gis_code = cadastral_code.to_gis_code(code)
        parcel = self._gis.find_parcel(gis_code)
        if parcel is None:
            raise CadastralParcelNotFoundException(
                f"El código {cadastral_code.printed(gis_code)} no existe en el GIS catastral."
            )
        xmin, ymin, xmax, ymax = polygon_of(parcel.ring).bounds
        half = max(max(xmax - xmin, ymax - ymin) * CROQUIS_TIMES / 2.0, CROQUIS_MIN_HALF_M)
        cx, cy = (xmin + xmax) / 2.0, (ymin + ymax) / 2.0
        bbox = (cx - half, cy - half, cx + half, cy + half)
        # The manzanas layer is the opaque one, as in the demo: it is the paper the
        # rest is printed on.
        layers = [
            self._gis.map_image(service, bbox, CROQUIS_PIXELS, transparent=service != "manzanasCertificado")
            for service in CROQUIS_LAYERS
        ]
        number = str(parcel.attributes.get("Nro_predio") or "").strip()
        return croquis_composer.compose(layers, bbox, CROQUIS_PIXELS, parcel.ring, number)
