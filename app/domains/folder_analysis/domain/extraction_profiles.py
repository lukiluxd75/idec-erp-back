"""
What to extract from each document type. The instructions go to the vision model on
the architects' PCs together with the JSON template it must fill. Keys are English
(internal identifiers, CLAUDE.md §1); the web maps them to Spanish labels.

A plan has no profile yet (fields to be defined): it gets the generic digitization
(full text, labeled fields and tables).
"""
from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.domains.folder_analysis.domain.entities import DocumentType

_PERSON = {"name": None, "id_number": None, "id_issued_at": None, "marital_status": None, "role": None}

FOLIO_TEMPLATE: Dict[str, Any] = {
    "registration_number": None,
    "registration_status": None,
    "administrative_location": None,
    "cadastre": None,
    "property_type": None,
    "location": None,
    "designation": None,
    "surface": None,
    "measures": None,
    "boundaries": {"north": None, "south": None, "east": None, "west": None},
    "property": None,
    "prior_title": None,
    "date": None,
    "page": {"number": None, "total": None},
    "ownership_entries": [
        {
            "entry_number": None,
            "owners": [_PERSON],
            "share": None,
            "act": None,
            "document": None,
            "authority": None,
            "filing": None,
        }
    ],
}

FOLIO_INSTRUCTIONS = """This photo is one page of a Bolivian "Folio Real" (Registro de la Propiedad Inmueble, Derechos Reales).
Extract ONLY two parts and ignore everything else (columns "B) GRAVÁMENES Y RESTRICCIONES" and "C) CANCELACIONES", stamps, signatures, barcodes):

1. The property description block in the upper part (labelled "Dirección Administrativa Financiera" on the margin):
- registration_number: the number after "MATRÍCULA Nº" (e.g. 3.01.1.01.0058438); registration_status: the word next to it (e.g. VIGENTE).
- administrative_location: the comma-separated line printed ABOVE the matricula number (province, section, canton).
- cadastre: the value after "CATASTRO:" (null if empty or just an "x").
- property_type: the text in parentheses on the "UBICACIÓN" line (e.g. "Lote de Terreno"), without the parentheses.
- location: the address on the "UBICACIÓN" line (urbanization, street, block).
- designation: "DESIGNACIÓN S/TIT:"; surface: "SUPERFICIE:" (keep units, drop the asterisks); measures: "MEDIDAS:".
- boundaries: "LINDEROS:" split by N. (north), S. (south), E. (east), O. (west), without the "N.:" prefixes.
- property: the value under "PROPIEDAD:"; prior_title: the "Antecedente Dominial" line; date: the "Fecha:" at the bottom.
- page: from "Pag. X de N" at the bottom (number = X, total = N).
If this page has no such block (a continuation page), leave those fields null.

2. Column "A) TITULARIDAD SOBRE EL DOMINIO" with its "PROPORCIÓN" column: one item per "Asiento Numero".
Each asiento only has the lines printed between its "Asiento Numero" and the next one: never copy act, document, authority or filing from another asiento (use null when the asiento does not print them).
- entry_number: the number after "Asiento Numero:".
- owners: every person in that asiento. name exactly as printed; id_number and id_issued_at from "C.I."/"c/CI" (e.g. "c/CI 4482143 CBA" -> 4482143 and CBA); marital_status from abbreviations such as "sol." (soltero/a), "cas." (casado/a), "viu." (viudo/a), "div." (divorciado/a); role only when a label such as "Vendedor(es):" is literally printed right above the name (copy the word without the colon), otherwise null -- do not deduce roles.
- share: the PROPORCIÓN printed next to the asiento (e.g. 1/1, 50%).
- act: the kind of transfer (e.g. "Compra Venta"); document: the document line (e.g. "Escrit. Priv. de fecha 12/10/1992"); authority: the notary and/or judge lines; filing: the "Present.-" line.
Drop the dashes and "#" used as filler. Copy names and numbers exactly; do not correct spelling."""

TAX_RECEIPT_TEMPLATE: Dict[str, Any] = {
    "receipt_type": None,
    "receipt_number": None,
    "municipality": None,
    "paid_at": None,
    "collecting_entity": None,
    "correspondent": None,
    "branch": None,
    "agency": None,
    "cashier": None,
    "folio": None,
    "concept": None,
    "tax_year": None,
    "taxpayer": {"type": None, "id_number": None, "name": None},
    "property_number": None,
    "cadastral_code": None,
    "property_class": None,
    "ownership_type": None,
    "location": None,
    "land_area": None,
    "built_area": None,
    "age_factor": None,
    "ufv": None,
    "taxable_base": None,
    "assessed_tax": None,
    "exemption": None,
    "discount_10": None,
    "discount_app_5": None,
    "amount_due": None,
    "amount_paid": None,
    "balance": None,
}

TAX_RECEIPT_INSTRUCTIONS = """This photo is a Bolivian municipal property tax payment receipt ("FUR - COMPROBANTE DE PAGO", IMPBI, RUAT).
Read every value exactly as printed:
- receipt_type: e.g. "FUR - COMPROBANTE DE PAGO"; receipt_number: the "Nº" of the receipt; municipality: e.g. "GAM - COCHABAMBA"; paid_at: the "FECHA:" with its time.
- collecting_entity: "ENTIDAD RECAUDADORA"; correspondent: "CORRESP."; branch: "SUCURSAL"; agency: "AGENCIA"; cashier: "CAJERO"; folio: "FOLIO".
- concept: the tax line (e.g. "INMUEBLES IMPBI 2024 TOTAL"); tax_year: the year in that line.
- taxpayer from "CONTRIBUYENTE:": type (e.g. NATURAL), id_number (the digits after "CI-"), name.
- property_number: "Nº INMUEBLE"; cadastral_code: "COD. CAT."; property_class: "CLASE"; ownership_type: "TIPO PROPIEDAD"; location: "UBICACION" (the whole address, even if it wraps to the next line).
- land_area: "SUP. TERRENO"; built_area: "SUP. TOTAL CONSTRUCCION" (keep "m2"); age_factor: "FACTOR ANTIGÜEDAD".
- ufv, taxable_base ("BASE IMPONIBLE"), assessed_tax ("IMPUESTO DETERMINADO"), exemption ("EXENCION"), discount_10 ("DESCUENTO 10%"), discount_app_5 ("DESCUENTO APP 5%"), amount_due ("IMPORTE A PAGAR"), amount_paid ("MONTO PAGADO"), balance ("SALDO GESTION"): the amounts as printed, without "Bs".
Copy codes character by character (letters and digits matter)."""


@dataclass(frozen=True)
class ExtractionProfile:
    instructions: Optional[str]
    output_template: Optional[Dict[str, Any]]


PROFILES: Dict[str, ExtractionProfile] = {
    DocumentType.FOLIO: ExtractionProfile(FOLIO_INSTRUCTIONS, FOLIO_TEMPLATE),
    DocumentType.TAX_RECEIPT: ExtractionProfile(TAX_RECEIPT_INSTRUCTIONS, TAX_RECEIPT_TEMPLATE),
    DocumentType.PLAN: ExtractionProfile(None, None),
}
