"""Implements OperativoAppraisalPort against catastro_operativo (the external Avalúos
system's own DB — see operativo_connection.py). Two methods write a single column
(status_id) back: mark_needs_correction / mark_approved. Nothing else in this
repository ever commits.
"""
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from app.domains.appraisal_review.domain.entities import (
    AppraisalDetail,
    AppraisalSummary,
    ConstructionUnit,
    Owner,
    Property,
    UnitCharacteristic,
)
from app.domains.appraisal_review.domain.ports.operativo_appraisal_port import OperativoAppraisalPort
from app.domains.appraisal_review.infrastructure.operativo_models import (
    AppraisalOp,
    ConstructionUnitOp,
    OwnerOp,
    PropertyDetailOp,
    PropertyOp,
    UnitCharacteristicValueOp,
    WorkflowStatusOp,
)

PENDING_REVIEW_STATUS_CODE = "submitted"
NEEDS_CORRECTION_STATUS_CODE = "needs_correction"
APPROVED_STATUS_CODE = "approved"


def _owner_to_entity(row: OwnerOp) -> Owner:
    return Owner(
        person_type=row.person_type,
        first_name=row.first_name,
        last_name_1=row.last_name_1,
        last_name_2=row.last_name_2,
        legal_name=row.legal_name,
        document_number=row.document_number,
        ownership_percent=row.ownership_percent if row.ownership_percent is not None else Decimal("100"),
        phone=row.phone,
        email=row.email,
        registry_matricula=row.registry_matricula,
        registry_asiento=row.registry_asiento,
        registry_fojas=row.registry_fojas,
        registry_partida=row.registry_partida,
        deed_number=row.deed_number,
        deed_date=row.deed_date,
        registry_ddr_date=row.registry_ddr_date,
        notary_name=row.notary_name,
    )


def _property_to_entity(row: PropertyOp) -> Property:
    detail = row.detail
    return Property(
        address=row.address,
        door_number=row.door_number,
        building_name=row.building_name,
        block_label=row.block_label,
        floor_label=row.floor_label,
        apartment_label=row.apartment_label,
        cadastral_code=row.cadastral_code,
        subdistrict=row.subdistrict,
        block_code=row.block_code,
        plot_code=row.plot_code,
        use_code=row.use_code,
        building_code=row.building_code,
        floor_code=row.floor_code,
        unit_code=row.unit_code,
        latitude=row.latitude,
        longitude=row.longitude,
        approved_area=detail.approved_area if detail else None,
        front_length=detail.front_length if detail else None,
        depth_length=detail.depth_length if detail else None,
        observations=detail.observations if detail else None,
        zone_item_id=detail.zone_item_id if detail else None,
        topography_item_id=detail.topography_item_id if detail else None,
        shape_item_id=detail.shape_item_id if detail else None,
        location_item_id=detail.location_item_id if detail else None,
        road_material_item_id=detail.road_material_item_id if detail else None,
        service_item_ids=[s.service_item_id for s in detail.services] if detail else [],
        equipment_item_ids=[e.equipment_item_id for e in detail.equipments] if detail else [],
    )


def _characteristic_to_entity(row: UnitCharacteristicValueOp) -> UnitCharacteristic:
    return UnitCharacteristic(
        group_id=row.characteristic_group_id,
        group_code=row.group.code,
        group_name=row.group.name,
        option_id=row.characteristic_option_id,
        option_label=row.option.label,
        percentage=row.percentage,
        score=row.score,
    )


def _unit_to_entity(row: ConstructionUnitOp) -> ConstructionUnit:
    return ConstructionUnit(
        id=row.id,
        unit_kind=row.unit_kind,
        unit_number=row.unit_number,
        area=row.area,
        floors_count=row.floors_count,
        construction_year=row.construction_year,
        modification_year=row.modification_year,
        observations=row.observations,
        total_score=row.total_score,
        unit_value=row.unit_value,
        use_coeff_item_id=row.use_coeff_item_id,
        depreciation_item_id=row.depreciation_item_id,
        improvement_type_item_id=row.improvement_type_item_id,
        characteristics=[_characteristic_to_entity(c) for c in row.characteristic_values],
    )


class SqlOperativoAppraisalRepository(OperativoAppraisalPort):
    def __init__(self, db: Session):
        self._db = db

    def list_pending_review(self, limit: int = 100) -> list[AppraisalSummary]:
        stmt = (
            select(AppraisalOp)
            .join(AppraisalOp.status)
            .options(joinedload(AppraisalOp.status), joinedload(AppraisalOp.property).joinedload(PropertyOp.owners))
            .where(WorkflowStatusOp.code == PENDING_REVIEW_STATUS_CODE)
            .order_by(AppraisalOp.created_at.asc())
            .limit(limit)
        )
        rows = self._db.execute(stmt).unique().scalars().all()
        return [self._summary_to_entity(r) for r in rows]

    def search_by_form_number(self, term: str, limit: int = 40) -> list[AppraisalSummary]:
        stmt = (
            select(AppraisalOp)
            .options(joinedload(AppraisalOp.status), joinedload(AppraisalOp.property).joinedload(PropertyOp.owners))
            .where(AppraisalOp.form_number.ilike(f"%{term}%"))
            .order_by(AppraisalOp.created_at.desc())
            .limit(limit)
        )
        rows = self._db.execute(stmt).unique().scalars().all()
        return [self._summary_to_entity(r) for r in rows]

    def get_by_form_number(self, form_number: str) -> AppraisalDetail | None:
        stmt = (
            select(AppraisalOp)
            .options(
                joinedload(AppraisalOp.status),
                joinedload(AppraisalOp.property).joinedload(PropertyOp.owners),
                joinedload(AppraisalOp.property)
                .joinedload(PropertyOp.detail)
                .joinedload(PropertyDetailOp.services),
                joinedload(AppraisalOp.property)
                .joinedload(PropertyOp.detail)
                .joinedload(PropertyDetailOp.equipments),
                joinedload(AppraisalOp.property)
                .joinedload(PropertyOp.units)
                .joinedload(ConstructionUnitOp.characteristic_values)
                .joinedload(UnitCharacteristicValueOp.group),
                joinedload(AppraisalOp.property)
                .joinedload(PropertyOp.units)
                .joinedload(ConstructionUnitOp.characteristic_values)
                .joinedload(UnitCharacteristicValueOp.option),
            )
            .where(AppraisalOp.form_number == form_number)
        )
        row = self._db.execute(stmt).unique().scalar_one_or_none()
        if row is None:
            return None

        prop = row.property
        owner = prop.owners[0] if prop and prop.owners else None

        return AppraisalDetail(
            id=row.id,
            form_number=row.form_number,
            status_code=row.status.code,
            status_name=row.status.name,
            fiscal_year=row.fiscal_year,
            land_area=row.land_area,
            blocks_area=row.blocks_area,
            improvements_area=row.improvements_area,
            land_value=row.land_value,
            blocks_value=row.blocks_value,
            improvements_value=row.improvements_value,
            total_value=row.total_value,
            property=_property_to_entity(prop),
            created_at=row.created_at,
            owner=_owner_to_entity(owner) if owner else None,
            construction_units=[_unit_to_entity(u) for u in prop.units] if prop else [],
        )

    def mark_needs_correction(self, appraisal_id: UUID) -> None:
        self._set_status(appraisal_id, NEEDS_CORRECTION_STATUS_CODE)

    def mark_approved(self, appraisal_id: UUID) -> None:
        self._set_status(appraisal_id, APPROVED_STATUS_CODE)

    def _set_status(self, appraisal_id: UUID, status_code: str) -> None:
        status_id = self._db.execute(
            select(WorkflowStatusOp.id).where(WorkflowStatusOp.code == status_code)
        ).scalar_one()
        self._db.execute(update(AppraisalOp).where(AppraisalOp.id == appraisal_id).values(status_id=status_id))
        self._db.commit()

    @staticmethod
    def _summary_to_entity(row: AppraisalOp) -> AppraisalSummary:
        prop = row.property
        owner = prop.owners[0] if prop and prop.owners else None
        owner_name = None
        if owner:
            owner_name = owner.legal_name or " ".join(
                p for p in [owner.first_name, owner.last_name_1, owner.last_name_2] if p
            )
        return AppraisalSummary(
            id=row.id,
            form_number=row.form_number,
            status_code=row.status.code,
            status_name=row.status.name,
            address=prop.address if prop else None,
            owner_name=owner_name,
            created_at=row.created_at,
        )
