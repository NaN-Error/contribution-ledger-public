-- Optional PostgreSQL privilege provisioning; NEVER run on normal startup.
-- Use psql as the migration owner, with pre-created NONOWNER, NONSUPERUSER roles.
-- psql -v app_schema=public -v credit_writer=cl_api -v credit_reader=cl_analytics -f infra/ledger-privileges.sql
-- This script grants only PHASE-6 table privileges, not the complete API's access.
-- Default local Compose uses an operator-owned account and does not exercise this
-- least-privilege profile. Configure separate credentials before remote/worker use.
\set ON_ERROR_STOP on
BEGIN;
GRANT USAGE ON SCHEMA :"app_schema" TO :"credit_writer", :"credit_reader";
REVOKE ALL ON :"app_schema".review_rounds, :"app_schema".review_assignments,
    :"app_schema".review_decisions, :"app_schema".credit_awards,
    :"app_schema".contribution_events, :"app_schema".credit_disputes,
    :"app_schema".dispute_assignments, :"app_schema".dispute_notes,
    :"app_schema".dispute_resolutions, :"app_schema".participant_notifications,
    :"app_schema".contribution_balances FROM PUBLIC, :"credit_reader", :"credit_writer";
GRANT SELECT, INSERT ON :"app_schema".review_rounds, :"app_schema".review_assignments,
    :"app_schema".review_decisions, :"app_schema".credit_awards,
    :"app_schema".contribution_events, :"app_schema".credit_disputes,
    :"app_schema".dispute_assignments, :"app_schema".dispute_notes,
    :"app_schema".dispute_resolutions, :"app_schema".participant_notifications TO :"credit_writer";
GRANT SELECT, INSERT, UPDATE ON :"app_schema".contribution_balances TO :"credit_writer";
-- Repair (DELETE/rebuild) is intentionally left to an audited operator, not API.
GRANT SELECT ON :"app_schema".credit_awards, :"app_schema".contribution_events,
    :"app_schema".contribution_balances TO :"credit_reader";
COMMIT;
-- Inspect inherited memberships/default privileges separately. Grants are
-- additive across role memberships; this script cannot neutralize a superuser,
-- owner, or another inherited writer role. Never grant a future AI evaluator
-- the credit_writer role or use the local operator DSN as its connection.
