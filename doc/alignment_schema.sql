-- =============================================================================
-- Esquema: alignment_results (v1)
-- Georreferenciación manual del municipio de Cercado (Cochabamba), manzana
-- por manzana, año por año, contra la capa fija de predios de 2015 -- ver
-- doc/CAMBIOS_DETECCION_CONSTRUCCIONES.md para contexto del módulo de
-- detección de construcciones. Este esquema es completamente independiente
-- de detection_results: no lo referencia ni comparte tablas con él.
--
-- Diseño: cada "alignment_block" es una porción (una manzana, o unas pocas)
-- que el arquitecto dibuja y corrige a mano para un año dado, comparándola
-- contra la base fija 2015. El polígono no cruza predios ni cubre la calle
-- completa (llega hasta el camino y toma solo un cuarto de su ancho) -- la
-- costura entre manzanas vecinas queda sin cubrir a propósito: en vez de un
-- único ajuste global sobre toda la ciudad (que distorsionaría zonas ya
-- buenas), cada manzana se corrige de forma independiente y el "rearmado" es
-- visual en el mapa (cada bloque como una capa georreferenciada propia), no
-- un mosaico de píxeles fusionados.
--
-- Motor: PostgreSQL 14+ con PostGIS.
-- =============================================================================

DROP SCHEMA IF EXISTS alignment_results CASCADE;
CREATE SCHEMA alignment_results AUTHORIZATION "UserCatBD";


-- -----------------------------------------------------------------------------
-- alignment_block -- una manzana (o unas pocas) ya corregida para un año dado
-- -----------------------------------------------------------------------------
CREATE TABLE alignment_results.alignment_block (
    id                   BIGSERIAL,
    year                 INTEGER NOT NULL,
    geom                 GEOMETRY(POLYGON, 4326) NOT NULL,
    status               VARCHAR(20) NOT NULL DEFAULT 'draft',
    transform_method     VARCHAR(20) NOT NULL DEFAULT 'affine',
    transform_params     JSONB,
    rmse_m               NUMERIC(6,2),
    cropped_image_path   TEXT,
    created_by           UUID,
    created_at           TIMESTAMP NOT NULL DEFAULT now(),
    confirmed_by         UUID,
    confirmed_at         TIMESTAMP,
    updated_at           TIMESTAMP NOT NULL DEFAULT now(),
    deleted_at           TIMESTAMP,
    CONSTRAINT pk_alignment_block PRIMARY KEY (id),
    CONSTRAINT fk_alignment_block_created_by FOREIGN KEY (created_by)
        REFERENCES public.users(id),
    CONSTRAINT fk_alignment_block_confirmed_by FOREIGN KEY (confirmed_by)
        REFERENCES public.users(id),
    CONSTRAINT ck_alignment_block_status CHECK (status IN ('draft','confirmed')),
    CONSTRAINT ck_alignment_block_transform_method CHECK (transform_method IN ('similarity','affine')),
    CONSTRAINT ck_alignment_block_year CHECK (year <> 2015),
    CONSTRAINT ck_alignment_block_geom_valid CHECK (ST_IsValid(geom))
);

CREATE INDEX ix_alignment_block_geom ON alignment_results.alignment_block USING GIST (geom);
CREATE INDEX ix_alignment_block_year ON alignment_results.alignment_block(year);
CREATE INDEX ix_alignment_block_status ON alignment_results.alignment_block(status);


-- -----------------------------------------------------------------------------
-- alignment_control_point -- puntos marcados por el arquitecto para calcular
-- la transformación de un alignment_block: uno sobre la base fija 2015
-- (lon_ref/lat_ref) y su correspondiente sobre la capa WMS del año a
-- corregir, tal como se ve hoy, sin corregir (lon_mov/lat_mov). Ambos en
-- WGS84 (grados) -- a diferencia de detection_results.control_point (que usa
-- coordenadas de píxel sobre un par de imágenes ya recortadas de un job), acá
-- ambos puntos se toman directamente clicando sobre capas WMS en el mapa.
-- -----------------------------------------------------------------------------
CREATE TABLE alignment_results.alignment_control_point (
    id                     BIGSERIAL,
    alignment_block_id     BIGINT NOT NULL,
    order_index            SMALLINT NOT NULL,
    lon_ref                NUMERIC NOT NULL,
    lat_ref                NUMERIC NOT NULL,
    lon_mov                NUMERIC NOT NULL,
    lat_mov                NUMERIC NOT NULL,
    CONSTRAINT pk_alignment_control_point PRIMARY KEY (id),
    CONSTRAINT fk_alignment_control_point_block FOREIGN KEY (alignment_block_id)
        REFERENCES alignment_results.alignment_block(id) ON DELETE CASCADE
);

CREATE INDEX ix_alignment_control_point_block_id ON alignment_results.alignment_control_point(alignment_block_id);
