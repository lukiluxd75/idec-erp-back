from abc import ABC, abstractmethod
from typing import Any, Dict, List


class ChatEnginePort(ABC):
    """Port over the external LLM host (Ollama, on a machine outside the ERP —
    see settings.CHATBOT_OLLAMA_URL). A single adapter is expected
    (infrastructure/ollama/ollama_chat_engine.py): there is no in-process/local
    variant planned, unlike detection's GPU engine. Implementations must raise
    ChatEngineUnavailableException (never let a raw connection error escape) when
    the host is unreachable or unconfigured."""

    @abstractmethod
    def chat(self, system_prompt: str, messages: List[Dict[str, str]]) -> str:
        """One non-streaming chat completion. `messages` are {role, content} pairs
        for the conversation so far (system prompt is passed separately, always
        rebuilt server-side per turn — see prompt_builder)."""

    @abstractmethod
    def vision(self, system_prompt: str, user_text: str, image_base64: str) -> str:
        """One non-streaming vision completion over a single embedded image."""

    @abstractmethod
    def embed(self, text: str) -> List[float]:
        """Embedding vector for one piece of text."""

    @abstractmethod
    def extract_json(self, system_prompt: str, raw_text: str) -> Dict[str, Any]:
        """Structured-output completion (Ollama `format: "json"`) used by document
        ingestion to map raw OCR text onto NuevoTramiteSchema-shaped JSON."""
