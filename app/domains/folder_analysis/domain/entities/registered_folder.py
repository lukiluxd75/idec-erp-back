from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.domains.folder_analysis.domain.entities.folder_document import FolderDocument

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
    """A project's folder ("carpeta registrada"): the documents that belong to
    the same trámite, kept together under the name the architect gave it.

    Its kind (`folder_type`, see domain/folder_types.py) is what says which
    documents it holds and which data it carries of its own -- two carpetas can
    both hold a folio and need different things out of it. A carpeta from before
    the catalogue carries no kind and falls back to the general one.

    The documents are opened inside the carpeta and stay in it while they are
    worked on; a document already reviewed on the loose board can be filed
    afterwards. Either way a document belongs to at most one carpeta, the way the
    paper it came from sits in a single folder.
    """

    id: str
    user_sub: str
    name: str
    created_at: datetime
    updated_at: datetime
    notes: Optional[str] = None
    folder_type: Optional[str] = None
    # The carpeta's own sheet: the field keys of its kind -> what was typed.
    data: Dict[str, Any] = field(default_factory=dict)
    documents: List[FolderDocument] = field(default_factory=list)

    @property
    def document_ids(self) -> List[str]:
        return [document.id for document in self.documents]

    @property
    def counts_by_type(self) -> Dict[str, int]:
        """How many documents of each type the carpeta holds.

        Every type its kind works with is present, at zero when it holds none, so
        the screen draws its counters without guessing -- and only those: a
        carpeta de poseedores has no reason to show a counter of comprobantes.
        A document of a type its kind does not hold (one filed before the
        carpeta had a kind) is still counted, so nothing disappears from the
        tally.
        """
        # Importado acá dentro y no arriba: el catálogo necesita los tipos de
        # documento de este paquete, así que pedirlo al importar la entidad sería
        # un círculo -- y quien importe primero el catálogo se lo come.
        from app.domains.folder_analysis.domain.folder_types import folder_type

        counts = {doc_type: 0 for doc_type in folder_type(self.folder_type).document_types}
        for document in self.documents:
            counts[document.doc_type] = counts.get(document.doc_type, 0) + 1
        return counts
