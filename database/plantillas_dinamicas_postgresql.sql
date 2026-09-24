-- Plantillas Dinámicas para IDEC (PostgreSQL 14+)
-- Este archivo es una propuesta de migración: NO se ejecuta automáticamente.
-- No crea ni modifica tablas de seguridad/RBAC; IDEC ya administra esos datos.

BEGIN;

CREATE SCHEMA IF NOT EXISTS plantillas_dinamicas;

CREATE TABLE IF NOT EXISTS plantillas_dinamicas.plantilla (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre              varchar(200) NOT NULL,
    codigo              varchar(100) NOT NULL UNIQUE,
    area                varchar(100) NOT NULL,
    tipo_documento      varchar(100) NOT NULL,
    descripcion         varchar(500),
    contenido_html      text NOT NULL,
    version             integer NOT NULL DEFAULT 1 CHECK (version > 0),
    activa              boolean NOT NULL DEFAULT true,
    creado_en           timestamptz NOT NULL DEFAULT now(),
    actualizado_en      timestamptz,
    creado_por          varchar(255),
    actualizado_por     varchar(255)
);

CREATE TABLE IF NOT EXISTS plantillas_dinamicas.variable (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre              varchar(150) NOT NULL,
    clave               varchar(100) NOT NULL UNIQUE,
    descripcion         varchar(500),
    tipo_dato           varchar(50) NOT NULL,
    valor_predeterminado text,
    activa              boolean NOT NULL DEFAULT true,
    creado_en           timestamptz NOT NULL DEFAULT now(),
    actualizado_en      timestamptz,
    CONSTRAINT ck_variable_clave
        CHECK (clave ~ '^[a-zA-Z][a-zA-Z0-9_]*$')
);

-- Variables incluidas en una plantilla. Permite validar qué placeholders puede usar
-- cada formato y preparar formularios dinámicos sin repetir la definición global.
CREATE TABLE IF NOT EXISTS plantillas_dinamicas.plantilla_variable (
    plantilla_id        bigint NOT NULL REFERENCES plantillas_dinamicas.plantilla(id),
    variable_id         bigint NOT NULL REFERENCES plantillas_dinamicas.variable(id),
    etiqueta            varchar(150),
    requerida           boolean NOT NULL DEFAULT false,
    editable            boolean NOT NULL DEFAULT true,
    orden               integer NOT NULL DEFAULT 0,
    PRIMARY KEY (plantilla_id, variable_id)
);

CREATE TABLE IF NOT EXISTS plantillas_dinamicas.cite_configuracion (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    area_codigo         varchar(20) NOT NULL,
    tipo_documento_codigo varchar(20) NOT NULL,
    nombre              varchar(150) NOT NULL,
    formato             varchar(150) NOT NULL,
    longitud_numero     smallint NOT NULL DEFAULT 5 CHECK (longitud_numero BETWEEN 1 AND 12),
    reinicia_por_gestion boolean NOT NULL DEFAULT true,
    activa              boolean NOT NULL DEFAULT true,
    CONSTRAINT uq_cite_configuracion UNIQUE (area_codigo, tipo_documento_codigo)
);

-- Una fila por configuración y gestión. Debe incrementarse dentro de una transacción
-- con SELECT ... FOR UPDATE para no emitir CITES duplicados.
CREATE TABLE IF NOT EXISTS plantillas_dinamicas.cite_correlativo (
    cite_configuracion_id bigint NOT NULL REFERENCES plantillas_dinamicas.cite_configuracion(id),
    gestion             integer NOT NULL CHECK (gestion BETWEEN 2000 AND 9999),
    ultimo_numero       integer NOT NULL DEFAULT 0 CHECK (ultimo_numero >= 0),
    PRIMARY KEY (cite_configuracion_id, gestion)
);

CREATE TABLE IF NOT EXISTS plantillas_dinamicas.documento_generado (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plantilla_id        bigint NOT NULL REFERENCES plantillas_dinamicas.plantilla(id),
    tramite_id          bigint,
    registro_catastral_id bigint,
    predio_id           bigint,
    titulo              varchar(250),
    contenido_html_final text NOT NULL,
    valores             jsonb NOT NULL DEFAULT '{}'::jsonb,
    estado              varchar(30) NOT NULL DEFAULT 'BORRADOR',
    generado_en         timestamptz NOT NULL DEFAULT now(),
    actualizado_en      timestamptz,
    generado_por        varchar(255),
    actualizado_por     varchar(255),
    CONSTRAINT ck_documento_estado CHECK (estado IN ('BORRADOR', 'GENERADO', 'ANULADO'))
);

CREATE TABLE IF NOT EXISTS plantillas_dinamicas.cite_generado (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cite_configuracion_id bigint NOT NULL REFERENCES plantillas_dinamicas.cite_configuracion(id),
    documento_id        bigint UNIQUE REFERENCES plantillas_dinamicas.documento_generado(id),
    gestion             integer NOT NULL CHECK (gestion BETWEEN 2000 AND 9999),
    numero_correlativo  integer NOT NULL CHECK (numero_correlativo > 0),
    codigo              varchar(100) NOT NULL UNIQUE,
    tramite_id          bigint,
    estado              varchar(30) NOT NULL DEFAULT 'GENERADO',
    motivo_anulacion    varchar(500),
    generado_en         timestamptz NOT NULL DEFAULT now(),
    generado_por        varchar(255),
    CONSTRAINT ck_cite_estado CHECK (estado IN ('GENERADO', 'ANULADO')),
    CONSTRAINT uq_cite_numero_por_gestion UNIQUE (cite_configuracion_id, gestion, numero_correlativo)
);

CREATE TABLE IF NOT EXISTS plantillas_dinamicas.historial_documento (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    documento_id        bigint NOT NULL REFERENCES plantillas_dinamicas.documento_generado(id),
    accion              varchar(100) NOT NULL,
    descripcion         varchar(500),
    contenido_anterior  text,
    contenido_nuevo     text,
    realizado_por       varchar(255),
    creado_en           timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_plantilla_activa ON plantillas_dinamicas.plantilla (activa);
CREATE INDEX IF NOT EXISTS ix_documento_plantilla ON plantillas_dinamicas.documento_generado (plantilla_id);
CREATE INDEX IF NOT EXISTS ix_documento_tramite ON plantillas_dinamicas.documento_generado (tramite_id);
CREATE INDEX IF NOT EXISTS ix_cite_documento ON plantillas_dinamicas.cite_generado (documento_id);
CREATE INDEX IF NOT EXISTS ix_historial_documento ON plantillas_dinamicas.historial_documento (documento_id, creado_en DESC);

COMMIT;

-- Permisos a crear en el RBAC existente de IDEC (no se insertan aquí):
-- templates.view, templates.edit
