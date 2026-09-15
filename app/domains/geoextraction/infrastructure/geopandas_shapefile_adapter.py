"""
Infrastructure adapter implementing ShapefilePort with GeoPandas/Shapely.
This is the only layer in this domain that knows those libraries — domain/ and
application/ do not import them, so the day this domain is extracted as a
separate service, only this file changes (see CLAUDE.md §3).

Logic moved from geo-extract/backend/main.py (export_shapefile/merge_shapefiles),
same projection and same generated attributes.
"""
import io
import os
import tempfile
import zipfile
from datetime import datetime

import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon

from app.domains.geoextraction.domain.entities.parcel import Parcel
from app.domains.geoextraction.domain.exceptions import UnreadableShapefileException
from app.domains.geoextraction.domain.ports.shapefile_port import ShapefilePort

COCHABAMBA_PROJECTION = "EPSG:32719"


def _pack_zip(gdf: "gpd.GeoDataFrame", base_name: str) -> bytes:
    zip_buffer = io.BytesIO()
    with tempfile.TemporaryDirectory() as tmpdir:
        shp_path = os.path.join(tmpdir, f"{base_name}.shp")
        gdf.to_file(shp_path, driver="ESRI Shapefile", encoding="utf-8")

        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            for root, _, files in os.walk(tmpdir):
                for file_name in files:
                    zip_file.write(os.path.join(root, file_name), arcname=file_name)

    zip_buffer.seek(0)
    return zip_buffer.getvalue()


class GeoPandasShapefileAdapter(ShapefilePort):
    def generate(self, parcels: list[Parcel]) -> bytes:
        is_individual = len(parcels) == 1
        base_name = "terreno_individual" if is_individual else "capa_masiva"

        polygons = []
        attributes_rows = []
        for index, parcel in enumerate(parcels):
            polygons.append(Polygon([(p.x, p.y) for p in parcel.points]))

            attrs = dict(parcel.attributes)
            attrs["Origen"] = "GeoExtraccion"
            attrs["Fecha"] = datetime.now().strftime("%Y-%m-%d")
            if not is_individual:
                attrs["ID_Ter"] = index + 1
            attributes_rows.append(attrs)

        gdf = gpd.GeoDataFrame(attributes_rows, geometry=polygons, crs=COCHABAMBA_PROJECTION)
        return _pack_zip(gdf, base_name)

    def merge(self, files: list[bytes]) -> bytes:
        layers = []
        for content in files:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            try:
                layers.append(gpd.read_file(f"zip://{tmp_path}"))
            except Exception as exc:
                raise UnreadableShapefileException(f"No se pudo leer un Shapefile del ZIP: {exc}") from exc
            finally:
                os.unlink(tmp_path)

        if not layers:
            raise UnreadableShapefileException("Ninguno de los archivos subidos contenía un Shapefile válido.")

        merged = pd.concat(layers, ignore_index=True)
        if merged.crs is None:
            merged = merged.set_crs(COCHABAMBA_PROJECTION)
        else:
            merged = merged.to_crs(COCHABAMBA_PROJECTION)

        return _pack_zip(merged, "shapefile_unido")
