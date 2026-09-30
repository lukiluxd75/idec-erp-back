-- Adds year_a/year_b back to detection_results.campaign -- reverting the v5
-- decision (see bdd.sql's original changelog) at the engineer's request: a
-- campaign now fixes a single year pair for its whole life, and the
-- frontend's year selectors lock to it once a campaign is chosen. Nullable:
-- campaigns created before this patch keep NULL (no fixed pair enforced for
-- them), only new campaigns are required to set both from here on (enforced
-- in the application layer, not a NOT NULL constraint, to avoid breaking the
-- existing rows). Applied 2026-09-29 against idec_erp.

BEGIN;

ALTER TABLE detection_results.campaign
    ADD COLUMN year_a INTEGER,
    ADD COLUMN year_b INTEGER;

COMMIT;
