#!/usr/bin/env python3
"""
Applies database/plantillas_dinamicas_postgresql.sql against the DB configured
in .env (same engine app.main uses -- see app/core/database/connection.py).

Idempotent (the SQL uses CREATE SCHEMA/TABLE IF NOT EXISTS): safe to re-run.
Run this once per environment, then scripts/bootstrap_templates_permissions.py
to grant templates.view/templates.edit to existing roles.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from app.core.config import settings
from app.core.database.connection import engine


def main() -> None:
    print(f"Connecting to {settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME} ...")

    with engine.connect() as conn:
        existing = conn.execute(
            text(
                "SELECT schema_name FROM information_schema.schemata "
                "WHERE schema_name = 'templates'"
            )
        ).fetchone()
        print(f"Schema 'templates' exists before running migration: {bool(existing)}")

    sql_path = ROOT / "database" / "plantillas_dinamicas_postgresql.sql"
    sql_text = sql_path.read_text(encoding="utf-8")

    raw_conn = engine.raw_connection()
    try:
        cur = raw_conn.cursor()
        cur.execute(sql_text)
        raw_conn.commit()
        print("Migration executed and committed OK.")
    finally:
        raw_conn.close()

    with engine.connect() as conn:
        tables = conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'templates' ORDER BY table_name"
            )
        ).fetchall()
        print("Tables now in templates schema:")
        for (t,) in tables:
            print(" -", t)


if __name__ == "__main__":
    main()
