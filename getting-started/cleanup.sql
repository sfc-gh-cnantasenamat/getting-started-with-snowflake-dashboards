-- Revenue Pulse: cleanup for Getting Started with Snowflake Dashboards.
-- Drops the four objects setup.sql created. The schema itself is left in place
-- because it existed before the tutorial. Set the USE lines to the same database
-- and schema you used in setup.sql.
-- Role: the role that ran setup.sql (it owns these objects). No warehouse needed.
-- First, if you published the dashboard, remove its roles in Share and delete
-- the artifact in CoWork. Afterwards, delete setup.sql, revenue_pulse.dash, and
-- this file from your workspace.

USE DATABASE TEMP;   -- Replace TEMP with your own database
USE SCHEMA CNANTASENAMAT;   -- Replace CNANTASENAMAT with your own schema in that database

DROP SEMANTIC VIEW IF EXISTS REVENUE_SEMANTIC_VIEW;
DROP TABLE IF EXISTS REVENUE_MONTHLY;
DROP TABLE IF EXISTS PRODUCTS;
DROP TABLE IF EXISTS CUSTOMERS;
