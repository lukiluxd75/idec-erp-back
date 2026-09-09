"""
Adaptador de infraestructura que implementa ShapefilePort con GeoPandas/Shapely.
Es la única capa de este dominio que conoce estas librerías — domain/ y application/ no
las importan, así que el día que este dominio se extraiga a servicio aparte, solo cambia
este archivo (ver CLAUDE.md §3).

Lógica trasladada de geo-extract/backend/main.py (export_shapefile/merge_shapefiles),
misma proyección y mismos atributos generados.
"""
import io
import os
import tempfile
import zipfile
from datetime import datetime

import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon

from app.domains.geoextraccion.domain.entities.terreno import Terreno
from app.domains.geoextraccion.domain.exceptions import ShapefileIlegibleException
from app.domains.geoextraccion.domain.ports.shapefile_port import ShapefilePort

PROYECCION_COCHABAMBA = "EPSG:32719"


def _empaquetar_zip(gdf: "gpd.GeoDataFrame", nombre_base: str) -> bytes:
    zip_buffer = io.BytesIO()
    with tempfile.TemporaryDirectory() as tmpdir:
        shp_path = os.path.join(tmpdir, f"{nombre_base}.shp")
        gdf.to_file(shp_path, driver="ESRI Shapefile", encoding="utf-8")

        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            for root, _, files in os.walk(tmpdir):
                for nombre_archivo in files:
                    zip_file.write(os.path.join(root, nombre_archivo), arcname=nombre_archivo)

    zip_buffer.seek(0)
    return zip_buffer.getvalue()


class GeoPandasShapefileAdapter(ShapefilePort):
    def generar(self, terrenos: list[Terreno]) -> bytes:
        es_individual = len(terrenos) == 1
        nombre_base = "terreno_individual" if es_individual else "capa_masiva"

        poligonos = []
        atributos = []
        for indice, terreno in enumerate(terrenos):
            poligonos.append(Polygon([(p.x, p.y) for p in terreno.puntos]))

            attrs = dict(terreno.atributos)
            attrs["Origen"] = "GeoExtraccion"
            attrs["Fecha"] = datetime.now().strftime("%Y-%m-%d")
            if not es_individual:
                attrs["ID_Ter"] = indice + 1
            atributos.append(attrs)

        gdf = gpd.GeoDataFrame(atributos, geometry=poligonos, crs=PROYECCION_COCHABAMBA)
        return _empaquetar_zip(gdf, nombre_base)

    def fusionar(self, archivos: list[bytes]) -> bytes:
        capas = []
        for contenido in archivos:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
                tmp.write(contenido)
                tmp_path = tmp.name
            try:
                capas.append(gpd.read_file(f"zip://{tmp_path}"))
            except Exception as exc:
                raise ShapefileIlegibleException(f"No se pudo leer un Shapefile del ZIP: {exc}") from exc
            finally:
                os.unlink(tmp_path)

        if not capas:
            raise ShapefileIlegibleException("Ninguno de los archivos subidos contenía un Shapefile válido.")

        capa_unida = pd.concat(capas, ignore_index=True)
        if capa_unida.crs is None:
            capa_unida = capa_unida.set_crs(PROYECCION_COCHABAMBA)
        else:
            capa_unida = capa_unida.to_crs(PROYECCION_COCHABAMBA)

        return _empaquetar_zip(capa_unida, "shapefile_unido")
