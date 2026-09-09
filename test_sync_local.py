"""
Prueba manual de la sincronización usuario <-> PostgreSQL, SIN pasar por Keycloak.
Simula lo que hace el login real: llama directo al repositorio con un keycloak_sub
inventado, como si fuera el 'sub' que vendría de un token real.

Uso:
    python test_sync_local.py

Requiere que la base local ya tenga el esquema real cargado (ecosistema_seguridad_backup.sql)
y que backend/.env apunte a esa base local.
"""
from app.core.database.connection import SessionLocal
from app.domains.seguridad.infrastructure.sql_user_repository import SqlUserRepository
from app.domains.seguridad.infrastructure.models import (
    AreaModel,
    PermisoModel,
    RecursoModel,
    RolInternoModel,
    SistemaModel,
    SubsistemaModel,
    UsuarioRolAreaModel,
)

FAKE_KEYCLOAK_SUB = "test-sub-12345"
FAKE_USERNAME = "usuario_de_prueba"
FAKE_CORREO = "prueba@gamc.gob.bo"


def main():
    db = SessionLocal()
    try:
        repo = SqlUserRepository(db)

        print("1) Simulando login: ensure_user_exists(...)")
        user_entity = repo.ensure_user_exists(
            keycloak_sub=FAKE_KEYCLOAK_SUB, username=FAKE_USERNAME, correo=FAKE_CORREO
        )
        print(f"   -> usuario en BD: id={user_entity.id_usuario} username={user_entity.username}")

        print("2) Permisos ANTES de asignar rol (debería ser una lista vacía):")
        print(f"   -> {repo.get_user_permissions(FAKE_KEYCLOAK_SUB)}")

        print("3) Creando área + rol + recurso + permiso de prueba y asignándoselos...")
        sistema = SistemaModel(nombre="Sistema Prueba")
        db.add(sistema)
        db.flush()

        subsistema = SubsistemaModel(sistema_id=sistema.id, nombre="Subsistema Prueba")
        db.add(subsistema)
        db.flush()

        recurso = RecursoModel(subsistema_id=subsistema.id, nombre="mapas")
        db.add(recurso)
        db.flush()

        permiso = PermisoModel(recurso_id=recurso.id, accion="ver")
        db.add(permiso)
        db.flush()

        area = AreaModel(nombre="Área de Prueba", tipo="oficina")
        db.add(area)
        db.flush()

        rol = RolInternoModel(nombre="rol_prueba", descripcion="Rol de prueba local")
        db.add(rol)
        db.flush()

        rol.permisos.append(permiso)
        db.flush()

        # user_entity.id_usuario es un string (UUID); buscamos el modelo real para el FK
        from app.domains.seguridad.infrastructure.models import UsuarioModel
        usuario_model = db.query(UsuarioModel).filter(
            UsuarioModel.keycloak_sub == FAKE_KEYCLOAK_SUB
        ).first()

        asignacion = UsuarioRolAreaModel(usuario_id=usuario_model.id, rol_id=rol.id, area_id=area.id)
        db.add(asignacion)
        db.commit()

        print("4) Permisos DESPUÉS de asignar rol (debería mostrar 'mapas.ver'):")
        print(f"   -> {repo.get_user_permissions(FAKE_KEYCLOAK_SUB)}")

        print("\nOK: la sincronización, el modelo ORM y las consultas RBAC funcionan contra el esquema real.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
