import pytest

from app.domains.templates.domain.entities.cite import render_cite_formato
from app.domains.templates.domain.exceptions import InvalidCiteFormatException


def test_render_cite_format_replaces_all_supported_fields():
    rendered = render_cite_formato(
        "GAMC-{area}-{tipo}-{numero}/{gestion}",
        area="CAT",
        tipo="INF",
        numero="00042",
        gestion=2026,
    )

    assert rendered == "GAMC-CAT-INF-00042/2026"


def test_render_cite_format_allows_literal_braces():
    rendered = render_cite_formato(
        "{{CITE}}-{area}-{numero}", area="CAT", tipo="INF", numero="00001", gestion=2026
    )

    assert rendered == "{CITE}-CAT-00001"


def test_render_cite_format_rejects_unknown_placeholder():
    with pytest.raises(InvalidCiteFormatException):
        render_cite_formato(
            "{area}-{desconocido}", area="CAT", tipo="INF", numero="00001", gestion=2026
        )
