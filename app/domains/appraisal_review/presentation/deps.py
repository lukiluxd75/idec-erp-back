from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database.connection import get_db
from app.domains.appraisal_review.application.use_cases import (
    GetAppraisalDetailUseCase,
    ListPendingAppraisalsUseCase,
    MigrateAppraisalUseCase,
    SearchAppraisalsUseCase,
    SendObservationsUseCase,
)
from app.domains.appraisal_review.domain.ports import MigratedAppraisalPort, OperativoAppraisalPort, ReviewPort
from app.domains.appraisal_review.infrastructure.operativo_connection import get_operativo_db
from app.domains.appraisal_review.infrastructure.sql_migrated_appraisal_repository import (
    SqlMigratedAppraisalRepository,
)
from app.domains.appraisal_review.infrastructure.sql_operativo_appraisal_repository import (
    SqlOperativoAppraisalRepository,
)
from app.domains.appraisal_review.infrastructure.sql_review_repository import SqlReviewRepository


def get_operativo_appraisal_repo(db: Session = Depends(get_operativo_db)) -> OperativoAppraisalPort:
    return SqlOperativoAppraisalRepository(db=db)


def get_review_repo(db: Session = Depends(get_db)) -> ReviewPort:
    return SqlReviewRepository(db=db)


def get_migrated_appraisal_repo(db: Session = Depends(get_db)) -> MigratedAppraisalPort:
    return SqlMigratedAppraisalRepository(db=db)


def get_list_pending_appraisals_use_case(
    operativo_repo: OperativoAppraisalPort = Depends(get_operativo_appraisal_repo),
) -> ListPendingAppraisalsUseCase:
    return ListPendingAppraisalsUseCase(operativo_repo=operativo_repo)


def get_search_appraisals_use_case(
    operativo_repo: OperativoAppraisalPort = Depends(get_operativo_appraisal_repo),
) -> SearchAppraisalsUseCase:
    return SearchAppraisalsUseCase(operativo_repo=operativo_repo)


def get_appraisal_detail_use_case(
    operativo_repo: OperativoAppraisalPort = Depends(get_operativo_appraisal_repo),
) -> GetAppraisalDetailUseCase:
    return GetAppraisalDetailUseCase(operativo_repo=operativo_repo)


def get_send_observations_use_case(
    operativo_repo: OperativoAppraisalPort = Depends(get_operativo_appraisal_repo),
    review_repo: ReviewPort = Depends(get_review_repo),
) -> SendObservationsUseCase:
    return SendObservationsUseCase(operativo_repo=operativo_repo, review_repo=review_repo)


def get_migrate_appraisal_use_case(
    operativo_repo: OperativoAppraisalPort = Depends(get_operativo_appraisal_repo),
    migrated_repo: MigratedAppraisalPort = Depends(get_migrated_appraisal_repo),
) -> MigrateAppraisalUseCase:
    return MigrateAppraisalUseCase(operativo_repo=operativo_repo, migrated_repo=migrated_repo)
