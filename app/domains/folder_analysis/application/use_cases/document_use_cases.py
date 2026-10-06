import logging
import re
from dataclasses import replace
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Set

from app.core.errors.exceptions import DomainException
from app.domains.folder_analysis.application.document_synchronizer import DocumentSynchronizer
from app.domains.folder_analysis.domain.entities import (
    CaptureStatus,
    DocumentPage,
    DocumentStatus,
    DocumentType,
    FolderDocument,
    PageStatus,
    ReadingStage,
)
from app.domains.folder_analysis.domain.exceptions import (
    CaptureNotAvailableException,
    CaptureNotFoundException,
    DocumentBusyException,
    DocumentNotFoundException,
    InvalidDocumentRequestException,
    RegisteredFolderNotFoundException,
)
from app.domains.folder_analysis.domain.extraction_profiles import profile_for
from app.domains.folder_analysis.domain.folder_types import (
    DOCUMENT_TYPES,
    FieldSource,
    document_fields,
    folder_type,
)
from app.domains.folder_analysis.domain.services import drawing_sides, plan_survey
from app.domains.folder_analysis.domain.services.field_harvest import (
    from_seals,
    from_vision,
    harvest,
    missing_labels,
    observation,
    vision_wanted,
)
from app.domains.folder_analysis.domain.ports import (
    CaptureRepositoryPort,
    DocumentRepositoryPort,
    ExtractionQueuePort,
    RegisteredFolderRepositoryPort,
    SealReadingPort,
    ServerReadingPort,
    VisionReadingPort,
)

logger = logging.getLogger("uvicorn.error")

# Cuántas fotos admite un documento.
MAX_PAGES = 20

DOC_LABEL = {key: spec.noun for key, spec in DOCUMENT_TYPES.items()}


def _require_document(repository: DocumentRepositoryPort, document_id: str, user_sub: str) -> FolderDocument:
    document = repository.get(document_id, user_sub)
    if document is None:
        raise DocumentNotFoundException()
    return document


def _validate_capture_ids(capture_ids: List[str]) -> List[str]:
    unique = list(dict.fromkeys(capture_ids or []))
    if not unique:
        raise InvalidDocumentRequestException("El documento debe tener al menos una foto.")
    if len(unique) > MAX_PAGES:
        raise InvalidDocumentRequestException(f"Un documento admite como máximo {MAX_PAGES} fotos.")
    return unique


def _file_without_reading(documents: DocumentRepositoryPort, document: FolderDocument) -> None:
    """Deja el documento guardado y terminado, sin leerlo.

    El carril de otros documentos no tiene nada que extraer: lo que se guarda son
    sus fotos. Queda en FILED desde que se crea, así que la pantalla no ofrece
    analizarlo y ningún lector lo toca. Se vuelve a llamar cuando le cambian las
    páginas, porque eso lo devuelve a borrador (ver replace_pages).
    """
    documents.save_progress(
        document.id,
        [replace(page, status=PageStatus.DONE, error=None) for page in document.pages],
        DocumentStatus.FILED,
        None,
        None,
    )


def _require_inbox_captures(captures: CaptureRepositoryPort, capture_ids: List[str], user_sub: str) -> None:
    found = {c.id: c for c in captures.get_many(capture_ids, user_sub)}
    if len(found) != len(capture_ids):
        raise CaptureNotFoundException("Una de las fotos no existe o no le pertenece.")
    if any(c.status != CaptureStatus.INBOX for c in found.values()):
        raise CaptureNotAvailableException("Una de las fotos ya forma parte de otro documento.")


class CreateDocumentUseCase:
    """The architect dropped photos onto one of the lanes.

    Inside a carpeta, the lanes are the ones its kind holds, so a document of a
    type that carpeta does not work with is refused here and not only hidden on
    screen. Dropped on the loose board (no carpeta), any known type goes."""

    def __init__(
        self,
        documents: DocumentRepositoryPort,
        captures: CaptureRepositoryPort,
        folders: Optional[RegisteredFolderRepositoryPort] = None,
    ):
        self._documents = documents
        self._captures = captures
        self._folders = folders

    def execute(
        self,
        doc_type: str,
        capture_ids: List[str],
        user_sub: str,
        folder_id: Optional[str] = None,
        folder_type_key: Optional[str] = None,
    ) -> FolderDocument:
        if doc_type not in DocumentType.ALL:
            raise InvalidDocumentRequestException("El tipo de documento no es válido.")
        folder = self._require_folder(folder_id, user_sub) if folder_id else None
        kind = folder_type(folder.folder_type if folder else folder_type_key)
        if folder is not None and not kind.holds(doc_type):
            raise InvalidDocumentRequestException(
                f'La carpeta "{folder.name}" no trabaja con ese tipo de documento.'
            )
        ids = _validate_capture_ids(capture_ids)
        _require_inbox_captures(self._captures, ids, user_sub)
        document = self._documents.create(user_sub, doc_type, ids, kind.key)
        self._captures.set_status(ids, CaptureStatus.ASSIGNED)
        if doc_type in DocumentType.NOT_READ:
            _file_without_reading(self._documents, document)
            document = _require_document(self._documents, document.id, user_sub)
        if folder is not None:
            self._folders.file_document(folder.id, document.id)
            document = _require_document(self._documents, document.id, user_sub)
        return document

    def _require_folder(self, folder_id: str, user_sub: str):
        folder = self._folders.get(folder_id, user_sub) if self._folders else None
        if folder is None:
            raise RegisteredFolderNotFoundException()
        return folder


class ConsolidateDocumentsUseCase:
    """Todo lo suelto en un solo documento del carril que no se lee.

    Un poseedor trae un montón de respaldos --carnets, recibos, cartas-- que no
    son un trámite cada uno sino el mismo legajo. Clasificarlos de a una foto
    deja el carril con veinte tarjetas de una página. Esto junta lo que quedó en
    la bandeja con las tarjetas que ya están en el carril y deja un documento con
    todas las páginas.

    Solo para DocumentType.NOT_READ: ahí juntar es pegar fotos y nada más. Un
    carril que se lee tiene resultados que habría que fusionar también, y qué
    significa fusionar dos lecturas no lo decide un botón.

    Se hace acá y no encadenando llamadas desde la web porque las fotos de una
    tarjeta tienen que dejar de ser suyas antes de ser de otra (capture_id es
    único entre páginas): encadenado desde el navegador, una ventana cerrada en
    el medio deja las fotos fuera de todo documento. Acá es un solo pedido --
    aunque cada método del repositorio confirme por su cuenta, así que si el
    rearmado falla las fotos se devuelven a la bandeja a mano, más abajo.
    """

    def __init__(
        self,
        documents: DocumentRepositoryPort,
        captures: CaptureRepositoryPort,
        folders: Optional[RegisteredFolderRepositoryPort] = None,
    ):
        self._documents = documents
        self._captures = captures
        self._folders = folders

    def execute(
        self,
        doc_type: str,
        user_sub: str,
        folder_id: Optional[str] = None,
        folder_type_key: Optional[str] = None,
    ) -> FolderDocument:
        if doc_type not in DocumentType.NOT_READ:
            raise InvalidDocumentRequestException(
                "Solo se pueden juntar los documentos que la carpeta guarda sin leer."
            )
        folder = self._require_folder(folder_id, user_sub) if folder_id else None
        kind = folder_type(folder.folder_type if folder else folder_type_key)
        if folder is not None and not kind.holds(doc_type):
            raise InvalidDocumentRequestException(
                f'La carpeta "{folder.name}" no trabaja con ese tipo de documento.'
            )

        existing = sorted(
            (
                document
                for document in self._documents.list(user_sub, doc_type=doc_type, folder_id=folder_id)
                if folder is not None or document.folder_id is None
            ),
            key=lambda document: document.created_at,
        )
        loose = [c.id for c in self._captures.list_by_status(user_sub, CaptureStatus.INBOX)]
        pages = [p.capture_id for d in existing for p in sorted(d.pages, key=lambda p: p.page_index)]
        ids = list(dict.fromkeys(pages + loose))
        if not ids:
            raise InvalidDocumentRequestException(
                "No hay fotos sueltas en la bandeja ni documentos en el carril para juntar."
            )
        # El tope es por documento, así que juntar es justo donde se alcanza.
        if len(ids) > MAX_PAGES:
            raise InvalidDocumentRequestException(
                f"Son {len(ids)} fotos y un documento admite {MAX_PAGES}. "
                "Deje fuera las que sobren o repártalas en dos documentos."
            )

        target = existing[0] if existing else None
        merged = [p.capture_id for d in existing[1:] for p in d.pages]
        for document in existing[1:]:
            self._documents.delete(document.id)

        try:
            if target is None:
                target = self._documents.create(user_sub, doc_type, ids, kind.key)
            else:
                self._documents.replace_pages(target.id, ids)
        except Exception:
            self._captures.set_status(merged, CaptureStatus.INBOX)
            raise
        self._captures.set_status(loose, CaptureStatus.ASSIGNED)
        target = _require_document(self._documents, target.id, user_sub)
        _file_without_reading(self._documents, target)
        if folder is not None:
            self._folders.file_document(folder.id, target.id)
        return _require_document(self._documents, target.id, user_sub)

    def _require_folder(self, folder_id: str, user_sub: str):
        folder = self._folders.get(folder_id, user_sub) if self._folders else None
        if folder is None:
            raise RegisteredFolderNotFoundException()
        return folder


class SetDocumentPagesUseCase:
    """Add, remove or reorder pages. Changing pages discards any previous result,
    so it is not allowed while the document is being analyzed."""

    def __init__(self, documents: DocumentRepositoryPort, captures: CaptureRepositoryPort):
        self._documents = documents
        self._captures = captures

    def execute(self, document_id: str, capture_ids: List[str], user_sub: str) -> FolderDocument:
        document = _require_document(self._documents, document_id, user_sub)
        if document.status in DocumentStatus.IN_PROGRESS:
            raise DocumentBusyException("El documento se está analizando; espere a que termine para cambiar sus fotos.")
        ids = _validate_capture_ids(capture_ids)
        current = [p.capture_id for p in document.pages]
        added = [c for c in ids if c not in current]
        removed = [c for c in current if c not in ids]
        if added:
            _require_inbox_captures(self._captures, added, user_sub)
        self._documents.replace_pages(document_id, ids)
        self._captures.set_status(added, CaptureStatus.ASSIGNED)
        self._captures.set_status(removed, CaptureStatus.INBOX)
        document = _require_document(self._documents, document_id, user_sub)
        if document.doc_type in DocumentType.NOT_READ:
            _file_without_reading(self._documents, document)
            document = _require_document(self._documents, document_id, user_sub)
        return document


class DeleteDocumentUseCase:
    """Removes the document; its photos go back to the inbox."""

    def __init__(self, documents: DocumentRepositoryPort, captures: CaptureRepositoryPort):
        self._documents = documents
        self._captures = captures

    def execute(self, document_id: str, user_sub: str) -> None:
        document = _require_document(self._documents, document_id, user_sub)
        self._documents.delete(document_id)
        self._captures.set_status([p.capture_id for p in document.pages], CaptureStatus.INBOX)


class AnalyzeDocumentUseCase:
    """Sends every page to the PCs with the extraction profile of its type --
    except the types read here on the server (a folio, a tax receipt), which the
    OCR + rules pipelines read off the request thread and queue no job at all."""

    def __init__(
        self, documents: DocumentRepositoryPort, captures: CaptureRepositoryPort, queue: ExtractionQueuePort
    ):
        self._documents = documents
        self._captures = captures
        self._queue = queue

    def execute(self, document_id: str, user_sub: str, force: bool = False) -> FolderDocument:
        document = _require_document(self._documents, document_id, user_sub)
        # El carril que no se lee no se analiza ni a pedido: se guarda y listo.
        if document.doc_type in DocumentType.NOT_READ:
            _file_without_reading(self._documents, document)
            return _require_document(self._documents, document_id, user_sub)
        if document.status in DocumentStatus.IN_PROGRESS:
            raise DocumentBusyException("El documento ya se está analizando.")
        if document.status == DocumentStatus.REVIEWED and not force:
            raise DocumentBusyException(
                "El documento ya fue revisado. Si lo vuelve a analizar se perderán sus correcciones; confirme para continuar."
            )

        if document.doc_type in DocumentType.SERVER_READ:
            # No job ids: RunServerReadingUseCase does the reading and writes the result.
            self._documents.mark_submitted(document_id, {})
            return _require_document(self._documents, document_id, user_sub)

        profile = profile_for(document.doc_type)
        job_ids: Dict[int, str] = {}
        for page in document.pages:
            image = self._captures.get_image(page.capture_id, user_sub)
            if image is None:
                raise CaptureNotFoundException(f"No se encontró la foto de la página {page.page_index + 1}.")
            content, mime = image
            job_ids[page.page_index] = self._queue.submit(
                content=content,
                file_name=f"{document.doc_type}-{document.id[:8]}-p{page.page_index + 1}.jpg",
                mime_type=mime,
                requested_by=user_sub,
                instructions=profile.instructions,
                output_template=profile.output_template,
            )
        self._documents.mark_submitted(document_id, job_ids)
        return _require_document(self._documents, document_id, user_sub)


class RunServerReadingUseCase:
    """Reads a document whose type is read here on the server (a folio with the
    folios pipeline, a tax receipt with the FUR rules) and stores the result.
    Runs in a BackgroundTask after `analyze` returned, so -- like the folios
    domain's own pipeline -- nothing is allowed to escape: every failure is
    stored on the document, where the architect can see it and retry.

    `seals` is the pass over the image that finds the stamps and reads them, for
    a carpeta whose field is stamped and not written (the number of the notary).
    Optional: without it the reading is what the text of the sheet gives.

    `vision` es la última pasada: el modelo de visión de las computadoras de los
    arquitectos mirando la foto, para lo que ni el texto ni el recorte del sello
    saben distinguir. También opcional, y también por fuera de la petición: cuesta
    entre veinte y treinta segundos por foto."""

    def __init__(
        self,
        documents: DocumentRepositoryPort,
        captures: CaptureRepositoryPort,
        extractors: Mapping[str, ServerReadingPort],
        folders: Optional[RegisteredFolderRepositoryPort] = None,
        seals: Optional[SealReadingPort] = None,
        vision: Optional[VisionReadingPort] = None,
        vision_max_pages: int = 3,
    ):
        self._documents = documents
        self._captures = captures
        self._extractors = extractors
        self._folders = folders
        self._seals = seals
        self._vision = vision
        self._vision_max_pages = vision_max_pages

    def execute(self, document_id: str, user_sub: str) -> None:
        document = self._documents.get(document_id, user_sub)
        # Gone, or the architect already changed its pages: this run is stale.
        if document is None or document.status not in DocumentStatus.IN_PROGRESS:
            return
        if document.doc_type in DocumentType.NOT_READ:
            return
        extractor = self._extractors.get(document.doc_type)
        if extractor is None:
            logger.error(
                "Folder analysis: %s %s no tiene lector en el servidor", document.doc_type, document_id
            )
            return

        label = DOC_LABEL.get(document.doc_type, "el documento")
        pages = sorted(document.pages, key=lambda p: p.page_index)
        try:
            images = []
            for page in pages:
                image = self._captures.get_image(page.capture_id, user_sub)
                if image is None:
                    raise CaptureNotFoundException(
                        f"No se encontró la foto de la página {page.page_index + 1}."
                    )
                images.append(image[0])

            self._save(document_id, pages, PageStatus.PROCESSING, DocumentStatus.PROCESSING, None, None)
            data, observations = extractor.extract(images, on_page=self._page_done(document_id, pages))
        except DomainException as exc:
            logger.warning(
                "Folder analysis: %s %s no se pudo leer: %s", document.doc_type, document_id, exc.message
            )
            self._save(document_id, pages, PageStatus.FAILED, DocumentStatus.FAILED, None, exc.message)
            return
        except Exception:
            logger.exception(
                "Folder analysis: error inesperado leyendo %s %s", document.doc_type, document_id
            )
            self._save(
                document_id, pages, PageStatus.FAILED, DocumentStatus.FAILED, None,
                f"Error inesperado al leer {label}. Vuelva a analizarlo.",
            )
            return

        data = self._with_harvested_values(document, data, observations, images)

        logger.info(
            "Folder analysis: %s %s leído con %d observación(es)",
            document.doc_type, document_id, len(observations),
        )
        self._save(document_id, pages, PageStatus.DONE, DocumentStatus.EXTRACTED, data, None)
        self._feed_folder_sheet(document, user_sub, data)

    def _with_harvested_values(
        self,
        document: FolderDocument,
        data: Dict[str, Any],
        observations: List[str],
        images: List[bytes],
    ) -> Dict[str, Any]:
        """The values the carpeta asks for, pulled out of what was read.

        A folio and a comprobante are read by parsers that know their layout and
        already answer with named values. The rest -- a plano, a declaración
        jurada -- are read generically, so what the carpeta needs is looked up by
        the label it is printed with, and stored under `values` next to the text.
        Nothing replaces the reading: what was not found stays empty and is named
        in the observations.
        """
        specs = document_fields(document.folder_type, document.doc_type)
        if not specs or not isinstance(data, dict):
            return data
        values, _missing = harvest(data, specs)
        stamped = self._from_seals(document.id, specs, values, images)
        seen = self._from_vision(document.id, specs, values, images)
        notes = [
            stamped,
            seen,
            observation(missing_labels(values, specs)),
            # Solo para el plano, como dice su nombre: buscar la cifra que la hoja
            # repite y repartir los lados medidos sobre el dibujo son reglas del
            # plano. Un avalúo repite "93.00 M2" por cada construcción, así que la
            # más repetida no es su superficie; y a un formulario le agregaba
            # frente y fondo que esa hoja no declara.
            self._complete_plan_values(data, values)
            if document.doc_type == DocumentType.PLAN
            else None,
        ]
        reading = data.get("reading")
        for note in filter(None, notes):
            observations.append(note)
            if isinstance(reading, dict):
                reading.setdefault("observations", []).append(note)
        return {**data, "values": values}

    def _from_seals(
        self,
        document_id: str,
        specs: Sequence[Any],
        values: Dict[str, Optional[str]],
        images: List[bytes],
    ) -> Optional[str]:
        """Lo que los sellos estampados en las fotos dicen, buscándolos en la imagen.

        Solo se hace para los campos que declaran vivir en un sello (hoy el
        número del notario) y solo si la lectura de sellos está cableada; un
        documento que no pide nada de un sello no gasta ni una llamada al OCR.

        Lo que diga el sello manda sobre lo que se leyó de la redacción, porque
        es donde el número está siempre: una minuta va dirigida al notario y no
        lo nombra, y el notario que sí aparece escrito suele ser el que reconoció
        el documento anterior. Si los dos dicen algo y no coinciden, queda dicho
        en las observaciones: es un caso para mirar la foto, no para elegir
        callado.

        Nunca levanta: un sello que no se pudo buscar o leer deja el campo como
        lo dejó el texto, que es exactamente lo que había antes de esta pasada.
        """
        if self._seals is None or not any(getattr(spec, "seal_patterns", ()) for spec in specs):
            return None
        self._announce(document_id, ReadingStage.SEALS)
        try:
            stamped = from_seals(self._seals.read(images), specs)
        except Exception:
            logger.exception("Folder analysis: no se pudieron leer los sellos del documento")
            return None
        disagreed = []
        for spec in specs:
            value = stamped.get(spec.key)
            if not value:
                continue
            written = values.get(spec.key)
            values[spec.key] = value
            if written and written != value:
                disagreed.append(f"{spec.label}: el sello dice {value} y el texto {written}")
        if not disagreed:
            return None
        return (
            "Se tomó lo que dice el sello; conviene comparar con la foto. "
            + "; ".join(disagreed)
            + "."
        )

    def _from_vision(
        self,
        document_id: str,
        specs: Sequence[Any],
        values: Dict[str, Optional[str]],
        images: List[bytes],
    ) -> Optional[str]:
        """La última pasada: el modelo de visión mirando la foto.

        Va al final porque es la más cara -- entre veinte y treinta segundos por
        foto en una computadora de los arquitectos-- y porque así se le pregunta
        lo menos posible: solo los campos que la carpeta declara con
        `vision_hint` y que el OCR no resolvió (vision_wanted), y solo hasta
        encontrarlos. Si el OCR leyó todo, no se gasta ni una llamada.

        Lo que ve el modelo manda sobre lo que se leyó del texto y del sello,
        porque es lo único que mira la hoja como hoja: el número del notario está
        estampado en una corona curva y a un centímetro está impresa la
        "Resolución Ministerial Nº 57/2020", que como texto se lee igual de bien.
        Cuando lo que ve no coincide con lo que se había leído, queda dicho en las
        observaciones: es un caso para mirar la foto, no para elegir callado.

        Nunca levanta: una computadora apagada, ocupada o lenta deja los valores
        como estaban, que es exactamente lo que había antes de esta pasada.
        """
        wanted = vision_wanted(specs, values)
        if not wanted:
            return None
        if self._vision is None or not self._vision.is_configured():
            # La pasada apagada no es un silencio: había algo que preguntarle a la foto y no se pudo.
            missing = ", ".join(spec.label for spec in wanted)
            logger.info(
                "Folder analysis: la pasada del modelo de visión está apagada; quedaron %s",
                missing,
            )
            return (
                "No se miró la foto con el modelo de visión (ninguna computadora conectada lo "
                f"tiene, o la pasada está apagada): {missing} quedó como lo leyó el texto."
            )
        self._announce(document_id, ReadingStage.VISION)
        by_key = {spec.key: spec for spec in specs}
        disagreed: List[str] = []
        failure: Optional[str] = None
        for page, image in enumerate(images[: max(self._vision_max_pages, 0)], start=1):
            try:
                answer = from_vision(self._vision.read(image, wanted), wanted)
            except DomainException as exc:
                # La primera hoja que no se pudo mirar ya dice por qué; las siguientes fallarían igual, así que no se insiste.
                logger.warning("Folder analysis: la foto %d no se pudo mirar: %s", page, exc.message)
                failure = exc.message
                break
            except Exception:
                logger.exception("Folder analysis: error inesperado mirando la foto %d", page)
                failure = "Error inesperado al mirar la foto."
                break
            for key, value in answer.items():
                written = values.get(key)
                values[key] = value
                if written and written != value:
                    disagreed.append(f"{by_key[key].label}: la foto dice {value} y el texto {written}")
            wanted = [spec for spec in wanted if spec.key not in answer]
            if not wanted:
                break
        # Las dos cosas pueden haber pasado: una hoja mirada que no coincidió y la siguiente que ya no se pudo mirar.
        notes = []
        if disagreed:
            notes.append("Se tomó lo que se ve en la foto; conviene comparar. " + "; ".join(disagreed) + ".")
        if failure:
            notes.append(
                "No se pudo revisar la foto con el modelo de visión, así que lo que falta quedó "
                f"como lo leyó el texto: {failure} Revíselo contra la foto."
            )
        return " ".join(notes) or None

    @staticmethod
    def _complete_plan_values(data: Dict[str, Any], values: Dict[str, Optional[str]]) -> Optional[str]:
        """What the label search could not give a plano, from the rest of the sheet.

        The useful surface, when the label was not followed by a figure that ends in
        m2 (the OCR splits the label from its number): the figure the sheet repeats.
        And frente, contra frente and fondos from the measures written on the drawing,
        for a plano that has no UTM table (domain/services/drawing_sides.py). They only
        fill what the sheet itself did not give, and only when the figures add up to the
        surface the plano declares."""
        if "usable_area" in values and not re.fullmatch(
            r"\s*\d+(?:[.,]\d+)?\s*M[2\u00b2]\s*", values.get("usable_area") or "", re.IGNORECASE
        ):
            surface = plan_survey.declared_surface(data.get("full_text") or "")
            values["usable_area"] = f"{surface:.2f}M2" if surface is not None else None
        pages = data.get("pages") or []
        dimensions = [d for page in pages for d in (page.get("dimensions") or [])]
        street = next((page["street"] for page in pages if page.get("street")), None)
        if street and not values.get("street_width") and street.get("width_m"):
            values["street_width"] = f"{float(street['width_m']):.2f} m"
        if not dimensions:
            return None
        area = re.search(r"\d+(?:[.,]\d+)?", values.get("usable_area") or "")
        result = drawing_sides.assign(dimensions, street, float(area.group(0).replace(",", ".")) if area else None)
        for key, value in result["values"].items():
            if not values.get(key):
                values[key] = value
        return result["note"]

    def _feed_folder_sheet(
        self, document: FolderDocument, user_sub: str, data: Dict[str, Any]
    ) -> None:
        """Copies what was just read into the carpeta's own sheet.

        Only the fields the carpeta declares as coming from this document, and
        only the ones still empty: what the architect typed is theirs and is
        never overwritten by a re-reading.
        """
        values = data.get("values") if isinstance(data, dict) else None
        if not values or not self._folders or not document.folder_id:
            return
        folder = self._folders.get(document.folder_id, user_sub)
        if folder is None:
            return
        sheet = dict(folder.data or {})
        filled = False
        for field in folder_type(folder.folder_type).fields:
            if field.source != FieldSource.DOCUMENT or field.from_document != document.doc_type:
                continue
            if not sheet.get(field.key) and values.get(field.key):
                sheet[field.key] = values[field.key]
                filled = True
        if filled:
            self._folders.update_details(folder.id, folder.name, folder.notes, sheet)

    def _announce(self, document_id: str, stage: Optional[str]) -> None:
        """Deja dicho en qué pasada anda la lectura, para la pantalla que la mira.

        Mientras se leen las fotos no hace falta: eso ya lo cuenta el estado de
        cada una. Hace falta después, cuando el trabajo es sobre el documento
        entero y la pantalla no tendría de dónde saber si sigue avanzando -- la
        pasada del modelo de visión se lleva entre veinte y treinta segundos por
        foto, y sin esto el cartel decía "Interpretando" y se quedaba quieto.

        No se apaga acá: lo apaga el guardado final, que es el único lugar por el
        que salen todas las lecturas (sql_document_repository.save_progress).

        Nunca levanta: un cartel que no se pudo escribir no puede tirar abajo una
        lectura que está saliendo bien.
        """
        try:
            self._documents.set_stage(document_id, stage)
        except Exception:
            logger.exception("Folder analysis: no se pudo anunciar la etapa de %s", document_id)

    def _page_done(self, document_id: str, pages: List[DocumentPage]) -> Callable[[int], None]:
        """Marks each photo as read as soon as it is, so the screen can show how
        many are left. A photo takes seconds, so this is a handful of writes.
        Never lets a failure here lose the reading that is already running."""
        finished: Set[int] = set()

        def done(index: int) -> None:
            finished.add(index)
            try:
                self._documents.save_progress(
                    document_id,
                    [
                        replace(page, status=PageStatus.DONE if i in finished else PageStatus.PROCESSING)
                        for i, page in enumerate(pages)
                    ],
                    DocumentStatus.PROCESSING,
                    None,
                    None,
                )
            except Exception:
                logger.exception("Folder analysis: no se pudo guardar el avance de %s", document_id)

        return done

    def _save(
        self,
        document_id: str,
        pages: List[DocumentPage],
        page_status: str,
        status: str,
        data: Optional[Dict[str, Any]],
        error: Optional[str],
    ) -> None:
        """One result for the whole document (its pages are read together), so
        the pages only carry the status."""
        self._documents.save_progress(
            document_id,
            [replace(page, status=page_status, error=error) for page in pages],
            status,
            data,
            error,
        )


class GetDocumentUseCase:
    def __init__(self, documents: DocumentRepositoryPort, synchronizer: DocumentSynchronizer):
        self._documents = documents
        self._synchronizer = synchronizer

    def execute(self, document_id: str, user_sub: str) -> FolderDocument:
        document = _require_document(self._documents, document_id, user_sub)
        return self._synchronizer.refresh([document])[0]


class ListDocumentsUseCase:
    def __init__(self, documents: DocumentRepositoryPort, synchronizer: DocumentSynchronizer):
        self._documents = documents
        self._synchronizer = synchronizer

    def execute(
        self,
        user_sub: str,
        doc_type: Optional[str] = None,
        folder_id: Optional[str] = None,
    ) -> List[FolderDocument]:
        if doc_type is not None and doc_type not in DocumentType.ALL:
            raise InvalidDocumentRequestException("El tipo de documento no es válido.")
        return self._synchronizer.refresh(self._documents.list(user_sub, doc_type, folder_id))


class ListReviewedDocumentsUseCase:
    """Lists only data explicitly saved by the user, optionally by document type."""

    def __init__(self, documents: DocumentRepositoryPort):
        self._documents = documents

    def execute(
        self,
        user_sub: str,
        doc_type: Optional[str] = None,
        folder_id: Optional[str] = None,
    ) -> List[FolderDocument]:
        if doc_type is not None and doc_type not in DocumentType.ALL:
            raise InvalidDocumentRequestException("El tipo de documento no es válido.")
        return self._documents.list_reviewed(user_sub, doc_type, folder_id)


class ReviewDocumentUseCase:
    """Saves the architect's corrected data (kept next to the extracted version)."""

    def __init__(self, documents: DocumentRepositoryPort):
        self._documents = documents

    def execute(self, document_id: str, user_sub: str, data: Dict[str, Any]) -> FolderDocument:
        document = _require_document(self._documents, document_id, user_sub)
        if document.status in (DocumentStatus.DRAFT, *DocumentStatus.IN_PROGRESS):
            raise DocumentBusyException("Solo puede revisar un documento que ya fue analizado.")
        if not isinstance(data, dict) or not data:
            raise InvalidDocumentRequestException("Los datos del documento están vacíos.")
        self._documents.save_review(document_id, data)
        return _require_document(self._documents, document_id, user_sub)
