-- Persistencia de datos revisados para el módulo folder_analysis.
-- Ejecutar en PostgreSQL. Cada fila representa la versión confirmada por el
-- usuario al pulsar "Guardar revisión" en folder_analysis.documents.

CREATE SCHEMA IF NOT EXISTS folder_analysis;

-- Folio Real: valores de la ficha y asientos de titularidad.
CREATE TABLE IF NOT EXISTS folder_analysis.reviewed_folios (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL UNIQUE
        REFERENCES folder_analysis.documents(id) ON DELETE CASCADE,
    user_sub VARCHAR(64) NOT NULL,
    registration_number TEXT,
    registration_status TEXT,
    administrative_location TEXT,
    cadastre TEXT,
    property_type TEXT,
    location TEXT,
    designation TEXT,
    surface TEXT,
    measures TEXT,
    boundaries JSONB NOT NULL DEFAULT '{}'::jsonb,
    property_description TEXT,
    prior_title TEXT,
    document_date TEXT,
    page_number INTEGER,
    page_total INTEGER,
    ownership_entries JSONB NOT NULL DEFAULT '[]'::jsonb,
    reviewed_data JSONB NOT NULL,
    reviewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_reviewed_folios_boundaries_object
        CHECK (jsonb_typeof(boundaries) = 'object'),
    CONSTRAINT ck_reviewed_folios_entries_array
        CHECK (jsonb_typeof(ownership_entries) = 'array'),
    CONSTRAINT ck_reviewed_folios_data_object
        CHECK (jsonb_typeof(reviewed_data) = 'object')
);

CREATE INDEX IF NOT EXISTS ix_reviewed_folios_user_registration
    ON folder_analysis.reviewed_folios (user_sub, registration_number);

-- Comprobantes de pago de impuestos (FUR / IMPBI).
CREATE TABLE IF NOT EXISTS folder_analysis.reviewed_tax_receipts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL UNIQUE
        REFERENCES folder_analysis.documents(id) ON DELETE CASCADE,
    user_sub VARCHAR(64) NOT NULL,
    receipt_type TEXT,
    receipt_number TEXT,
    municipality TEXT,
    paid_at TEXT,
    collecting_entity TEXT,
    correspondent TEXT,
    branch TEXT,
    agency TEXT,
    cashier TEXT,
    folio TEXT,
    concept TEXT,
    tax_year INTEGER,
    taxpayer_type TEXT,
    taxpayer_id_number TEXT,
    taxpayer_name TEXT,
    property_number TEXT,
    cadastral_code TEXT,
    property_class TEXT,
    ownership_type TEXT,
    location TEXT,
    land_area TEXT,
    built_area TEXT,
    age_factor TEXT,
    ufv TEXT,
    taxable_base TEXT,
    assessed_tax TEXT,
    exemption TEXT,
    discount_10 TEXT,
    discount_app_5 TEXT,
    amount_due TEXT,
    amount_paid TEXT,
    balance TEXT,
    reviewed_data JSONB NOT NULL,
    reviewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_reviewed_tax_receipts_data_object
        CHECK (jsonb_typeof(reviewed_data) = 'object')
);

CREATE INDEX IF NOT EXISTS ix_reviewed_tax_receipts_user_property
    ON folder_analysis.reviewed_tax_receipts (user_sub, property_number);
CREATE INDEX IF NOT EXISTS ix_reviewed_tax_receipts_cadastral_code
    ON folder_analysis.reviewed_tax_receipts (cadastral_code);

-- Planos: el extractor puede devolver estructuras variables según el plano;
-- JSONB conserva campos, tablas y resultados revisados sin perder información.
CREATE TABLE IF NOT EXISTS folder_analysis.reviewed_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL UNIQUE
        REFERENCES folder_analysis.documents(id) ON DELETE CASCADE,
    user_sub VARCHAR(64) NOT NULL,
    plan_name TEXT,
    plan_type TEXT,
    address TEXT,
    cadastral_code TEXT,
    scale TEXT,
    plan_date TEXT,
    extracted_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    reviewed_data JSONB NOT NULL,
    reviewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_reviewed_plans_extracted_object
        CHECK (jsonb_typeof(extracted_data) = 'object'),
    CONSTRAINT ck_reviewed_plans_data_object
        CHECK (jsonb_typeof(reviewed_data) = 'object')
);

CREATE INDEX IF NOT EXISTS ix_reviewed_plans_user_cadastral_code
    ON folder_analysis.reviewed_plans (user_sub, cadastral_code);

COMMENT ON TABLE folder_analysis.reviewed_folios IS
    'Datos de Folio Real confirmados por el usuario; document_id apunta al documento fuente.';
COMMENT ON TABLE folder_analysis.reviewed_tax_receipts IS
    'Datos de comprobantes de impuestos confirmados por el usuario; document_id apunta al documento fuente.';
COMMENT ON TABLE folder_analysis.reviewed_plans IS
    'Datos de planos confirmados por el usuario; JSONB conserva la estructura variable del extractor.';
