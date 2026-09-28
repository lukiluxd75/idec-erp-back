-- Migrate detection_results' actor columns from BIGINT to UUID, with a real
-- FK to public.users(id). bdd.sql (v5) created these as BIGINT with a
-- "pendiente: FK real al autenticador del ERP" note, because the only
-- internal user identity in this ERP is public.users.id, which is UUID (see
-- security/infrastructure/models.py) -- not BIGINT, and not the Keycloak
-- `sub` either. Applied 2026-09-17 against idec_erp.
--
-- USING NULL discards any BIGINT values already stored in these columns
-- (there is no legacy numeric user id anywhere in this ERP to convert them
-- from) -- safe here because these columns were never populated: the backend
-- had no code path writing to them until this migration's matching ORM
-- change (see detection/infrastructure/models.py).

BEGIN;

ALTER TABLE detection_results.campaign
    ALTER COLUMN created_by TYPE UUID USING NULL;

ALTER TABLE detection_results.processed_sector
    ALTER COLUMN created_by TYPE UUID USING NULL,
    ALTER COLUMN updated_by TYPE UUID USING NULL;

ALTER TABLE detection_results.affected_parcel
    ALTER COLUMN validated_by TYPE UUID USING NULL;

ALTER TABLE detection_results.architect_review
    ALTER COLUMN created_by TYPE UUID USING NULL;

ALTER TABLE detection_results.model_feedback
    ALTER COLUMN created_by TYPE UUID USING NULL;

ALTER TABLE detection_results.campaign
    ADD CONSTRAINT fk_campaign_created_by
    FOREIGN KEY (created_by) REFERENCES public.users(id);

ALTER TABLE detection_results.processed_sector
    ADD CONSTRAINT fk_processed_sector_created_by
    FOREIGN KEY (created_by) REFERENCES public.users(id),
    ADD CONSTRAINT fk_processed_sector_updated_by
    FOREIGN KEY (updated_by) REFERENCES public.users(id);

ALTER TABLE detection_results.affected_parcel
    ADD CONSTRAINT fk_affected_parcel_validated_by
    FOREIGN KEY (validated_by) REFERENCES public.users(id);

ALTER TABLE detection_results.architect_review
    ADD CONSTRAINT fk_architect_review_created_by
    FOREIGN KEY (created_by) REFERENCES public.users(id);

ALTER TABLE detection_results.model_feedback
    ADD CONSTRAINT fk_model_feedback_created_by
    FOREIGN KEY (created_by) REFERENCES public.users(id);

COMMIT;
