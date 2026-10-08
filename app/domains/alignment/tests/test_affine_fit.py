import pytest

from app.domains.alignment.domain.entities.alignment_block import ControlPointRecord
from app.domains.alignment.domain.exceptions import InvalidControlPoints
from app.domains.alignment.domain.services.affine_fit import fit_affine


def point(index: int, lon: float, lat: float) -> ControlPointRecord:
    return ControlPointRecord(
        order_index=index,
        lon_mov=lon,
        lat_mov=lat,
        lon_ref=2 * lon + 3 * lat + 5,
        lat_ref=-lon + 0.5 * lat + 7,
    )


def test_fit_affine_recovers_transform_from_non_collinear_points():
    transform, rmse = fit_affine(
        [point(0, 1, 2), point(1, 2, 2), point(2, 1, 3), point(3, 3, 4)]
    )

    assert transform["lon"] == pytest.approx({"a": 2, "b": 3, "c": 5})
    assert transform["lat"] == pytest.approx({"a": -1, "b": 0.5, "c": 7})
    assert rmse == pytest.approx(0, abs=1e-8)


def test_fit_affine_requires_three_points():
    with pytest.raises(InvalidControlPoints, match="al menos 3"):
        fit_affine([point(0, 1, 2), point(1, 2, 2)])


def test_fit_affine_rejects_collinear_points():
    with pytest.raises(InvalidControlPoints, match="colineales"):
        fit_affine([point(0, 0, 0), point(1, 1, 1), point(2, 2, 2)])
