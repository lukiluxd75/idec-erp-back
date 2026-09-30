-- Carpetas registradas del módulo folder_analysis: submódulo de "Datos
-- guardados" donde el usuario agrupa por proyecto los documentos ya
-- solucionados (folios, comprobantes de impuestos y planos) bajo el nombre de
-- carpeta que él mismo escribe.
--
-- Ejecutar en PostgreSQL. Requiere folder_analysis.documents (ver
-- folder_analysis_reviewed_data.sql). La aplicación también crea estas tablas
-- al arrancar (app/domains/folder_analysis/presentation/router.py); este script
-- existe para aplicarlas a mano en un entorno ya desplegado.

CREATE SCHEMA IF NOT EXISTS folder_analysis;

-- Una carpeta = un proyecto. El nombre es lo que el usuario reconoce, así que
-- es obligatorio y único por usuario sin distinguir mayúsculas: dos carpetas
-- llamadas igual serían indistinguibles en la lista.
CREATE TABLE IF NOT EXISTS folder_analysis.registered_folders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_sub VARCHAR(64) NOT NULL,
    name VARCHAR(120) NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_folder_analysis_registered_folders_user_name
    ON folder_analysis.registered_folders (user_sub, lower(name));

CREATE INDEX IF NOT EXISTS ix_folder_analysis_registered_folders_user
    ON folder_analysis.registered_folders (user_sub, name);

-- Cada documento guardado que se archiva en una carpeta. document_id es único
-- en toda la tabla, no solo dentro de la carpeta: un documento se archiva en una
-- sola carpeta, igual que la hoja de la que salió está en un solo folder.
-- Si el documento se elimina (sus fotos vuelven a "Fotos recibidas"), su fila
-- aquí se va con él; borrar la carpeta no toca los documentos.
CREATE TABLE IF NOT EXISTS folder_analysis.registered_folder_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    folder_id UUID NOT NULL
        REFERENCES folder_analysis.registered_folders(id) ON DELETE CASCADE,
    document_id UUID NOT NULL UNIQUE
        REFERENCES folder_analysis.documents(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_registered_folder_items_folder_position
        UNIQUE (folder_id, position)
);

COMMENT ON TABLE folder_analysis.registered_folders IS
    'Carpetas registradas: agrupan por proyecto los documentos revisados del usuario.';
COMMENT ON TABLE folder_analysis.registered_folder_items IS
    'Documentos revisados archivados en una carpeta; position guarda el orden de archivo.';
