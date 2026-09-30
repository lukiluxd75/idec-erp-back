from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from app.domains.folder_analysis.domain.entities.folder_document import DocumentType, FolderDocument

# The name is what the architect types to recognise the project, and the note is
# the one line they may add under it; both are trimmed and capped here so the
# column width is a domain rule and not a database detail.
MAX_NAME_LENGTH = 120
MAX_NOTES_LENGTH = 500
# A carpeta holds the reviewed documents of one project. Ten folios, ten
# comprobantes and ten planos is already a very large project; the cap only
# exists so one request cannot ask for thousands of rows.
MAX_DOCUMENTS = 60


@dataclass
class RegisteredFolder:
    """A project's folder ("carpeta registrada"): the reviewed folios,
    comprobantes de impuestos and planos that belong to the same project, kept
    together under the name the architect gave it.

    Only documents whose review was saved go in -- an unreviewed document is
    still being worked on, so it has nothing to file. A document belongs to at
    most one carpeta, the way the paper it came from sits in a single folder.
    """

    id: str
    user_sub: str
    name: str
    created_at: datetime
    updated_at: datetime
    notes: Optional[str] = None
    documents: List[FolderDocument] = field(default_factory=list)

    @property
    def document_ids(self) -> List[str]:
        return [document.id for document in self.documents]

    @property
    def counts_by_type(self) -> Dict[str, int]:
        """How many documents of each type the carpeta holds, every type present
        so the screen can render the three counters without guessing."""
        counts = {doc_type: 0 for doc_type in DocumentType.ALL}
        for document in self.documents:
            counts[document.doc_type] = counts.get(document.doc_type, 0) + 1
        return counts
