from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.domains.chatbot.application.use_cases import (
    AnalyzeImageUseCase,
    AnswerQuestionUseCase,
    SubmitFeedbackUseCase,
)
from app.domains.chatbot.domain.exceptions import InvalidUploadException
from app.domains.chatbot.presentation.deps import (
    get_analyze_image_use_case,
    get_answer_question_use_case,
    get_submit_feedback_use_case,
)
from app.domains.chatbot.presentation.schemas.chat_schema import (
    ChatRequest,
    ChatResponse,
    FeedbackRequest,
    FeedbackResponse,
    VisionResponse,
)
from app.domains.security.contracts import UserProfile, require_permission

router = APIRouter(tags=["Chatbot"])

_MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB, same cap as the ported prototype


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    use_case: AnswerQuestionUseCase = Depends(get_answer_question_use_case),
    user: UserProfile = Depends(require_permission("chatbot.view")),
):
    """Answer one turn of the trámite assistant. See AnswerQuestionUseCase for
    why the request carries only the new message, never a client-supplied
    transcript."""
    message = use_case.execute(payload.conversation_id, payload.message, user.sub)
    return ChatResponse(
        conversation_id=message.conversation_id, message_id=message.id, response=message.content
    )


@router.post("/vision", response_model=VisionResponse)
async def vision(
    image: UploadFile = File(...),
    prompt: str = Form(""),
    conversation_id: Optional[str] = Form(None),
    use_case: AnalyzeImageUseCase = Depends(get_analyze_image_use_case),
    user: UserProfile = Depends(require_permission("chatbot.view")),
):
    """Analyze a document photo a citizen attaches to the chat."""
    if not image.content_type or not image.content_type.startswith("image/"):
        raise InvalidUploadException("El archivo debe ser una imagen.")

    content = await image.read()
    if not content:
        raise InvalidUploadException("La imagen está vacía.")
    if len(content) > _MAX_IMAGE_BYTES:
        raise InvalidUploadException("La imagen es demasiado grande (máx. 20 MB).")

    message = use_case.execute(conversation_id, content, prompt, user.sub)
    return VisionResponse(
        conversation_id=message.conversation_id, message_id=message.id, response=message.content
    )


@router.post("/feedback", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
def submit_feedback(
    payload: FeedbackRequest,
    use_case: SubmitFeedbackUseCase = Depends(get_submit_feedback_use_case),
    _user: UserProfile = Depends(require_permission("chatbot.view")),
):
    use_case.execute(payload.message_id, payload.feedback, payload.comment)
    return FeedbackResponse()
