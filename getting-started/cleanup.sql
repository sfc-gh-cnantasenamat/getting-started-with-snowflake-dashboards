-- Revenue Pulse: cleanup for Getting Started with Snowflake Dashboards.
-- Drops the four objects setup.sql created in TEMP.CNANTASENAMAT. The schema itself is left
-- in place because it existed before the tutorial.
-- Role: the role that ran setup.sql (it owns these objects). No warehouse needed.
-- First, if you published the dashboard, remove its roles in Share and delete
-- the artifact in CoWork. Afterwards, delete setup.sql, revenue_pulse.dash, and
-- this file from your workspace.

DROP SEMANTIC VIEW IF EXISTS TEMP.CNANTASENAMAT.REVENUE_SEMANTIC_VIEW;
DROP TABLE IF EXISTS TEMP.CNANTASENAMAT.REVENUE_MONTHLY;
DROP TABLE IF EXISTS TEMP.CNANTASENAMAT.PRODUCTS;
DROP TABLE IF EXISTS TEMP.CNANTASENAMAT.CUSTOMERS;
