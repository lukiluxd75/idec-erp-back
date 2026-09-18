import uuid

from app.domains.chatbot.infrastructure.models import InstitutionalContextModel, ChatbotAuditModel
from sqlalchemy.orm import Session

class LearnFromFeedbackUseCase:
    def __init__(self, db: Session):
        self._db = db

    def execute(self, rule_text: str, actor_user_sub: str) -> None:
        new_rule = InstitutionalContextModel(
            code=f"feedback_rule_{uuid.uuid4().hex[:8]}",
            category="feedback_rule",
            title="Regla aprendida de retroalimentación",
            content=rule_text
        )
        self._db.add(new_rule)
        
        audit = ChatbotAuditModel(
            actor_user_sub=actor_user_sub,
            action="feedback.learn",
            description="Agregada nueva regla a partir de retroalimentación."
        )
        self._db.add(audit)
        self._db.commit()
