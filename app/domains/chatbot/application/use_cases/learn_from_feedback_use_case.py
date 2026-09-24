from app.domains.chatbot.domain.ports.procedure_repository_port import ProcedureRepositoryPort


class LearnFromFeedbackUseCase:
    """Persist a human-corrected rule as an InstitutionalContext entry so the
    prompt builder picks it up on every future chat turn.

    Follows the same port pattern as every other use case in this domain
    (application/ must not import from infrastructure/ or receive a raw
    SQLAlchemy Session — CLAUDE.md §3).
    """

    def __init__(self, procedure_repository: ProcedureRepositoryPort) -> None:
        self._procedures = procedure_repository

    def execute(self, rule_text: str, actor_user_sub: str) -> None:
        self._procedures.save_feedback_rule(rule_text, actor_user_sub)
