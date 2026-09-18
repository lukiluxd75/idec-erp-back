"""
Shared re-embedding logic, used by every write path that can change what a
procedure's vectors should represent (admin edit, OCR ingest, bulk reindex).
One place instead of three keeps them from drifting apart — the exact bug this
replaces: the ported prototype computed embeddings once, lazily, and never
recomputed them on edit (see the ChromaDB note in domain/entities and the
integration plan)."""
from typing import List

from app.domains.chatbot.domain.entities.procedure import Procedure
from app.domains.chatbot.domain.ports.chat_engine_port import ChatEnginePort
from app.domains.chatbot.domain.ports.procedure_repository_port import ProcedureRepositoryPort


def reindex_procedure(
    procedure: Procedure,
    chat_engine: ChatEnginePort,
    repository: ProcedureRepositoryPort,
    model: str,
) -> None:
    """Embeds the procedure's name, every alias, and its search_description (the
    prototype only embedded name + alias; the seeded catalog has no aliases, so
    search_description makes up for that missing retrieval signal — see the
    integration plan), and replaces its stored embedding rows in one call."""
    texts: List[tuple] = [("name", procedure.name)]
    for alias in procedure.aliases:
        if alias.strip():
            texts.append(("alias", alias))
    if procedure.search_description and procedure.search_description.strip():
        texts.append(("description", procedure.search_description))

    entries = [(kind, text, chat_engine.embed(text)) for kind, text in texts]
    repository.save_embeddings(procedure.id, model, entries)
