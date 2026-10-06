import pytest

from app.domains.procedurereports.infrastructure.odbc_connection import (
    build_reports_connection_string,
    parse_reports_server,
    resolve_odbc_driver,
)


def test_parse_reports_server_comma_port():
    assert parse_reports_server("172.16.67.100,1433") == ("172.16.67.100", 1433)


def test_parse_reports_server_host_only():
    assert parse_reports_server("172.16.67.100") == ("172.16.67.100", 1433)


def test_freetds_connection_string_uses_port_not_comma_server(monkeypatch):
    monkeypatch.setattr(
        "app.domains.procedurereports.infrastructure.odbc_connection.pyodbc.drivers",
        lambda: ["FreeTDS"],
    )
    cs = build_reports_connection_string(
        server="172.16.67.100,1433",
        database="catastro",
        user="u",
        password="p",
        driver="FreeTDS",
    )
    assert "SERVER=172.16.67.100;" in cs
    assert "PORT=1433;" in cs
    assert "172.16.67.100,1433" not in cs
    assert "TDS_Version=7.4;" in cs


def test_resolve_odbc_driver_prefers_explicit_when_installed(monkeypatch):
    monkeypatch.setattr(
        "app.domains.procedurereports.infrastructure.odbc_connection.pyodbc.drivers",
        lambda: ["FreeTDS", "ODBC Driver 17 for SQL Server"],
    )
    assert resolve_odbc_driver("FreeTDS") == "FreeTDS"


def _drivers(monkeypatch, names):
    monkeypatch.setattr(
        "app.domains.procedurereports.infrastructure.odbc_connection.pyodbc.drivers",
        lambda: names,
    )


_WINDOWS_WITH_OFFICE = [
    "SQL Server",
    "Microsoft Access Driver (*.mdb, *.accdb)",
    "Microsoft Excel Driver (*.xls, *.xlsx, *.xlsm, *.xlsb)",
]


def test_falls_back_to_legacy_windows_driver(monkeypatch):
    _drivers(monkeypatch, _WINDOWS_WITH_OFFICE)
    assert resolve_odbc_driver("FreeTDS") == "SQL Server"


def test_legacy_driver_gets_no_tls_keywords(monkeypatch):
    _drivers(monkeypatch, _WINDOWS_WITH_OFFICE)
    cs = build_reports_connection_string(
        server="172.16.67.100,1433",
        database="catastro",
        user="u",
        password="p",
        driver="",
    )
    assert "DRIVER={SQL Server};" in cs
    assert "SERVER=172.16.67.100,1433;" in cs
    assert "Encrypt=" not in cs
    assert "TrustServerCertificate=" not in cs


def test_modern_driver_keeps_tls_keywords(monkeypatch):
    _drivers(monkeypatch, ["ODBC Driver 18 for SQL Server", "SQL Server"])
    cs = build_reports_connection_string(
        server="172.16.67.100",
        database="catastro",
        user="u",
        password="p",
        driver="",
        encrypt=True,
    )
    assert "DRIVER={ODBC Driver 18 for SQL Server};" in cs
    assert "TrustServerCertificate=yes;" in cs
    assert "Encrypt=yes;" in cs


def test_requested_driver_never_matches_an_office_driver(monkeypatch):
    # "Driver" aparece en los de Office: el match por subcadena no debe salirse de la familia SQL Server.
    _drivers(monkeypatch, ["Microsoft Access Text Driver (*.txt, *.csv)"])
    with pytest.raises(RuntimeError, match="No SQL Server ODBC driver found"):
        resolve_odbc_driver("Driver")


def test_requested_driver_matches_by_partial_name(monkeypatch):
    _drivers(monkeypatch, ["FreeTDS"])
    assert resolve_odbc_driver("FreeTDS 1.3") == "FreeTDS"
