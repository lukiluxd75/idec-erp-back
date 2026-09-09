"""
Script manual para verificar/crear las tablas de PostgreSQL a partir de los modelos ORM.
Usa la misma función que corre automáticamente al levantar la app (ver
app/core/database/connection.py::init_db_tables) — no se duplica la lógica acá.

En la práctica esto no debería crear tablas nuevas: el esquema real ya existe, creado con
SQL puro por el equipo de base de datos (ver ecosistema_seguridad_backup.sql en la raíz
del repo). Esto sirve solo de red de seguridad para un entorno local vacío.
"""
from app.core.config import settings
from app.core.database.connection import init_db_tables


if __name__ == "__main__":
    print(f"[*] Conectando a PostgreSQL: {settings.SQLALCHEMY_DATABASE_URI}")
    ok = init_db_tables()
    if ok:
        print("[+] ¡Tablas creadas/verificadas exitosamente en PostgreSQL!")
    else:
        print("[-] Hubo un problema al inicializar la base de datos (ver advertencia arriba).")
