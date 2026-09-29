"""Fits a 2D affine transform mapping a block's un-corrected control points
(lon_mov/lat_mov, as currently shown on the target year's WMS layer) onto
the fixed 2015 reference (lon_ref/lat_ref). Deliberately a RIGID/AFFINE fit
per block, not a global elastic warp -- see doc/alignment_schema.sql's header
for why: each manzana is corrected independently, with the seam against its
neighbor left uncovered on purpose, instead of one continuous transform that
could distort an area far from where the architect actually looked.

Pure math, no SQLAlchemy/FastAPI -- the domain layer's business rule for
"what a valid correction looks like" (see InvalidControlPoints)."""
import math
from typing import Sequence, Tuple

import numpy as np

from app.domains.alignment.domain.entities.alignment_block import ControlPointRecord
from app.domains.alignment.domain.exceptions import InvalidControlPoints

MIN_CONTROL_POINTS = 3


def fit_affine(points: Sequence[ControlPointRecord]) -> Tuple[dict, float]:
    """Returns (transform_params, rmse_m). transform_params holds the 6
    coefficients of lon_ref = a*lon_mov + b*lat_mov + c and
    lat_ref = d*lon_mov + e*lat_mov + f, computed by least squares."""
    if len(points) < MIN_CONTROL_POINTS:
        raise InvalidControlPoints(
            f"Se necesitan al menos {MIN_CONTROL_POINTS} puntos de control, se recibieron {len(points)}."
        )

    design = np.array([[p.lon_mov, p.lat_mov, 1.0] for p in points])
    if np.linalg.matrix_rank(design) < 3:
        raise InvalidControlPoints(
            "Los puntos de control son colineales o coinciden entre sí -- no se puede calcular una "
            "transformación única. Elija puntos más dispersos."
        )

    lon_ref = np.array([p.lon_ref for p in points])
    lat_ref = np.array([p.lat_ref for p in points])

    (a, b, c), *_ = np.linalg.lstsq(design, lon_ref, rcond=None)
    (d, e, f), *_ = np.linalg.lstsq(design, lat_ref, rcond=None)

    pred_lon = design @ np.array([a, b, c])
    pred_lat = design @ np.array([d, e, f])

    mean_lat_rad = math.radians(float(np.mean(lat_ref)))
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * math.cos(mean_lat_rad)

    dx_m = (pred_lon - lon_ref) * m_per_deg_lon
    dy_m = (pred_lat - lat_ref) * m_per_deg_lat
    rmse_m = float(np.sqrt(np.mean(dx_m**2 + dy_m**2)))

    transform_params = {
        "lon": {"a": float(a), "b": float(b), "c": float(c)},
        "lat": {"a": float(d), "b": float(e), "c": float(f)},
    }
    return transform_params, rmse_m
