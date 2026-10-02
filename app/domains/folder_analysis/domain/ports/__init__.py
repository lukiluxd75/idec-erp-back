from app.domains.folder_analysis.domain.ports.cadastral_gis_port import CadastralGisPort, GisParcel
from app.domains.folder_analysis.domain.ports.capture_repository_port import CaptureRepositoryPort
from app.domains.folder_analysis.domain.ports.document_repository_port import DocumentRepositoryPort
from app.domains.folder_analysis.domain.ports.extraction_queue_port import ExtractionQueuePort
from app.domains.folder_analysis.domain.ports.folio_extraction_port import FolioExtractionPort
from app.domains.folder_analysis.domain.ports.pdf_rasterizer_port import PdfRasterizerPort
from app.domains.folder_analysis.domain.ports.registered_folder_repository_port import (
    RegisteredFolderRepositoryPort,
)
from app.domains.folder_analysis.domain.ports.server_reading_port import ServerReadingPort
from app.domains.folder_analysis.domain.ports.tax_extraction_port import TaxExtractionPort
from app.domains.folder_analysis.domain.ports.tax_structurer_port import TaxStructurerPort
from app.domains.folder_analysis.domain.ports.thumbnail_port import ThumbnailPort

__all__ = [
    "CadastralGisPort",
    "GisParcel",
    "CaptureRepositoryPort",
    "DocumentRepositoryPort",
    "ExtractionQueuePort",
    "FolioExtractionPort",
    "PdfRasterizerPort",
    "RegisteredFolderRepositoryPort",
    "ServerReadingPort",
    "TaxExtractionPort",
    "TaxStructurerPort",
    "ThumbnailPort",
]
