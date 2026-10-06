from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database.connection import get_db
from app.domains.detection.application.use_cases import (
    CreateCampaignUseCase,
    ExportCampaignReportUseCase,
    GetProcessedSectorDetailUseCase,
    IngestDetectionResultUseCase,
    ListCampaignsUseCase,
    ListProcessedSectorsUseCase,
    ResumeSectorValidationUseCase,
    ReviewAffectedParcelUseCase,
    StartDetectionJobUseCase,
)
from app.domains.detection.domain.ports.affected_parcel_review_port import AffectedParcelReviewPort
from app.domains.detection.domain.ports.campaign_repository_port import CampaignRepositoryPort
from app.domains.detection.domain.ports.processed_sector_repository_port import (
    ProcessedSectorRepositoryPort,
)
from app.domains.detection.domain.ports.sector_history_port import SectorHistoryPort
from app.domains.detection.infrastructure.gpu_detection_client import GpuDetectionClient
from app.domains.detection.infrastructure.sql_affected_parcel_review_repository import (
    SqlAffectedParcelReviewRepository,
)
from app.domains.detection.infrastructure.sql_campaign_repository import SqlCampaignRepository
from app.domains.detection.infrastructure.sql_processed_sector_repository import (
    SqlProcessedSectorRepository,
)
from app.domains.detection.infrastructure.sql_sector_history_repository import (
    SqlSectorHistoryRepository,
)


def get_detection_engine() -> GpuDetectionClient:
    return GpuDetectionClient()


def get_processed_sector_repository(db: Session = Depends(get_db)) -> ProcessedSectorRepositoryPort:
    return SqlProcessedSectorRepository(db=db)


def get_campaign_repository(db: Session = Depends(get_db)) -> CampaignRepositoryPort:
    return SqlCampaignRepository(db=db)


def get_affected_parcel_review_repository(
    db: Session = Depends(get_db),
) -> AffectedParcelReviewPort:
    return SqlAffectedParcelReviewRepository(db=db)


def get_start_detection_job_use_case(
    engine: GpuDetectionClient = Depends(get_detection_engine),
    repository: ProcessedSectorRepositoryPort = Depends(get_processed_sector_repository),
) -> StartDetectionJobUseCase:
    return StartDetectionJobUseCase(engine=engine, repository=repository)


def get_ingest_detection_result_use_case(
    engine: GpuDetectionClient = Depends(get_detection_engine),
    repository: ProcessedSectorRepositoryPort = Depends(get_processed_sector_repository),
) -> IngestDetectionResultUseCase:
    return IngestDetectionResultUseCase(engine=engine, repository=repository)


def get_list_campaigns_use_case(
    repository: CampaignRepositoryPort = Depends(get_campaign_repository),
) -> ListCampaignsUseCase:
    return ListCampaignsUseCase(repository=repository)


def get_create_campaign_use_case(
    repository: CampaignRepositoryPort = Depends(get_campaign_repository),
) -> CreateCampaignUseCase:
    return CreateCampaignUseCase(repository=repository)


def get_review_affected_parcel_use_case(
    repository: AffectedParcelReviewPort = Depends(get_affected_parcel_review_repository),
) -> ReviewAffectedParcelUseCase:
    return ReviewAffectedParcelUseCase(repository=repository)


def get_sector_history_repository(db: Session = Depends(get_db)) -> SectorHistoryPort:
    return SqlSectorHistoryRepository(db=db)


def get_list_processed_sectors_use_case(
    repository: SectorHistoryPort = Depends(get_sector_history_repository),
) -> ListProcessedSectorsUseCase:
    return ListProcessedSectorsUseCase(repository=repository)


def get_processed_sector_detail_use_case(
    repository: SectorHistoryPort = Depends(get_sector_history_repository),
) -> GetProcessedSectorDetailUseCase:
    return GetProcessedSectorDetailUseCase(repository=repository)


def get_resume_sector_validation_use_case(
    engine: GpuDetectionClient = Depends(get_detection_engine),
    repository: ProcessedSectorRepositoryPort = Depends(get_processed_sector_repository),
) -> ResumeSectorValidationUseCase:
    return ResumeSectorValidationUseCase(engine=engine, repository=repository)


def get_export_campaign_report_use_case(
    repository: ProcessedSectorRepositoryPort = Depends(get_processed_sector_repository),
) -> ExportCampaignReportUseCase:
    return ExportCampaignReportUseCase(repository=repository)
