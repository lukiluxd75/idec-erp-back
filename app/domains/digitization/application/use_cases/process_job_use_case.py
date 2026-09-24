from app.domains.digitization.domain.entities import DigitizationJob
from app.domains.digitization.domain.exceptions import WorkerOutputException, WorkerUnavailableException
from app.domains.digitization.domain.ports import JobRepositoryPort, VisionWorkerPort


class ProcessJobUseCase:
    """Run one claimed job on one PC. On a retryable failure the job goes back to
    the queue until it reaches `max_attempts`. WorkerUnavailableException is
    re-raised after updating the job so the dispatcher can rest that PC."""

    def __init__(self, repository: JobRepositoryPort, worker: VisionWorkerPort, max_attempts: int):
        self._repository = repository
        self._worker = worker
        self._max_attempts = max_attempts

    def execute(self, job: DigitizationJob, host: str) -> None:
        image = self._repository.get_prepared_image(job.id)
        if image is None:
            self._repository.mark_failed(job.id, "No se encontró la imagen del documento.")
            return

        try:
            result = self._worker.extract(host, image, job.instructions, job.output_template)
        except WorkerUnavailableException as exc:
            self._give_back(job, f"El equipo {host} no respondió: {exc}")
            raise
        except WorkerOutputException as exc:
            self._give_back(job, f"El equipo {host} devolvió una respuesta inválida: {exc}")
            return

        self._repository.mark_done(job.id, result)

    def _give_back(self, job: DigitizationJob, error: str) -> None:
        if job.attempts >= self._max_attempts:
            self._repository.mark_failed(job.id, error)
        else:
            self._repository.release(job.id, error)
