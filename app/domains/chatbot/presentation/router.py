from fastapi import APIRouter

from app.domains.chatbot.presentation.endpoints.admin import router as admin_router
from app.domains.chatbot.presentation.endpoints.chat import router as chat_router

router = APIRouter()
router.include_router(chat_router, prefix="/chatbot")
router.include_router(admin_router, prefix="/chatbot")
