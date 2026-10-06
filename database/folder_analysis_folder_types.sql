-- Tipos de carpeta en folder_analysis: cada carpeta registrada pasa a tener un
-- tipo de trámite (el catálogo vive en
-- app/domains/folder_analysis/domain/folder_types.py) y una hoja de datos
-- propia. El tipo es el que manda qué documentos lleva la carpeta y qué campos
-- se extraen de cada uno.
--
-- Ejecutar en PostgreSQL. Requiere folder_analysis.registered_folders (ver
-- folder_analysis_registered_folders.sql). La aplicación también agrega estas
-- columnas al arrancar (app/domains/folder_analysis/infrastructure/models.py);
-- este script existe para aplicarlas a mano en un entorno ya desplegado.

-- Las carpetas que ya existían no tenían tipo: quedan como 'general', que es el
-- tablero de siempre (folio, impuesto y plano), así que nada deja de abrirse.
ALTER TABLE folder_analysis.registered_folders
    ADD COLUMN IF NOT EXISTS folder_type VARCHAR(40) NOT NULL DEFAULT 'general';

-- La hoja propia de la carpeta, con las claves de campo que declara su tipo.
-- Lo que no es campo de ese tipo no se guarda: el catálogo es la verdad.
ALTER TABLE folder_analysis.registered_folders
    ADD COLUMN IF NOT EXISTS data JSONB NOT NULL DEFAULT '{}'::jsonb;

-- El documento también lleva bajo qué tipo de carpeta se clasificó: es lo que
-- decide qué campos se le sacan al analizarlo, y hace falta en el documento y no
-- solo en la carpeta porque en el tablero suelto se elige el tipo sin abrir
-- ninguna carpeta. Los documentos anteriores quedan en NULL, que se lee como el
-- tipo 'general'.
ALTER TABLE folder_analysis.documents
    ADD COLUMN IF NOT EXISTS folder_type VARCHAR(40);

COMMENT ON COLUMN folder_analysis.documents.folder_type IS
    'Tipo de carpeta bajo el que se clasificó el documento; manda qué datos se le extraen.';

COMMENT ON COLUMN folder_analysis.registered_folders.folder_type IS
    'Tipo de carpeta (trámite) del catálogo: manda qué documentos lleva y qué campos tiene.';
COMMENT ON COLUMN folder_analysis.registered_folders.data IS
    'Hoja propia de la carpeta: clave de campo del tipo -> valor cargado.';

-- No hace falta tocar registered_folder_items: en qué carpeta está un documento
-- se sigue guardando ahí y en ningún otro lado. Lo que cambia es cuándo entra --
-- un documento abierto dentro de una carpeta se archiva en ella desde que se
-- crea, en borrador, y ya no solo cuando se guarda su revisión.
