from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class MapLayerItem(BaseModel):
    id: str
    code: str
    name: str
    layer_type: str
    service_type: str = "wms"
    service_url: str
    service_layer: str = "0"
    year: Optional[int] = None
    source: Optional[str] = None
    is_active: bool = True
    display_order: int = 0


class ProcedureItem(BaseModel):
    id: str
    code: str
    name: str
    description: Optional[str] = None
    category: str = "services"
    icon: str = "📋"
    requirements: List[str] = Field(default_factory=list)
    estimated_days: Optional[str] = None
    location: Optional[str] = None
    status: str = "published"
    display_order: int = 0


class AdvertisementItem(BaseModel):
    id: str
    title: str
    source_type: Literal["upload", "url"]
    source_url: Optional[str] = None
    original_file_name: Optional[str] = None
    mime_type: Optional[str] = None
    file_size: Optional[int] = None
    storage_key: Optional[str] = None
    is_active: bool = False
    display_order: int = 0
    download_url: str


class MapSearchItem(BaseModel):
    id: str
    kind: Literal["parcel", "street"]
    title: str
    subtitle: str
    geometry: Dict[str, Any]


class AdminProcedurePayload(BaseModel):
    code: Optional[str] = None
    name: str
    description: Optional[str] = None
    category: Optional[str] = "services"
    icon: Optional[str] = "📋"
    requirements: List[str] = Field(default_factory=list)
    estimated_days: Optional[str] = None
    location: Optional[str] = None
    status: str = "published"
    display_order: int = 0


class AdminLayerPayload(BaseModel):
    code: Optional[str] = None
    name: str
    layer_type: str = "imagery"
    service_type: str = "wms"
    service_url: str
    service_layer: str = "0"
    year: Optional[int] = None
    source: Optional[str] = None
    is_active: bool = True
    display_order: int = 0


class AdminAdvertisementPayload(BaseModel):
    title: str
    source_url: str
    is_active: bool = False
    display_order: int = 0


class AdvertisementUpdatePayload(BaseModel):
    title: Optional[str] = None
    source_url: Optional[str] = None
    is_active: Optional[bool] = None
    display_order: Optional[int] = None


class HealthResponse(BaseModel):
    # El atributo NO puede llamarse `schema`: pisa BaseModel.schema() y pydantic
    # avisa al importar. El alias mantiene intacto el JSON de /health, que FastAPI
    # serializa con by_alias=True.
    model_config = ConfigDict(populate_by_name=True)

    ok: bool
    schema_name: str = Field(alias="schema")
    service: str
