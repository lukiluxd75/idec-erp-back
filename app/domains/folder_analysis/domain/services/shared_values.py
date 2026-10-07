"""Lo que una hoja de la carpeta no dijo y otra hoja de la misma carpeta sí dice.

El plano y el avalúo de una carpeta de poseedores hablan del mismo predio: los
dos imprimen el código catastral y la superficie útil del lote. Cuando una de
las dos lo trae leído y en la otra quedó vacío --el OCR no encontró el rótulo, la
cifra quedó pegada al dibujo, la fotocopia estaba velada-- el dato ya está en la
carpeta, y pedirlo a mano otra vez es hacer copiar lo que el sistema tiene a la
vista.

Esto es lo que lo pasa de una hoja a la otra, y nada más que eso:

- Solo entre campos que las dos hojas declaran con la MISMA clave
  (folder_types.DOCUMENT_FIELDS). La clave es la que dice que es el mismo dato;
  dos rótulos parecidos no alcanzan. Hoy, en poseedores, son la superficie útil y
  el código catastral, que el plano y el avalúo declaran los dos.
- Solo lo que quedó vacío. Nada pisa lo que la hoja sí dijo: dos hojas que
  declaran superficies distintas es justamente lo que el arquitecto tiene que
  ver, no algo que se arregle eligiendo una en silencio.
- Nunca callado. Cada valor prestado queda nombrado en las observaciones y
  anotado con el documento del que salió (BORROWED), para poder compararlo con la
  foto.
- Lo prestado no se vuelve a prestar: un valor se toma de la hoja que lo trae
  impreso, no de una tercera que ya lo tenía prestado.
- Solo entre carriles distintos. Dos hojas del mismo carril son dos hojas de la
  misma clase y no una la copia de la otra: un plano de ubicación y un plano
  arquitectónico declaran los dos el frente y el fondo, y no son los del mismo
  dibujo. Que dos CARRILES declaren la misma clave es lo que dice que ahí hay un
  solo dato.

Puro: trabaja sobre los valores que se le dan (CLAUDE.md §3).
"""
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set

from app.domains.folder_analysis.domain.folder_types import (
    DOCUMENT_TYPES,
    document_fields,
    folder_type,
)

# Dónde queda anotado, dentro de lo leído de un documento, de qué otro documento
# salió cada valor prestado: clave del campo -> tipo de documento que lo prestó.
BORROWED = "borrowed_values"


@dataclass(frozen=True)
class Lender:
    """Otro documento de la carpeta, con lo que se le leyó.

    `borrowed` son las claves que ese documento tampoco leyó de su hoja y tiene
    prestadas de un tercero: no se vuelven a prestar.
    """

    doc_type: str
    values: Mapping[str, Any] = field(default_factory=dict)
    borrowed: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Borrowed:
    """Un valor que esta hoja no trajo y otro documento de la carpeta sí."""

    key: str
    label: str
    value: str
    doc_type: str

    @property
    def noun(self) -> str:
        spec = DOCUMENT_TYPES.get(self.doc_type)
        return spec.noun if spec else "el documento"


def lender(doc_type: str, data: Optional[Mapping[str, Any]]) -> Lender:
    """Un documento ya leído, visto como lo que le puede prestar a otro."""
    read = data if isinstance(data, Mapping) else {}
    values = read.get("values")
    sources = read.get(BORROWED)
    return Lender(
        doc_type=doc_type,
        values=values if isinstance(values, Mapping) else {},
        borrowed=sources if isinstance(sources, Mapping) else {},
    )


def shared_keys(folder_type_key: Optional[str], doc_type: str) -> Set[str]:
    """Las claves de este documento que algún otro documento de la carpeta también declara."""
    own = _declared(folder_type_key, doc_type)
    if not own:
        return set()
    shared: Set[str] = set()
    for other in folder_type(folder_type_key).document_types:
        if other != doc_type:
            shared |= own & _declared(folder_type_key, other)
    return shared


def borrow(
    folder_type_key: Optional[str],
    doc_type: str,
    values: Mapping[str, Any],
    lenders: Sequence[Lender],
    replacing: Iterable[str] = (),
) -> List[Borrowed]:
    """Lo que esta hoja no trajo y otro documento de la carpeta sí, sin aplicarlo.

    `lenders` va en orden de preferencia: el primero que diga algo contesta.

    `replacing` son las claves cuyo valor actual es prestado y puede cambiarse:
    lo que un documento prestó antes se vuelve a tomar de él cuando se lo lee de
    nuevo y ahora dice otra cosa. Sin eso, volver a analizar la hoja de la que
    salió el dato dejaría el valor viejo pegado al hermano para siempre.
    """
    specs = {spec.key: spec for spec in document_fields(folder_type_key, doc_type)}
    shared = shared_keys(folder_type_key, doc_type)
    replaceable = set(replacing)
    taken: List[Borrowed] = []
    for key, spec in specs.items():
        if key not in shared:
            continue
        current = values.get(key)
        if _said(current) and key not in replaceable:
            continue
        for source in lenders:
            if key in source.borrowed or key not in _declared(folder_type_key, source.doc_type):
                continue
            value = _clean(source.values.get(key))
            if value is None:
                # Esa hoja declara el campo y tampoco lo trae: se le pregunta a la siguiente.
                continue
            if value == _clean(current):
                # Ya dice lo mismo que está guardado: no hay nada que traer ni que avisar.
                break
            taken.append(Borrowed(key, spec.label, value, source.doc_type))
            break
    return taken


def apply(values: Dict[str, Any], taken: Sequence[Borrowed]) -> Dict[str, str]:
    """Deja los valores prestados en `values` y devuelve de qué documento salió cada uno."""
    for item in taken:
        values[item.key] = item.value
    return {item.key: item.doc_type for item in taken}


def observation(taken: Sequence[Borrowed]) -> Optional[str]:
    """Lo que se prestó, dicho para el arquitecto."""
    if not taken:
        return None
    return (
        "Lo que esta hoja no decía se tomó de otro documento de la misma carpeta; "
        "conviene compararlo con la foto. "
        + "; ".join(f"{item.label}: {item.value}, {_de(item.noun)}" for item in taken)
        + "."
    )


def _declared(folder_type_key: Optional[str], doc_type: str) -> Set[str]:
    return {spec.key for spec in document_fields(folder_type_key, doc_type)}


def _clean(value: Any) -> Optional[str]:
    """El valor como se guarda, o None cuando no dice nada."""
    if value is None or isinstance(value, (dict, list, bool)):
        return None
    return str(value).strip() or None


def _said(value: Any) -> bool:
    return _clean(value) is not None


def _de(noun: str) -> str:
    """"el plano" -> "del plano"; "la declaración jurada" -> "de la declaración jurada"."""
    return f"del {noun[3:]}" if noun.startswith("el ") else f"de {noun}"
