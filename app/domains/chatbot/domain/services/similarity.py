"""
Cosine similarity over embeddings stored in Postgres (`procedure_embeddings`) —
replaces the ported prototype's ChromaDB index. At the current catalog size
(~70 procedures, ~2-4 embedded texts each) this is a few hundred vectors: a full
Python scan is effectively instant and needs no vector extension in Postgres.
"""
import math
from typing import List, Optional, Tuple

from app.domains.chatbot.domain.entities.conversation import ProcedureMatch


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def find_best_match(
    query_vector: List[float],
    embeddings: List[Tuple[str, str, List[float]]],
    threshold: float,
) -> ProcedureMatch:
    """`embeddings` is (procedure_id, source_text, vector) rows, typically
    ProcedureRepositoryPort.list_all_embeddings(). Returns the best-scoring
    procedure, or is_found=False if nothing clears `threshold` (or there is
    nothing indexed yet)."""
    best_procedure_id: Optional[str] = None
    best_score = 0.0

    for procedure_id, _source_text, vector in embeddings:
        score = _cosine(query_vector, vector)
        if score > best_score:
            best_score = score
            best_procedure_id = procedure_id

    if best_procedure_id is not None and best_score >= threshold:
        return ProcedureMatch(is_found=True, score=round(best_score, 4), procedure_id=best_procedure_id)
    return ProcedureMatch(is_found=False, score=round(best_score, 4))
