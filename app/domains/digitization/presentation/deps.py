from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database.connection import SessionLocal, engine, get_db
from app.domains.digitization.application.use_cases import (
    CheckWorkersUseCase,
    GetJobUseCase,
    ListJobsUseCase,
    RetryJobUseCase,
    StopWorkerUseCase,
    SubmitDocumentUseCase,
)
from app.domains.digitization.domain.ports import (
    HostUsagePort,
    ImagePreprocessorPort,
    JobRepositoryPort,
    VisionWorkerPort,
)
from app.domains.digitization.infrastructure.config import get_digitization_settings
from app.domains.digitization.infrastructure.dispatcher import JobDispatcher
from app.domains.digitization.infrastructure.ollama_vision_worker import OllamaVisionWorker
from app.domains.digitization.infrastructure.opencv_image_preprocessor import OpenCvImagePreprocessor
from app.domains.digitization.infrastructure.sql_host_usage_repository import SqlHostUsageRepository
from app.domains.digitization.infrastructure.sql_job_repository import SqlJobRepository


@lru_cache()
def get_vision_worker() -> VisionWorkerPort:
    settings = get_digitization_settings()
    return OllamaVisionWorker(
        model=settings.vision_model,
        keep_alive=settings.keep_alive,
        connect_timeout=settings.connect_timeout_seconds,
        request_timeout=settings.request_timeout_seconds,
        health_timeout=settings.health_timeout_seconds,
        num_ctx=settings.num_ctx,
        num_predict=settings.num_predict,
    )


@lru_cache()
def get_host_usage() -> HostUsagePort:
    return SqlHostUsageRepository(SessionLocal)


@lru_cache()
def get_preprocessor() -> ImagePreprocessorPort:
    return OpenCvImagePreprocessor(max_side=get_digitization_settings().max_image_side)


def build_dispatcher() -> JobDispatcher:
    settings = get_digitization_settings()
    return JobDispatcher(
        engine=engine,
        session_factory=SessionLocal,
        repository_factory=SqlJobRepository,
        worker=get_vision_worker(),
        hosts=settings.worker_hosts,
        max_attempts=settings.max_attempts,
        poll_interval=settings.poll_interval_seconds,
        host_cooldown=settings.host_cooldown_seconds,
    )


def build_job_repository(db: Session) -> JobRepositoryPort:
    return SqlJobRepository(db)


def get_max_upload_bytes() -> int:
    return get_digitization_settings().max_upload_mb * 1024 * 1024


def get_job_repository(db: Session = Depends(get_db)) -> JobRepositoryPort:
    return build_job_repository(db)


def get_submit_document_use_case(
    repository: JobRepositoryPort = Depends(get_job_repository),
) -> SubmitDocumentUseCase:
    return SubmitDocumentUseCase(
        repository=repository,
        preprocessor=get_preprocessor(),
        max_bytes=get_max_upload_bytes(),
    )


def get_get_job_use_case(repository: JobRepositoryPort = Depends(get_job_repository)) -> GetJobUseCase:
    return GetJobUseCase(repository)


def get_list_jobs_use_case(repository: JobRepositoryPort = Depends(get_job_repository)) -> ListJobsUseCase:
    return ListJobsUseCase(repository)


def get_retry_job_use_case(repository: JobRepositoryPort = Depends(get_job_repository)) -> RetryJobUseCase:
    return RetryJobUseCase(repository)


def get_stop_worker_use_case(
    repository: JobRepositoryPort = Depends(get_job_repository),
) -> StopWorkerUseCase:
    return StopWorkerUseCase(repository, get_host_usage(), get_digitization_settings().worker_hosts)


def get_check_workers_use_case(
    repository: JobRepositoryPort = Depends(get_job_repository),
) -> CheckWorkersUseCase:
    return CheckWorkersUseCase(
        repository, get_vision_worker(), get_digitization_settings().worker_hosts, get_host_usage()
    )
