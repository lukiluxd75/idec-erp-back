from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class AppraisalSummaryOut(BaseModel):
    """One row in the pending-review queue."""
    id: UUID
    form_number: str | None
    status_code: str
    status_name: str
    address: str | None
    owner_name: str | None
    created_at: datetime


class OwnerOut(BaseModel):
    person_type: str
    first_name: str | None = None
    last_name_1: str | None = None
    last_name_2: str | None = None
    legal_name: str | None = None
    document_number: str | None = None
    ownership_percent: Decimal = Decimal("100")
    phone: str | None = None
    email: str | None = None
    registry_matricula: str | None = None
    registry_asiento: str | None = None
    registry_fojas: int | None = None
    registry_partida: int | None = None
    deed_number: str | None = None
    deed_date: date | None = None
    registry_ddr_date: date | None = None
    notary_name: str | None = None


class UnitCharacteristicOut(BaseModel):
    group_id: UUID
    group_code: str
    group_name: str
    option_id: UUID
    option_label: str
    percentage: Decimal
    score: Decimal


class ConstructionUnitOut(BaseModel):
    id: UUID
    unit_kind: str
    unit_number: str
    area: Decimal
    floors_count: int
    construction_year: int
    modification_year: int | None = None
    observations: str | None = None
    total_score: Decimal | None = None
    unit_value: Decimal | None = None
    use_coeff_item_id: UUID | None = None
    depreciation_item_id: UUID | None = None
    improvement_type_item_id: UUID | None = None
    characteristics: list[UnitCharacteristicOut] = Field(default_factory=list)


class PropertyOut(BaseModel):
    address: str
    door_number: str | None = None
    building_name: str | None = None
    block_label: str | None = None
    floor_label: str | None = None
    apartment_label: str | None = None
    cadastral_code: str | None = None
    subdistrict: str | None = None
    block_code: str | None = None
    plot_code: str | None = None
    use_code: str | None = None
    building_code: str | None = None
    floor_code: str | None = None
    unit_code: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    approved_area: Decimal | None = None
    front_length: Decimal | None = None
    depth_length: Decimal | None = None
    observations: str | None = None
    zone_item_id: UUID | None = None
    topography_item_id: UUID | None = None
    shape_item_id: UUID | None = None
    location_item_id: UUID | None = None
    road_material_item_id: UUID | None = None
    service_item_ids: list[UUID] = Field(default_factory=list)
    equipment_item_ids: list[UUID] = Field(default_factory=list)


class AppraisalDetailOut(BaseModel):
    id: UUID
    form_number: str | None
    status_code: str
    status_name: str
    fiscal_year: int | None
    land_area: Decimal
    blocks_area: Decimal
    improvements_area: Decimal
    land_value: Decimal
    blocks_value: Decimal
    improvements_value: Decimal
    total_value: Decimal
    property: PropertyOut
    created_at: datetime
    owner: OwnerOut | None = None
    construction_units: list[ConstructionUnitOut] = Field(default_factory=list)


class SendObservationsIn(BaseModel):
    """Free-text remarks the reviewer writes point by point — no appraisal data is edited."""
    observations: list[str] = Field(..., min_length=1)


class ObservationBatchOut(BaseModel):
    id: UUID
    form_number: str
    operativo_appraisal_id: UUID
    observations: list[str]
    reviewed_by: str
    reviewed_at: datetime


class MigratedAppraisalOut(BaseModel):
    id: UUID
    form_number: str
    operativo_appraisal_id: UUID
    is_active: bool
    migrated_by: str
    migrated_at: datetime
