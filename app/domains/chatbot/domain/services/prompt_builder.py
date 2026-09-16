"""
System prompt assembler — dynamic RAG context injection. Ported verbatim from
the prototype (app/domains/chatbot/application/prompt_builder.py in
Chatbot-Cat): the prompt text is product content in Spanish, formal register
("usted") — CONVENCIONES.md §1 keeps user-facing/product text in Spanish even
though the surrounding code is English. Only the plumbing changed: it now reads
from domain entities (Procedure, InstitutionalContext) instead of raw dicts
fetched inline, and runs synchronously (SQLAlchemy repositories, not asyncpg).
"""
import urllib.parse
from typing import List, Optional

from app.domains.chatbot.domain.entities.procedure import InstitutionalContext, Procedure

_SYSTEM_PROMPT_BASE = """\
Eres el Asistente Catastral Oficial del Gobierno Autónomo Municipal de Cochabamba (GAMC).

## Tu rol y tono
1. Escuchar la "historia" o situación del ciudadano, entender qué tiene y qué necesita.
2. Brindar información clara, guiando al usuario sobre qué trámites aplican a su caso.
3. Auditar documentos SOLO cuando el usuario esté listo para verificar los requisitos de un trámite.
4. UTILIZAR UN LENGUAJE FORMAL, INSTITUCIONAL Y MUY EDUCADO (tratar de "usted" al ciudadano) en todas tus respuestas. Evita jergas o excesiva confianza.

## Reglas de formato de respuesta
- Si estás respondiendo dudas, explicando un proceso, analizando el caso del usuario, o dando información general: RESPONDE EN TEXTO NORMAL (Markdown). ¡NO USES JSON!
- Si respondes a la opción "Contacto", proporciona números telefónicos de contacto de Catastro GAMC (ej. 4255319, 4255320, o línea de atención 151) y la dirección de las oficinas.
- SOLO si el usuario está presentando explícitamente sus documentos para ser evaluados contra los requisitos de un trámite específico, DEBES RESPONDER EXCLUSIVAMENTE CON UN OBJETO JSON VÁLIDO (sin usar bloques Markdown ```json), con la siguiente estructura:
{
  "estado": "Aprobado" o "Rechazado" o "Pendiente",
  "documentos_presentes": ["lista de documentos que el usuario mencionó tener"],
  "documentos_faltantes": ["lista de documentos requeridos que el usuario NO mencionó"],
  "observaciones": "Mensaje formal indicando qué falta, pasos a seguir o si está todo correcto."
}
"""

_CONTEXTO_SIN_TRAMITE = """\
## [CONTEXTO DEL TRÁMITE]
No se ha identificado un trámite específico para auditar documentos en este momento, o el usuario está haciendo una consulta general.

Como no hay un trámite específico que auditar:
- RESPONDE EN TEXTO NORMAL (Markdown), NO en JSON.
- Analiza la historia o situación que plantea el usuario y oriéntalo amablemente sobre los pasos a seguir.
- Si pregunta "¿Qué puedes hacer?", explica que puedes guiarlo en sus trámites catastrales, evaluar su situación legal/documental, auditar sus requisitos y resolver sus dudas.
- Si pregunta "¿Qué áreas abarcas?", indica que abarcas todos los trámites de Catastro (Certificados Catastrales, Visación de Planos, Avalúos, Cambios de Nombre, etc.) en el municipio de Cochabamba.
- Si pregunta por "Contacto", brinda los números de atención de Catastro y la dirección de las oficinas.
"""


def _institutional_block(contexts: List[InstitutionalContext]) -> str:
    ctx_text = "\n".join(f"- **{c.title}**: {c.content}" for c in contexts)
    return f"\n## [CONTEXTO DEL SISTEMA (Información General del GAMC)]\n{ctx_text}\n"


def _format_cost(procedure: Procedure) -> str:
    if procedure.amount is not None:
        cost = f"{procedure.currency or ''} {procedure.amount}".strip()
        if procedure.cost_note:
            cost += f" ({procedure.cost_note})"
        return cost
    if procedure.cost_note:
        return procedure.cost_note
    return ""


def _format_estimated_time(procedure: Procedure) -> str:
    if procedure.min_days and procedure.max_days:
        return f"{procedure.min_days} a {procedure.max_days} días hábiles"
    return ""


def _procedure_block(procedure: Procedure) -> str:
    reqs_text = "\n".join(f"  {i}. {r.description}" for i, r in enumerate(procedure.requirements, start=1))
    if not reqs_text:
        reqs_text = "  (No hay requisitos registrados)"

    pasos_text = "\n".join(f"  Paso {s.step_number}: {s.title} - {s.description}" for s in procedure.steps)
    if not pasos_text:
        pasos_text = "  (No hay pasos registrados)"

    exc_text = "\n".join(
        f"  - **Si es {e.case_name}**: {e.description}. Requisitos extra: {e.additional_requirements}"
        for e in procedure.exceptions
    )
    if not exc_text:
        exc_text = "  (No aplican casos especiales)"

    # Solo FAQ propias del trámite -- las generales ya entraron en el contexto institucional.
    faq_text = "\n".join(
        f"  P: {f.question}\n  R: {f.answer}" for f in procedure.faqs if f.category != "general"
    )
    if not faq_text:
        faq_text = "  (No hay preguntas frecuentes específicas)"

    if procedure.qr_images:
        qr_lines = "\n".join(
            f"![Formulario QR {i}]({urllib.parse.quote(qr)})"
            for i, qr in enumerate(procedure.qr_images, start=1)
        )
        qr_text = (
            "**5. Formularios QR Asociados al Trámite:**\n"
            "ATENCIÓN LLM: DEBES incluir los siguientes códigos QR en tu respuesta explicando al "
            "usuario que estos son FORMULARIOS que debe descargar, escanear o llenar. Usa la sintaxis "
            "Markdown exactamente como se muestra a continuación:\n"
            f"{qr_lines}\n"
        )
    else:
        qr_text = "**5. Formularios QR Asociados al Trámite:**\n  (No hay formularios QR disponibles)"

    costo = _format_cost(procedure)
    costo_text = f"**Costo:** {costo}" if costo else "**Costo:** No especificado en la base de datos."
    tiempo = _format_estimated_time(procedure)
    tiempo_text = f"**Tiempo estimado:** {tiempo}" if tiempo else "**Tiempo estimado:** No especificado."

    return f"""
## [CONTEXTO DEL TRÁMITE]
**Trámite detectado:** {procedure.name}
{costo_text}
{tiempo_text}

**1. Requisitos documentales (lista exhaustiva):**
{reqs_text}

**2. Pasos a seguir:**
{pasos_text}

**3. Casos especiales y excepciones:**
{exc_text}

**4. Preguntas Frecuentes Relacionadas:**
{faq_text}

{qr_text}

> RECORDATORIO PARA EL LLM: Esta es la ÚNICA información que puedes dar. No inventes requisitos adicionales ni asumas horarios o costos que no estén escritos aquí. Si te preguntan por costos, usa estrictamente el Costo provisto arriba. Si hay Formularios QR asociados, es tu OBLIGACIÓN mostrarlos en la respuesta e indicarle al ciudadano que debe escanearlos para llenar los formularios correspondientes.
"""


INGEST_SYSTEM_PROMPT: str = (
    "Eres un analista legal. Lee este texto extraído por OCR y mapealo "
    "ESTRICTAMENTE a este JSON: {'nombre_tramite': '', 'requisitos': [], 'costo': ''}. "
    "Ignora el ruido de lectura o caracteres extraños. No incluyas explicaciones."
)

VISION_SYSTEM_PROMPT: str = (
    "Eres un asistente experto en trámites catastrales del Gobierno "
    "Autónomo Municipal de Cochabamba (GAMC). Analiza las imágenes de "
    "documentos que te envían los ciudadanos. Identifica el tipo de "
    "documento, verifica si la información es legible y completa, y "
    "brinda orientación sobre qué trámite catastral corresponde. "
    "Responde siempre en español."
)

VISION_DEFAULT_USER_PROMPT: str = (
    "Analiza esta imagen de un documento catastral. Describe qué tipo de "
    "documento es, qué información contiene y si parece estar completo."
)


def build_system_prompt(
    institutional_context: List[InstitutionalContext],
    procedure: Optional[Procedure],
) -> str:
    """`procedure` is the fully-detailed match (requirements/steps/exceptions/faqs
    already loaded), or None when retrieval found nothing above the threshold."""
    bloque_institucional = _institutional_block(institutional_context)

    if procedure is None:
        return _SYSTEM_PROMPT_BASE + bloque_institucional + _CONTEXTO_SIN_TRAMITE

    return _SYSTEM_PROMPT_BASE + bloque_institucional + _procedure_block(procedure)
