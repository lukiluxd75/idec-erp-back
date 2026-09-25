from typing import List, Optional, Tuple

from app.domains.folder_analysis.domain.entities import DocumentPage, DocumentStatus, PageStatus

# digitization job status -> page status
_JOB_TO_PAGE = {
    "pending": PageStatus.QUEUED,
    "processing": PageStatus.PROCESSING,
    "done": PageStatus.DONE,
    "failed": PageStatus.FAILED,
    # Someone stopped that page's digitization from the PC monitor. A dead end
    # for the page, so the document can finish instead of waiting forever.
    "stopped": PageStatus.FAILED,
}


def page_status_from_job(job_status: str) -> str:
    return _JOB_TO_PAGE.get(job_status, PageStatus.QUEUED)


def document_status(pages: List[DocumentPage]) -> Tuple[str, Optional[str]]:
    """Overall status and, when failed, the message for the architect. A failed
    page only fails the document once the other pages have finished too."""
    statuses = [p.status for p in pages]
    if any(s in PageStatus.IN_PROGRESS for s in statuses):
        return (DocumentStatus.PROCESSING if PageStatus.PROCESSING in statuses else DocumentStatus.QUEUED), None
    failed = [p for p in pages if p.status == PageStatus.FAILED]
    if failed:
        detail = "; ".join(f"página {p.page_index + 1}: {p.error or 'sin detalle'}" for p in failed)
        return DocumentStatus.FAILED, f"No se pudo analizar el documento ({detail})."
    return DocumentStatus.EXTRACTED, None
