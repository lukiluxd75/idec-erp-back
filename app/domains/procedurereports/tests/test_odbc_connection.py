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
