-- Revenue Pulse: cleanup for Getting Started with Snowflake Dashboards.
-- Removes everything setup.sql created: REVENUE_PULSE_DB, its DASHBOARD_DEMO
-- schema, the three tables, and REVENUE_SEMANTIC_VIEW.
-- Role: use the same role that ran setup.sql. DROP DATABASE needs OWNERSHIP of
-- the database, and that role owns it. No warehouse is needed.
-- Before running, delete setup.sql and revenue_pulse.dash from your workspace,
-- and if you published the dashboard, remove its roles in Share and delete the
-- artifact in CoWork.
-- If you continued into Build Snowflake Dashboards with CoCo, run
-- sql/99_cleanup.sql instead; it also removes that guide's role and integration.

DROP DATABASE IF EXISTS REVENUE_PULSE_DB;
