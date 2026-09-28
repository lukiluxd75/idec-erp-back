-- =============================================================================
-- Esquema: detection_results (v5)
-- Cambios sobre la versión anterior, tras revisión con el ingeniero:
--   - Se retira el trigger de auto-cierre: la transición de estado del sector
--     la decide el backend explícitamente (mismo patrón que usa idec_erp.job).
--   - Se retira processed_sector.n_reviewed_parcels: se calcula al vuelo con
--     un COUNT() cuando haga falta, no se persiste.
--   - campaign ya no guarda year_a/year_b: una campaña puede agrupar sectores
--     con distintos pares de años (ej. 2023-2024 y 2010-2023 en el mismo
--     trimestre); el año vive únicamente en processed_sector.
--   - Nueva tabla model_feedback: captura falsos positivos/negativos que el
--     arquitecto identifica, para retroalimentar el reentrenamiento del
--     modelo. Separada de architect_review a propósito (ver documentación).
-- Motor: PostgreSQL 14+ con PostGIS.
--
-- Parche 2026-09-17 (aplicado, ver scripts/migrate_detection_results_created_by_to_uuid.sql):
--   - campaign.created_by, processed_sector.created_by/updated_by,
--     affected_parcel.validated_by, architect_review.created_by y
--     model_feedback.created_by pasan de BIGINT a UUID con FK real a
--     public.users(id) — el identificador interno de usuario del ERP es UUID
--     (ver security/infrastructure/models.py), no BIGINT; el comentario
--     "pendiente: FK real al autenticador del ERP" de la v5 original queda
--     resuelto.
-- =============================================================================

DROP SCHEMA IF EXISTS detection_results CASCADE;
CREATE SCHEMA detection_results AUTHORIZATION "UserCatBD";


-- -----------------------------------------------------------------------------
-- campaign — agrupa sectores procesados de un periodo (ej. un trimestre)
-- -----------------------------------------------------------------------------
CREATE TABLE detection_results.campaign (
    id                   BIGSERIAL,
    code                 VARCHAR(30) NOT NULL,
    name                 VARCHAR(150) NOT NULL,
    description          TEXT,
    period_start         DATE,
    period_end           DATE,
    status               VARCHAR(20) NOT NULL DEFAULT 'active',
    n_sectors            INTEGER NOT NULL DEFAULT 0,
    n_affected_parcels   INTEGER NOT NULL DEFAULT 0,
    created_by           UUID,  -- FK a public.users(id); ver migración 2026-09-17
    created_at           TIMESTAMP NOT NULL DEFAULT now(),
    closed_at            TIMESTAMP,
    CONSTRAINT pk_campaign PRIMARY KEY (id),
    CONSTRAINT uq_campaign_code UNIQUE (code),
    CONSTRAINT ck_campaign_status CHECK (status IN ('draft','active','closed')),
    CONSTRAINT fk_campaign_created_by FOREIGN KEY (created_by)
        REFERENCES public.users(id)
);


-- -----------------------------------------------------------------------------
-- processed_sector
-- -----------------------------------------------------------------------------
CREATE TABLE detection_results.processed_sector (
    id                   BIGSERIAL,
    campaign_id          BIGINT,  -- nullable por ahora: hay sectores de prueba sin campaña
    name                 VARCHAR(150),
    geom                 GEOMETRY(POLYGON, 4326) NOT NULL,
    year_a               INTEGER NOT NULL,
    year_b               INTEGER NOT NULL,
    status               VARCHAR(25) NOT NULL DEFAULT 'pending',
    progress_pct         SMALLINT NOT NULL DEFAULT 0,
    has_changes          BOOLEAN,
    n_affected_parcels   INTEGER NOT NULL DEFAULT 0,
    n_new_parcels        INTEGER NOT NULL DEFAULT 0,
    n_removed_parcels    INTEGER NOT NULL DEFAULT 0,
    n_changed_parcels    INTEGER NOT NULL DEFAULT 0,
    created_by           UUID,  -- FK a public.users(id); ver migración 2026-09-17
    created_at           TIMESTAMP NOT NULL DEFAULT now(),
    updated_by           UUID,  -- FK a public.users(id); ver migración 2026-09-17
    updated_at           TIMESTAMP NOT NULL DEFAULT now(),
    processed_at         TIMESTAMP,
    deleted_at           TIMESTAMP,
    CONSTRAINT pk_processed_sector PRIMARY KEY (id),
    CONSTRAINT fk_processed_sector_created_by FOREIGN KEY (created_by)
        REFERENCES public.users(id),
    CONSTRAINT fk_processed_sector_updated_by FOREIGN KEY (updated_by)
        REFERENCES public.users(id),
    CONSTRAINT fk_processed_sector_campaign FOREIGN KEY (campaign_id)
        REFERENCES detection_results.campaign(id),
    CONSTRAINT ck_processed_sector_status CHECK (status IN ('pending','aligning',
        'removing_shadows','detecting','awaiting_manual_alignment',
        'awaiting_validation','completed','error')),
    CONSTRAINT ck_processed_sector_progress_pct CHECK (progress_pct BETWEEN 0 AND 100),
    CONSTRAINT ck_processed_sector_geom_valid CHECK (ST_IsValid(geom))
);

CREATE INDEX ix_processed_sector_geom ON detection_results.processed_sector USING GIST (geom);
CREATE INDEX ix_processed_sector_campaign_id ON detection_results.processed_sector(campaign_id);


-- -----------------------------------------------------------------------------
-- alignment
-- -----------------------------------------------------------------------------
CREATE TABLE detection_results.alignment (
    id                    BIGSERIAL,
    processed_sector_id   BIGINT NOT NULL,
    method                VARCHAR(20) NOT NULL,
    cc                    NUMERIC(5,4),
    residual_m            NUMERIC(6,2),
    threshold_used        NUMERIC(5,4) NOT NULL DEFAULT 0.75,
    gcp_method            VARCHAR(20),
    base_image_source     VARCHAR(20),
    quality_level         VARCHAR(10),
    is_accepted           BOOLEAN NOT NULL DEFAULT false,
    warp_matrix           JSONB,
    created_at            TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT pk_alignment PRIMARY KEY (id),
    CONSTRAINT fk_alignment_processed_sector FOREIGN KEY (processed_sector_id)
        REFERENCES detection_results.processed_sector(id) ON DELETE CASCADE,
    CONSTRAINT ck_alignment_method CHECK (method IN ('auto_ecc','manual_gcp')),
    CONSTRAINT ck_alignment_gcp_method CHECK (gcp_method IN ('affine','homography')),
    CONSTRAINT ck_alignment_base_image_source CHECK (base_image_source IN ('job_ortho','live_wms')),
    CONSTRAINT ck_alignment_quality_level CHECK (quality_level IN ('good','warn','poor','bad','manual'))
);

CREATE INDEX ix_alignment_processed_sector_id ON detection_results.alignment(processed_sector_id);


-- -----------------------------------------------------------------------------
-- control_point
-- -----------------------------------------------------------------------------
CREATE TABLE detection_results.control_point (
    id             BIGSERIAL,
    alignment_id   BIGINT NOT NULL,
    order_index    SMALLINT NOT NULL,
    x_ref          NUMERIC NOT NULL,
    y_ref          NUMERIC NOT NULL,
    x_mov          NUMERIC NOT NULL,
    y_mov          NUMERIC NOT NULL,
    CONSTRAINT pk_control_point PRIMARY KEY (id),
    CONSTRAINT fk_control_point_alignment FOREIGN KEY (alignment_id)
        REFERENCES detection_results.alignment(id) ON DELETE CASCADE
);

CREATE INDEX ix_control_point_alignment_id ON detection_results.control_point(alignment_id);


-- -----------------------------------------------------------------------------
-- shadow_removal
-- -----------------------------------------------------------------------------
CREATE TABLE detection_results.shadow_removal (
    id                    BIGSERIAL,
    processed_sector_id   BIGINT NOT NULL,
    image                 CHAR(1) NOT NULL,
    shadow_pct            NUMERIC(5,2),
    mask_path             TEXT NOT NULL,
    original_path         TEXT NOT NULL,
    deshadowed_path       TEXT NOT NULL,
    created_at            TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT pk_shadow_removal PRIMARY KEY (id),
    CONSTRAINT fk_shadow_removal_processed_sector FOREIGN KEY (processed_sector_id)
        REFERENCES detection_results.processed_sector(id) ON DELETE CASCADE,
    CONSTRAINT ck_shadow_removal_image CHECK (image IN ('a','b')),
    CONSTRAINT uq_shadow_removal_processed_sector_id_image UNIQUE (processed_sector_id, image)
);


-- -----------------------------------------------------------------------------
-- processing_run
-- -----------------------------------------------------------------------------
CREATE TABLE detection_results.processing_run (
    id                    BIGSERIAL,
    processed_sector_id   BIGINT NOT NULL,
    alignment_id          BIGINT,
    params                JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at            TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT pk_processing_run PRIMARY KEY (id),
    CONSTRAINT fk_processing_run_processed_sector FOREIGN KEY (processed_sector_id)
        REFERENCES detection_results.processed_sector(id) ON DELETE CASCADE,
    CONSTRAINT fk_processing_run_alignment FOREIGN KEY (alignment_id)
        REFERENCES detection_results.alignment(id)
);

CREATE INDEX ix_processing_run_processed_sector_id ON detection_results.processing_run(processed_sector_id);


-- -----------------------------------------------------------------------------
-- detection
-- -----------------------------------------------------------------------------
CREATE TABLE detection_results.detection (
    id                      BIGSERIAL,
    processed_sector_id     BIGINT NOT NULL,
    processing_run_id       BIGINT,
    type                    VARCHAR(20) NOT NULL,
    geom                    GEOMETRY(POLYGON, 4326) NOT NULL,
    probability             NUMERIC(5,4),
    area_m2                 NUMERIC,
    is_included_in_report   BOOLEAN NOT NULL DEFAULT true,
    reject_reason           VARCHAR(30),
    created_at              TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT pk_detection PRIMARY KEY (id),
    CONSTRAINT fk_detection_processed_sector FOREIGN KEY (processed_sector_id)
        REFERENCES detection_results.processed_sector(id) ON DELETE CASCADE,
    CONSTRAINT fk_detection_processing_run FOREIGN KEY (processing_run_id)
        REFERENCES detection_results.processing_run(id),
    CONSTRAINT ck_detection_type CHECK (type IN ('new','removed','changed','unchanged')),
    CONSTRAINT ck_detection_reject_reason CHECK (reject_reason IN ('low_probability','outside_polygon','other')),
    CONSTRAINT ck_detection_geom_valid CHECK (ST_IsValid(geom))
);

CREATE INDEX ix_detection_processed_sector_id ON detection_results.detection(processed_sector_id);
CREATE INDEX ix_detection_geom ON detection_results.detection USING GIST (geom);


-- -----------------------------------------------------------------------------
-- affected_parcel — tabla de valor real
-- -----------------------------------------------------------------------------
CREATE TABLE detection_results.affected_parcel (
    id                     BIGSERIAL,
    processed_sector_id    BIGINT NOT NULL,
    detection_id           BIGINT,
    cadastral_code         VARCHAR(30),
    block_code             VARCHAR(30),
    parcel_geom            GEOMETRY(MULTIPOLYGON, 4326),
    match_confidence       VARCHAR(10),
    match_distance_m       NUMERIC(6,2),
    no_match_reason        VARCHAR(30),
    change_type            VARCHAR(20) NOT NULL,
    construction_type      VARCHAR(30),
    validation_status      VARCHAR(20) NOT NULL DEFAULT 'pending',
    validated_by           UUID,  -- FK a public.users(id); ver migración 2026-09-17
    validated_at           TIMESTAMP,
    created_at             TIMESTAMP NOT NULL DEFAULT now(),
    updated_at             TIMESTAMP NOT NULL DEFAULT now(),
    deleted_at             TIMESTAMP,
    CONSTRAINT pk_affected_parcel PRIMARY KEY (id),
    CONSTRAINT fk_affected_parcel_validated_by FOREIGN KEY (validated_by)
        REFERENCES public.users(id),
    CONSTRAINT fk_affected_parcel_processed_sector FOREIGN KEY (processed_sector_id)
        REFERENCES detection_results.processed_sector(id) ON DELETE CASCADE,
    CONSTRAINT fk_affected_parcel_detection FOREIGN KEY (detection_id)
        REFERENCES detection_results.detection(id) ON DELETE SET NULL,
    CONSTRAINT ck_affected_parcel_match_confidence CHECK (match_confidence IN ('high','medium','low')),
    CONSTRAINT ck_affected_parcel_no_match_reason CHECK (no_match_reason IN ('no_layer','outside_buffer','arcgis_error')),
    CONSTRAINT ck_affected_parcel_change_type CHECK (change_type IN ('new','removed','modified','unchanged')),
    CONSTRAINT ck_affected_parcel_validation_status CHECK (validation_status IN ('pending','confirmed','rejected','uncertain')),
    CONSTRAINT ck_affected_parcel_geom_valid CHECK (parcel_geom IS NULL OR ST_IsValid(parcel_geom)),
    CONSTRAINT ck_affected_parcel_cadastral_code_or_reason CHECK (cadastral_code IS NOT NULL OR no_match_reason IS NOT NULL)
);

CREATE INDEX ix_affected_parcel_processed_sector_id ON detection_results.affected_parcel(processed_sector_id);
CREATE INDEX ix_affected_parcel_cadastral_code ON detection_results.affected_parcel(cadastral_code);
CREATE INDEX ix_affected_parcel_parcel_geom ON detection_results.affected_parcel USING GIST (parcel_geom);


-- -----------------------------------------------------------------------------
-- sector_artifact
-- -----------------------------------------------------------------------------
CREATE TABLE detection_results.sector_artifact (
    id                    BIGSERIAL,
    processed_sector_id   BIGINT NOT NULL,
    processing_run_id     BIGINT,
    kind                  VARCHAR(30) NOT NULL,
    path                  TEXT NOT NULL,
    created_at            TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT pk_sector_artifact PRIMARY KEY (id),
    CONSTRAINT fk_sector_artifact_processed_sector FOREIGN KEY (processed_sector_id)
        REFERENCES detection_results.processed_sector(id) ON DELETE CASCADE,
    CONSTRAINT fk_sector_artifact_processing_run FOREIGN KEY (processing_run_id)
        REFERENCES detection_results.processing_run(id),
    CONSTRAINT ck_sector_artifact_kind CHECK (kind IN ('aligned_a','aligned_b','checkerboard','result_panel','other'))
);

CREATE INDEX ix_sector_artifact_processed_sector_id ON detection_results.sector_artifact(processed_sector_id);


-- -----------------------------------------------------------------------------
-- architect_review — decisión catastral/fiscal sobre un predio
-- -----------------------------------------------------------------------------
CREATE TABLE detection_results.architect_review (
    id                   BIGSERIAL,
    affected_parcel_id   BIGINT NOT NULL,
    action               VARCHAR(20) NOT NULL,
    comment              TEXT,
    created_by           UUID,  -- FK a public.users(id); ver migración 2026-09-17
    created_at           TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT pk_architect_review PRIMARY KEY (id),
    CONSTRAINT fk_architect_review_created_by FOREIGN KEY (created_by)
        REFERENCES public.users(id),
    CONSTRAINT fk_architect_review_affected_parcel FOREIGN KEY (affected_parcel_id)
        REFERENCES detection_results.affected_parcel(id) ON DELETE CASCADE,
    CONSTRAINT ck_architect_review_action CHECK (action IN (
        'confirm','reject','mark_uncertain','add_manual','flag_for_retraining'
    ))
);

CREATE INDEX ix_architect_review_affected_parcel_id ON detection_results.architect_review(affected_parcel_id);


-- -----------------------------------------------------------------------------
-- model_feedback — retroalimentación técnica para reentrenar el modelo
-- Separada de architect_review a propósito: distinto público (equipo de ML,
-- no auditoría fiscal), distinto ciclo de vida (export_status propio), y
-- taxonomía de "reason" que evoluciona independiente de las acciones
-- catastrales. architect_review_id es opcional: puede originarse en el mismo
-- clic que una revisión, o reportarse por separado más adelante.
-- -----------------------------------------------------------------------------
CREATE TABLE detection_results.model_feedback (
    id                     BIGSERIAL,
    affected_parcel_id     BIGINT NOT NULL,
    architect_review_id    BIGINT,
    reason                 VARCHAR(30) NOT NULL,
    technical_note         TEXT,
    chip_a_path            TEXT,  -- nullable: mecanismo de recorte aún no definido
    chip_b_path            TEXT,
    chip_mask_path         TEXT,
    export_status          VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_by             UUID,  -- FK a public.users(id); ver migración 2026-09-17
    created_at             TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT pk_model_feedback PRIMARY KEY (id),
    CONSTRAINT fk_model_feedback_created_by FOREIGN KEY (created_by)
        REFERENCES public.users(id),
    CONSTRAINT fk_model_feedback_affected_parcel FOREIGN KEY (affected_parcel_id)
        REFERENCES detection_results.affected_parcel(id) ON DELETE CASCADE,
    CONSTRAINT fk_model_feedback_architect_review FOREIGN KEY (architect_review_id)
        REFERENCES detection_results.architect_review(id),
    CONSTRAINT ck_model_feedback_reason CHECK (reason IN (
        'false_positive_angle','false_positive_shadow','false_positive_other',
        'false_negative','other'
    )),
    CONSTRAINT ck_model_feedback_export_status CHECK (export_status IN ('pending','exported','discarded'))
);

CREATE INDEX ix_model_feedback_affected_parcel_id ON detection_results.model_feedback(affected_parcel_id);


-- -----------------------------------------------------------------------------
-- processing_history
-- -----------------------------------------------------------------------------
CREATE TABLE detection_results.processing_history (
    id                    BIGSERIAL,
    processed_sector_id   BIGINT NOT NULL,
    stage                 VARCHAR(20) NOT NULL,
    status                VARCHAR(10) NOT NULL,
    message               TEXT,
    duration_seconds      NUMERIC,
    created_at            TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT pk_processing_history PRIMARY KEY (id),
    CONSTRAINT fk_processing_history_processed_sector FOREIGN KEY (processed_sector_id)
        REFERENCES detection_results.processed_sector(id) ON DELETE CASCADE,
    CONSTRAINT ck_processing_history_stage CHECK (stage IN ('alignment','shadows','detection')),
    CONSTRAINT ck_processing_history_status CHECK (status IN ('ok','error'))
);

CREATE INDEX ix_processing_history_processed_sector_id ON detection_results.processing_history(processed_sector_id);


-- -----------------------------------------------------------------------------
-- module_parameter
-- -----------------------------------------------------------------------------
CREATE TABLE detection_results.module_parameter (
    id            BIGSERIAL,
    param_key     VARCHAR(50) NOT NULL,
    value         TEXT NOT NULL,
    description   TEXT,
    updated_at    TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT pk_module_parameter PRIMARY KEY (id),
    CONSTRAINT uq_module_parameter_param_key UNIQUE (param_key)
);

INSERT INTO detection_results.module_parameter (param_key, value, description) VALUES
    ('align_cc_bad', '0.75', 'ECC cc threshold below which manual alignment is required');


-- =============================================================================
-- Permisos — ajustar el rol si el backend se conecta con un usuario distinto
-- a "UserCatBD".
-- =============================================================================
-- GRANT USAGE ON SCHEMA detection_results TO "UserCatBD";
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA detection_results TO "UserCatBD";
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA detection_results TO "UserCatBD";