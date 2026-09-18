"""ORM models that mirror the REAL schema of catastro_operativo (the external Avalúos
system — see ProyectoAvaluos/backend/app/models/__init__.py). This file describes that
schema, it does not define it: if those tables change, this file is updated to match,
never the other way around (same approach as app/domains/resoluciones/infrastructure/
models.py). Only the columns this domain needs to read (or, for status_id, update) are
listed.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domains.appraisal_review.infrastructure.operativo_connection import OperativoBase


class WorkflowStatusOp(OperativoBase):
    __tablename__ = "workflow_statuses"
    __table_args__ = {"schema": "config"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(100))


class CharacteristicGroupOp(OperativoBase):
    __tablename__ = "characteristic_groups"
    __table_args__ = {"schema": "config"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    code: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(150))


class CharacteristicOptionOp(OperativoBase):
    __tablename__ = "characteristic_options"
    __table_args__ = {"schema": "config"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("config.characteristic_groups.id"))
    label: Mapped[str] = mapped_column(String(200))

    group: Mapped[CharacteristicGroupOp] = relationship()


class AppraisalOp(OperativoBase):
    __tablename__ = "appraisals"
    __table_args__ = {"schema": "catastro"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    form_number: Mapped[str | None] = mapped_column(String(40))
    status_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("config.workflow_statuses.id"))
    fiscal_year: Mapped[int | None] = mapped_column(Integer)
    land_area: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    blocks_area: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    improvements_area: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    land_value: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    blocks_value: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    improvements_value: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    total_value: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    status: Mapped[WorkflowStatusOp] = relationship()
    property: Mapped["PropertyOp | None"] = relationship(back_populates="appraisal", uselist=False)


class PropertyOp(OperativoBase):
    __tablename__ = "properties"
    __table_args__ = {"schema": "catastro"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    appraisal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catastro.appraisals.id"))
    cadastral_code: Mapped[str | None] = mapped_column(String(30))
    subdistrict: Mapped[str | None] = mapped_column(String(10))
    block_code: Mapped[str | None] = mapped_column(String(20))
    plot_code: Mapped[str | None] = mapped_column(String(20))
    use_code: Mapped[str | None] = mapped_column(String(10))
    building_code: Mapped[str | None] = mapped_column(String(10))
    floor_code: Mapped[str | None] = mapped_column(String(10))
    unit_code: Mapped[str | None] = mapped_column(String(10))
    address: Mapped[str] = mapped_column(Text)
    door_number: Mapped[str | None] = mapped_column(String(30))
    building_name: Mapped[str | None] = mapped_column(String(100))
    block_label: Mapped[str | None] = mapped_column(String(50))
    floor_label: Mapped[str | None] = mapped_column(String(50))
    apartment_label: Mapped[str | None] = mapped_column(String(50))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))

    appraisal: Mapped[AppraisalOp] = relationship(back_populates="property")
    detail: Mapped["PropertyDetailOp | None"] = relationship(back_populates="property", uselist=False)
    owners: Mapped[list["OwnerOp"]] = relationship(back_populates="property")
    units: Mapped[list["ConstructionUnitOp"]] = relationship(back_populates="property")


class PropertyDetailOp(OperativoBase):
    __tablename__ = "property_details"
    __table_args__ = {"schema": "catastro"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    property_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catastro.properties.id"))
    zone_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    topography_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    shape_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    location_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    road_material_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_area: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    front_length: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    depth_length: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    observations: Mapped[str | None] = mapped_column(Text)

    property: Mapped[PropertyOp] = relationship(back_populates="detail")
    services: Mapped[list["PropertyServiceOp"]] = relationship(back_populates="detail")
    equipments: Mapped[list["PropertyEquipmentOp"]] = relationship(back_populates="detail")


class PropertyServiceOp(OperativoBase):
    __tablename__ = "property_services"
    __table_args__ = {"schema": "catastro"}

    property_detail_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("catastro.property_details.id"), primary_key=True
    )
    service_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)

    detail: Mapped[PropertyDetailOp] = relationship(back_populates="services")


class PropertyEquipmentOp(OperativoBase):
    __tablename__ = "property_equipments"
    __table_args__ = {"schema": "catastro"}

    property_detail_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("catastro.property_details.id"), primary_key=True
    )
    equipment_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)

    detail: Mapped[PropertyDetailOp] = relationship(back_populates="equipments")


class OwnerOp(OperativoBase):
    __tablename__ = "owners"
    __table_args__ = {"schema": "catastro"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    property_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catastro.properties.id"))
    person_type: Mapped[str] = mapped_column(String(20))
    first_name: Mapped[str | None] = mapped_column(String(120))
    last_name_1: Mapped[str | None] = mapped_column(String(120))
    last_name_2: Mapped[str | None] = mapped_column(String(120))
    legal_name: Mapped[str | None] = mapped_column(String(200))
    document_number: Mapped[str | None] = mapped_column(String(40))
    ownership_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    registry_matricula: Mapped[str | None] = mapped_column(String(30))
    registry_asiento: Mapped[str | None] = mapped_column(String(20))
    registry_fojas: Mapped[int | None] = mapped_column(Integer)
    registry_partida: Mapped[int | None] = mapped_column(Integer)
    deed_number: Mapped[str | None] = mapped_column(String(50))
    deed_date: Mapped[date | None] = mapped_column(Date)
    registry_ddr_date: Mapped[date | None] = mapped_column(Date)
    notary_name: Mapped[str | None] = mapped_column(String(150))
    phone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String)

    property: Mapped[PropertyOp] = relationship(back_populates="owners")


class ConstructionUnitOp(OperativoBase):
    __tablename__ = "construction_units"
    __table_args__ = {"schema": "catastro"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    property_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catastro.properties.id"))
    unit_kind: Mapped[str] = mapped_column(String(20))
    unit_number: Mapped[str] = mapped_column(String(20))
    area: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    floors_count: Mapped[int] = mapped_column(Integer)
    construction_year: Mapped[int] = mapped_column(Integer)
    modification_year: Mapped[int | None] = mapped_column(Integer)
    use_coeff_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    depreciation_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    improvement_type_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    total_score: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    unit_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    observations: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))

    property: Mapped[PropertyOp] = relationship(back_populates="units")
    characteristic_values: Mapped[list["UnitCharacteristicValueOp"]] = relationship(back_populates="unit")


class UnitCharacteristicValueOp(OperativoBase):
    __tablename__ = "unit_characteristic_values"
    __table_args__ = {"schema": "catastro"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    construction_unit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("catastro.construction_units.id")
    )
    characteristic_group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("config.characteristic_groups.id"))
    characteristic_option_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("config.characteristic_options.id"))
    percentage: Mapped[Decimal] = mapped_column(Numeric(8, 4))
    score: Mapped[Decimal] = mapped_column(Numeric(12, 4))

    unit: Mapped[ConstructionUnitOp] = relationship(back_populates="characteristic_values")
    group: Mapped[CharacteristicGroupOp] = relationship()
    option: Mapped[CharacteristicOptionOp] = relationship()
