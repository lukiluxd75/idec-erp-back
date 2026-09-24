from dataclasses import replace
from typing import List

from app.domains.folder_analysis.domain.entities import DocumentStatus, FolderDocument, PageStatus
from app.domains.folder_analysis.domain.ports import DocumentRepositoryPort, ExtractionQueuePort
from app.domains.folder_analysis.domain.services.document_progress import document_status, page_status_from_job
from app.domains.folder_analysis.domain.services.result_merger import merge_pages


class DocumentSynchronizer:
    """Pulls the queue status of documents that are being analyzed and stores it.
    There is no in-process event bus yet (CLAUDE.md §7), so this runs whenever a
    document is read; the web polls while something is in progress."""

    def __init__(self, repository: DocumentRepositoryPort, queue: ExtractionQueuePort):
        self._repository = repository
        self._queue = queue

    def refresh(self, documents: List[FolderDocument]) -> List[FolderDocument]:
        pending = [d for d in documents if d.status in DocumentStatus.IN_PROGRESS]
        job_ids = [p.job_id for d in pending for p in d.pages if p.status in PageStatus.IN_PROGRESS and p.job_id]
        if not job_ids:
            return documents
        jobs = self._queue.status(job_ids)

        refreshed = {}
        for document in pending:
            pages = []
            for page in document.pages:
                job = jobs.get(page.job_id) if page.status in PageStatus.IN_PROGRESS else None
                if job is None:
                    pages.append(page)
                    continue
                pages.append(replace(page, status=page_status_from_job(job.status), result=job.result, error=job.error))
            status, error = document_status(pages)
            if status == document.status and [p.status for p in pages] == [p.status for p in document.pages]:
                continue
            extracted = None
            if status == DocumentStatus.EXTRACTED:
                extracted = merge_pages(document.doc_type, [p.result or {} for p in pages])
            self._repository.save_progress(document.id, pages, status, extracted, error)
            refreshed[document.id] = replace(document, pages=pages, status=status, extracted_data=extracted, error=error)
        return [refreshed.get(d.id, d) for d in documents]
