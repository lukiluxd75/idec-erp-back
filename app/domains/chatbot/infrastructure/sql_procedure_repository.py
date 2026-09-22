import re
import unicodedata
import uuid
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session, joinedload

from app.domains.chatbot.domain.entities.procedure import (
    Faq,
    InstitutionalContext,
    Procedure,
    ProcedureException,
    Requirement,
    Step,
)
from app.domains.chatbot.domain.ports.procedure_repository_port import ProcedureRepositoryPort
from app.domains.chatbot.infrastructure.models import (
    ChatbotAuditModel,
    FaqModel,
    InstitutionalContextModel,
    ProcedureEmbeddingModel,
    ProcedureExceptionModel,
    ProcedureModel,
    ProcedureRequirementModel,
    ProcedureStepModel,
)


def _slugify(name: str) -> str:
    """Same shape as the ported prototype's `_generar_code`: strip accents,
    lowercase, collapse anything that is not [a-z0-9] into a single underscore."""
    normalized = unicodedata.normalize("NFD", name)
    without_accents = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    slug = re.sub(r"[^a-z0-9]+", "_", without_accents.lower()).strip("_")
    return slug or "tramite"


def _to_requirement(m: ProcedureRequirementModel) -> Requirement:
    return Requirement(
        id=str(m.id),
        description=m.description,
        is_mandatory=m.is_mandatory,
        display_order=m.display_order,
        detail=m.detail,
        where_to_obtain=m.where_to_obtain,
        validity=m.validity,
        estimated_cost=m.estimated_cost,
    )


def _to_step(m: ProcedureStepModel) -> Step:
    return Step(
        id=str(m.id),
        step_number=m.step_number,
        title=m.title,
        description=m.description,
        location=m.location,
        estimated_duration=m.estimated_duration,
        note=m.note,
    )


def _to_exception(m: ProcedureExceptionModel) -> ProcedureException:
    return ProcedureException(
        id=str(m.id),
        case_name=m.case_name,
        description=m.description,
        additional_requirements=m.additional_requirements,
        note=m.note,
    )


def _to_faq(m: FaqModel) -> Faq:
    return Faq(id=str(m.id), question=m.question, answer=m.answer, category=m.category or "general")


def _to_procedure(m: ProcedureModel) -> Procedure:
    qr_images = m.qr_image.split("|") if m.qr_image else []
    return Procedure(
        id=str(m.id),
        code=m.code,
        name=m.name,
        description=m.description,
        search_description=m.search_description,
        cost_note=m.cost_note,
        amount=float(m.amount) if m.amount is not None else None,
        currency=m.currency,
        min_days=m.min_days,
        max_days=m.max_days,
        legal_basis=m.legal_basis,
        category=m.category,
        qr_images=qr_images,
        is_active=m.is_active,
        aliases=[a.alias for a in m.aliases],
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


class SqlProcedureRepository(ProcedureRepositoryPort):
    def __init__(self, db: Session):
        self._db = db

    def _audit(self, actor_user_sub: str, action: str, description: str) -> None:
        """Records an administrative write on this domain's own audit table
        (CLAUDE.md §9) -- never security.access_audits/geoocr_audits, those
        belong to a different domain's schema (CLAUDE.md §2). Same pattern as
        SqlRbacAdminRepository._audit: own commit, right after the business write."""
        self._db.add(
            ChatbotAuditModel(actor_user_sub=actor_user_sub, action=action, description=description)
        )
        self._db.commit()

    def _get_model_by_id(self, procedure_id: str) -> Optional[ProcedureModel]:
        try:
            pid = uuid.UUID(procedure_id)
        except (ValueError, TypeError, AttributeError):
            return None
        return (
            self._db.query(ProcedureModel)
            .options(
                joinedload(ProcedureModel.aliases),
                joinedload(ProcedureModel.requirements),
                joinedload(ProcedureModel.steps),
                joinedload(ProcedureModel.exceptions),
            )
            .filter(ProcedureModel.id == pid)
            .first()
        )

    def _load_full(self, m: ProcedureModel) -> Procedure:
        procedure = _to_procedure(m)
        procedure.requirements = [_to_requirement(r) for r in sorted(m.requirements, key=lambda r: r.display_order)]
        procedure.steps = [_to_step(s) for s in sorted(m.steps, key=lambda s: s.step_number)]
        procedure.exceptions = [_to_exception(e) for e in m.exceptions]
        procedure.faqs = [
            _to_faq(f)
            for f in self._db.query(FaqModel)
            .filter(FaqModel.procedure_id == m.id, FaqModel.is_active.is_(True))
            .order_by(FaqModel.display_order)
            .all()
        ]
        return procedure

    def list_active(self) -> List[Procedure]:
        models = (
            self._db.query(ProcedureModel)
            .options(joinedload(ProcedureModel.aliases))
            .filter(ProcedureModel.is_active.is_(True))
            .all()
        )
        return [_to_procedure(m) for m in models]

    def list_for_admin(self) -> List[Procedure]:
        models = (
            self._db.query(ProcedureModel).options(joinedload(ProcedureModel.aliases)).order_by(ProcedureModel.name).all()
        )
        return [_to_procedure(m) for m in models]

    def get_by_code(self, code: str) -> Optional[Procedure]:
        m = (
            self._db.query(ProcedureModel)
            .options(
                joinedload(ProcedureModel.aliases),
                joinedload(ProcedureModel.requirements),
                joinedload(ProcedureModel.steps),
                joinedload(ProcedureModel.exceptions),
            )
            .filter(ProcedureModel.code == code)
            .first()
        )
        if m is None:
            return None
        return self._load_full(m)

    def get_by_id(self, procedure_id: str) -> Optional[Procedure]:
        m = self._get_model_by_id(procedure_id)
        if m is None:
            return None
        return self._load_full(m)

    def update_admin_fields(
        self,
        code: str,
        name: str,
        description: Optional[str],
        amount: Optional[float],
        currency: Optional[str],
        is_active: bool,
        actor_user_sub: str,
    ) -> Optional[Procedure]:
        m = self._db.query(ProcedureModel).options(joinedload(ProcedureModel.aliases)).filter(
            ProcedureModel.code == code
        ).first()
        if m is None:
            return None

        m.name = name
        m.description = description
        m.amount = amount
        m.currency = currency
        m.is_active = is_active
        self._db.commit()
        self._db.refresh(m)

        self._audit(actor_user_sub, "procedure.update", f"Trámite '{code}' actualizado desde el panel admin.")
        return _to_procedure(m)

    def upsert_from_ingest(
        self, name: str, requirements: List[str], cost_note: str, actor_user_sub: str
    ) -> Procedure:
        code = _slugify(name)
        m = self._db.query(ProcedureModel).filter(ProcedureModel.code == code).first()
        if m is None:
            m = ProcedureModel(code=code)
            self._db.add(m)

        m.name = name
        m.cost_note = cost_note or None
        self._db.flush()  # need m.id before touching requirements

        self._db.query(ProcedureRequirementModel).filter(
            ProcedureRequirementModel.procedure_id == m.id
        ).delete()
        for order, description in enumerate(requirements):
            self._db.add(
                ProcedureRequirementModel(procedure_id=m.id, description=description, display_order=order)
            )

        self._db.commit()
        self._db.refresh(m)

        self._audit(actor_user_sub, "procedure.ingest", f"Trámite '{code}' cargado/actualizado por ingesta OCR.")
        return self.get_by_id(str(m.id))

    def get_steps(self, procedure_id: str) -> List[Step]:
        procedure = self.get_by_id(procedure_id)
        return procedure.steps if procedure else []

    def get_exceptions(self, procedure_id: str) -> List[ProcedureException]:
        procedure = self.get_by_id(procedure_id)
        return procedure.exceptions if procedure else []

    def get_faqs(self, procedure_id: str) -> List[Faq]:
        procedure = self.get_by_id(procedure_id)
        return procedure.faqs if procedure else []

    def get_institutional_context(self) -> List[InstitutionalContext]:
        models = (
            self._db.query(InstitutionalContextModel)
            .filter(InstitutionalContextModel.is_active.is_(True))
            .order_by(InstitutionalContextModel.display_order)
            .all()
        )
        return [
            InstitutionalContext(id=str(m.id), code=m.code, category=m.category, title=m.title, content=m.content)
            for m in models
        ]

    def save_embeddings(self, procedure_id: str, model: str, entries: List[Tuple[str, str, List[float]]]) -> None:
        pid = uuid.UUID(procedure_id)
        self._db.query(ProcedureEmbeddingModel).filter(ProcedureEmbeddingModel.procedure_id == pid).delete()
        for source_kind, source_text, vector in entries:
            self._db.add(
                ProcedureEmbeddingModel(
                    procedure_id=pid, source_kind=source_kind, source_text=source_text, model=model, vector=vector
                )
            )
        self._db.commit()

    def list_all_embeddings(self) -> List[Tuple[str, str, List[float]]]:
        rows = self._db.query(
            ProcedureEmbeddingModel.procedure_id,
            ProcedureEmbeddingModel.source_text,
            ProcedureEmbeddingModel.vector,
        ).all()
        return [(str(procedure_id), source_text, vector) for procedure_id, source_text, vector in rows]

    def save_feedback_rule(self, rule_text: str, actor_user_sub: str) -> None:
        """Persist a human-corrected rule as an InstitutionalContext entry.
        Uses a unique code prefix to avoid colliding with manually-seeded entries."""
        import uuid as _uuid
        new_rule = InstitutionalContextModel(
            code=f"feedback_rule_{_uuid.uuid4().hex[:8]}",
            category="feedback_rule",
            title="Regla aprendida de retroalimentación",
            content=rule_text,
        )
        self._db.add(new_rule)
        self._db.commit()
        self._audit(actor_user_sub, "feedback.learn", "Agregada nueva regla a partir de retroalimentación.")

    def upsert_from_json(
        self,
        id_tramite: str,
        nombre_tramite: str,
        descripcion_busqueda: str,
        costo: str,
        leyes_asociadas: List[str],
        requisitos: List[dict],
        actor_user_sub: str,
    ) -> "Procedure":
        """Create or update a procedure from a tramites_data.json entry.

        `id_tramite` is used as the canonical `code` (e.g. "REG-ART30") so
        re-running the import is always idempotent.  Requirements fully replace
        whatever the procedure had before, matching the behaviour of
        upsert_from_ingest.
        """
        legal_basis = ", ".join(leyes_asociadas) if leyes_asociadas else None

        m = self._db.query(ProcedureModel).filter(ProcedureModel.code == id_tramite).first()
        if m is None:
            m = ProcedureModel(code=id_tramite)
            self._db.add(m)

        m.name = nombre_tramite
        m.search_description = descripcion_busqueda
        m.cost_note = costo or None
        m.legal_basis = legal_basis
        self._db.flush()  # need m.id before touching requirements

        self._db.query(ProcedureRequirementModel).filter(
            ProcedureRequirementModel.procedure_id == m.id
        ).delete()
        for order, req in enumerate(requisitos):
            description = req.get("nombre", "") if isinstance(req, dict) else str(req)
            is_mandatory = req.get("obligatorio", True) if isinstance(req, dict) else True
            detail = req.get("condicion") if isinstance(req, dict) else None
            self._db.add(
                ProcedureRequirementModel(
                    procedure_id=m.id,
                    description=description,
                    is_mandatory=is_mandatory,
                    detail=detail,
                    display_order=order,
                )
            )

        self._db.commit()
        self._db.refresh(m)
        self._audit(
            actor_user_sub,
            "procedure.json_ingest",
            f"Trámite '{id_tramite}' cargado/actualizado desde tramites_data.json.",
        )
        return self.get_by_id(str(m.id))
