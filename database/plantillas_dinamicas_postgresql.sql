-- Plantillas Dinámicas para IDEC (PostgreSQL 14+)
-- Este archivo es una propuesta de migración: NO se ejecuta automáticamente.
-- No crea ni modifica tablas de seguridad/RBAC; IDEC ya administra esos datos.

BEGIN;

CREATE SCHEMA IF NOT EXISTS templates;

CREATE TABLE IF NOT EXISTS templates.templates (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name                varchar(200) NOT NULL,
    code                varchar(100) NOT NULL UNIQUE,
    area                varchar(100) NOT NULL,
    document_type       varchar(100) NOT NULL,
    description         varchar(500),
    html_content        text NOT NULL,
    version             integer NOT NULL DEFAULT 1 CHECK (version > 0),
    is_active           boolean NOT NULL DEFAULT true,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz,
    created_by          varchar(255),
    updated_by          varchar(255)
);

CREATE TABLE IF NOT EXISTS templates.variables (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name                varchar(150) NOT NULL,
    key                 varchar(100) NOT NULL UNIQUE,
    description         varchar(500),
    data_type           varchar(50) NOT NULL,
    default_value       text,
    is_active           boolean NOT NULL DEFAULT true,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz,
    CONSTRAINT ck_variable_clave
        CHECK (clave ~ '^[a-zA-Z][a-zA-Z0-9_]*$')
);

-- Variables incluidas en una plantilla. Permite validar qué placeholders puede usar
-- cada formato y preparar formularios dinámicos sin repetir la definición global.
CREATE TABLE IF NOT EXISTS templates.templates_variable (
    template_id         bigint NOT NULL REFERENCES templates.templates(id),
    variable_id         bigint NOT NULL REFERENCES templates.variables(id),
    label               varchar(150),
    is_required         boolean NOT NULL DEFAULT false,
    is_editable         boolean NOT NULL DEFAULT true,
    order_index         integer NOT NULL DEFAULT 0,
    PRIMARY KEY (template_id, variable_id)
);

CREATE TABLE IF NOT EXISTS templates.cite_configurations (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    area_code           varchar(20) NOT NULL,
    document_type_code  varchar(20) NOT NULL,
    name                varchar(150) NOT NULL,
    format              varchar(150) NOT NULL,
    number_length       smallint NOT NULL DEFAULT 5 CHECK (longitud_numero BETWEEN 1 AND 12),
    resets_per_year     boolean NOT NULL DEFAULT true,
    is_active           boolean NOT NULL DEFAULT true,
    CONSTRAINT uq_cite_configuracion UNIQUE (area_code, document_type_code)
);

-- Una fila por configuración y gestión. Debe incrementarse dentro de una transacción
-- con SELECT ... FOR UPDATE para no emitir CITES duplicados.
CREATE TABLE IF NOT EXISTS templates.cite_counters (
    cite_configuration_id bigint NOT NULL REFERENCES templates.cite_configurations(id),
    year                integer NOT NULL CHECK (year BETWEEN 2000 AND 9999),
    last_number         integer NOT NULL DEFAULT 0 CHECK (last_number >= 0),
    PRIMARY KEY (cite_configuration_id, year)
);

CREATE TABLE IF NOT EXISTS templates.generated_documents (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    template_id         bigint NOT NULL REFERENCES templates.templates(id),
    procedure_id        bigint,
    cadastral_record_id bigint,
    property_id         bigint,
    title               varchar(250),
    final_html_content  text NOT NULL,
    values_json         jsonb NOT NULL DEFAULT '{}'::jsonb,
    status              varchar(30) NOT NULL DEFAULT 'BORRADOR',
    generated_at        timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz,
    generated_by        varchar(255),
    updated_by          varchar(255),
    CONSTRAINT ck_documento_estado CHECK (estado IN ('BORRADOR', 'GENERADO', 'ANULADO'))
);

CREATE TABLE IF NOT EXISTS templates.generated_cites (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cite_configuration_id bigint NOT NULL REFERENCES templates.cite_configurations(id),
    documento_id        bigint UNIQUE REFERENCES templates.generated_documents(id),
    year                integer NOT NULL CHECK (year BETWEEN 2000 AND 9999),
    correlative_number  integer NOT NULL CHECK (correlative_number > 0),
    code                varchar(100) NOT NULL UNIQUE,
    procedure_id        bigint,
    status              varchar(30) NOT NULL DEFAULT 'GENERADO',
    cancellation_reason varchar(500),
    generated_at        timestamptz NOT NULL DEFAULT now(),
    generated_by        varchar(255),
    CONSTRAINT ck_cite_estado CHECK (estado IN ('GENERADO', 'ANULADO')),
    CONSTRAINT uq_cite_numero_por_gestion UNIQUE (cite_configuration_id, year, correlative_number)
);

CREATE TABLE IF NOT EXISTS templates.document_history (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    documento_id        bigint NOT NULL REFERENCES templates.generated_documents(id),
    action              varchar(100) NOT NULL,
    description         varchar(500),
    previous_content    text,
    new_content         text,
    performed_by        varchar(255),
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_plantilla_activa ON templates.templates (is_active);
CREATE INDEX IF NOT EXISTS ix_documento_plantilla ON templates.generated_documents (template_id);
CREATE INDEX IF NOT EXISTS ix_documento_tramite ON templates.generated_documents (procedure_id);
CREATE INDEX IF NOT EXISTS ix_cite_documento ON templates.generated_cites (documento_id);
CREATE INDEX IF NOT EXISTS ix_historial_documento ON templates.document_history (documento_id, creado_en DESC);

COMMIT;

-- Permisos a crear en el RBAC existente de IDEC (no se insertan aquí):
-- templates.view, templates.edit
