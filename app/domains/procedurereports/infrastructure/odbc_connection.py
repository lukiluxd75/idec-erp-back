"""Build pyodbc connection strings for SQL Server (Windows ODBC 17/18 vs Linux FreeTDS)."""
from __future__ import annotations

import logging

import pyodbc

logger = logging.getLogger(__name__)

_PREFERRED_DRIVERS = (
    "ODBC Driver 18 for SQL Server",
    "ODBC Driver 17 for SQL Server",
    "FreeTDS",
)


def _driver_index() -> dict[str, str]:
    return {name.lower(): name for name in pyodbc.drivers()}


def parse_reports_server(server: str) -> tuple[str, int]:
    """Accept host, host:port, or host,port (common in REPORTS_DB_SERVER)."""
    raw = (server or "").strip()
    if not raw:
        raise RuntimeError("REPORTS_DB_SERVER is empty.")
    if "," in raw:
        host, port_s = raw.rsplit(",", 1)
        return host.strip(), int(port_s.strip())
    if raw.count(":") == 1 and not raw.startswith("["):
        host, port_s = raw.split(":", 1)
        if port_s.isdigit():
            return host.strip(), int(port_s)
    return raw, 1433


def resolve_odbc_driver(explicit: str) -> str:
    """Pick an installed driver; prefer explicit, then platform-friendly fallbacks."""
    available = _driver_index()
    if not available:
        raise RuntimeError(
            "No ODBC drivers installed. Linux dev: apt install unixodbc freetds-bin tdsodbc "
            "and set REPORTS_DB_DRIVER=FreeTDS in .env"
        )

    requested = (explicit or "").strip()
    if requested:
        key = requested.lower()
        if key in available:
            return available[key]
        for k, canonical in available.items():
            if key in k or k in key:
                logger.warning(
                    "REPORTS_DB_DRIVER=%r matched installed driver %r",
                    explicit,
                    canonical,
                )
                return canonical
        logger.warning(
            "REPORTS_DB_DRIVER=%r not installed (%s); trying fallbacks",
            explicit,
            list(pyodbc.drivers()),
        )

    for name in _PREFERRED_DRIVERS:
        if name.lower() in available:
            if requested and name.lower() != requested.lower():
                logger.info("Using ODBC driver %r for procedure reports", name)
            return available[name.lower()]

    raise RuntimeError(
        f"No SQL Server ODBC driver found (installed: {list(pyodbc.drivers())}). "
        "On Linux set REPORTS_DB_DRIVER=FreeTDS after installing freetds/unixodbc."
    )


def build_reports_connection_string(
    *,
    server: str,
    database: str,
    user: str,
    password: str,
    driver: str,
    tds_version: str = "7.4",
    encrypt: bool = False,
) -> str:
    host, port = parse_reports_server(server)
    resolved = resolve_odbc_driver(driver)

    if resolved.lower() == "freetds":
        # FreeTDS expects SERVER + PORT; comma form (host,1433) breaks on Linux.
        return (
            f"DRIVER={{{resolved}}};"
            f"SERVER={host};"
            f"PORT={port};"
            f"DATABASE={database};"
            f"UID={user};"
            f"PWD={password};"
            f"TDS_Version={tds_version};"
            "ClientCharset=UTF-8;"
        )

    encrypt_flag = "yes" if encrypt else "no"
    return (
        f"DRIVER={{{resolved}}};"
        f"SERVER={host},{port};"
        f"DATABASE={database};"
        f"UID={user};"
        f"PWD={password};"
        "TrustServerCertificate=yes;"
        f"Encrypt={encrypt_flag};"
    )
