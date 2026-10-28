"""Build the Part 1 files in getting-started/ from the committed data, semantic view, and dashboard.

Writes setup.sql, cleanup.sql, and revenue_pulse.dash, all pointing at one existing
schema (default TEMP.CNANTASENAMAT). Usage: build_getting_started.py [DB.SCHEMA] [OUT_DIR]
"""
import csv
import os
import sys

C = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FQ = sys.argv[1] if len(sys.argv) > 1 else 'TEMP.CNANTASENAMAT'
OUT_DIR = sys.argv[2] if len(sys.argv) > 2 else os.path.join(C, 'getting-started')
OUT = os.path.join(OUT_DIR, 'setup.sql')
SOURCE_FQ = 'REVENUE_PULSE_DB.DASHBOARD_DEMO'


def q(s):
    return "'" + s.replace("'", "''") + "'"


cust = list(csv.DictReader(open(f'{C}/data/customers.csv')))
prod = list(csv.DictReader(open(f'{C}/data/products.csv')))
rev = list(csv.DictReader(open(f'{C}/data/revenue_monthly.csv')))
sv = open(f'{C}/sql/02_semantic_view.sql').read().strip()
sv = sv.replace(SOURCE_FQ, FQ)
assert sv.endswith(";")
# COPY GRANTS keeps existing grants (for example a dashboard viewer role) on rerun.
sv = sv[:-1] + "\n  COPY GRANTS;"
drivers = sorted({r['recorded_driver'] for r in rev})
dcode = {d: i for i, d in enumerate(drivers)}

head = f"""-- Revenue Pulse: setup for Getting Started with Snowflake Dashboards.
-- Creates three tables of synthetic revenue data and a semantic view in an
-- existing schema, {FQ}. No new database, stages, or Git integrations.
-- To use another schema, find-and-replace {FQ} with your DATABASE.SCHEMA in
-- this file, revenue_pulse.dash, and cleanup.sql before uploading them.
-- Role: any role with USAGE on the database, a warehouse, and on the schema
-- CREATE TABLE and CREATE SEMANTIC VIEW (the schema's owner has all of these).
-- No ACCOUNTADMIN or SYSADMIN needed. Upload to a workspace and select Run All.
-- Rerunning is safe: objects are replaced and keep their grants.
-- Note: this replaces any existing CUSTOMERS, PRODUCTS, REVENUE_MONTHLY, or
-- REVENUE_SEMANTIC_VIEW in the schema. Teardown: run cleanup.sql.

CREATE SCHEMA IF NOT EXISTS {FQ};

CREATE OR REPLACE TABLE {FQ}.CUSTOMERS (
  CUSTOMER_ID VARCHAR NOT NULL PRIMARY KEY,
  CUSTOMER_NAME VARCHAR NOT NULL,
  REGION VARCHAR NOT NULL,
  SEGMENT VARCHAR NOT NULL
) COMMENT = 'Synthetic customer accounts' COPY GRANTS;

CREATE OR REPLACE TABLE {FQ}.PRODUCTS (
  PRODUCT_ID VARCHAR NOT NULL PRIMARY KEY,
  PRODUCT_NAME VARCHAR NOT NULL
) COMMENT = 'Synthetic product lines' COPY GRANTS;

CREATE OR REPLACE TABLE {FQ}.REVENUE_MONTHLY (
  REVENUE_ID VARCHAR NOT NULL PRIMARY KEY,
  MONTH DATE NOT NULL,
  CUSTOMER_ID VARCHAR NOT NULL,
  PRODUCT_ID VARCHAR NOT NULL,
  GROSS_REVENUE_CENTS NUMBER(18,0) NOT NULL,
  DISCOUNT_CENTS NUMBER(18,0) NOT NULL,
  REFUND_CENTS NUMBER(18,0) NOT NULL,
  COST_CENTS NUMBER(18,0) NOT NULL,
  TARGET_CENTS NUMBER(18,0) NOT NULL,
  RECORDED_DRIVER VARCHAR NOT NULL
) COMMENT = 'Synthetic revenue at account x product x month grain' COPY GRANTS;
"""

parts = [head]
parts.append(f"INSERT INTO {FQ}.CUSTOMERS VALUES\n" + ",\n".join(
    f"({q(r['customer_id'])},{q(r['customer_name'])},{q(r['region'])},{q(r['segment'])})" for r in cust) + ";\n")
parts.append(f"INSERT INTO {FQ}.PRODUCTS VALUES\n" + ",\n".join(
    f"({q(r['product_id'])},{q(r['product_name'])})" for r in prod) + ";\n")
decode = ", ".join(f"{i}, {q(d)}" for d, i in dcode.items())
rows = ",\n".join(
    f"('{r['customer_id']}','{r['product_id']}',{r['month'][:7].replace('-', '')},"
    f"{r['gross_revenue_cents']},{r['discount_cents']},{r['refund_cents']},"
    f"{r['cost_cents']},{r['target_cents']},{dcode[r['recorded_driver']]})" for r in rev)
parts.append(
    "-- Revenue rows are packed as (customer, product, YYYYMM, gross, discount, refund, cost,\n"
    "-- target, driver code) to keep this file small; the SELECT expands them to full columns.\n"
    f"INSERT INTO {FQ}.REVENUE_MONTHLY\n"
    "SELECT c || '-' || p || '-' || ym, TO_DATE(ym::VARCHAR, 'YYYYMM'), c, p, g, d, r, k, t,\n"
    f"  DECODE(dr, {decode})\nFROM VALUES\n{rows}\n  AS v(c, p, ym, g, d, r, k, t, dr);\n")
parts.append(sv + "\n")
parts.append(f"""-- Expect 54 customers, 3 products, 3888 revenue rows.
SELECT
  (SELECT COUNT(*) FROM {FQ}.CUSTOMERS) AS CUSTOMERS,
  (SELECT COUNT(*) FROM {FQ}.PRODUCTS) AS PRODUCTS,
  (SELECT COUNT(*) FROM {FQ}.REVENUE_MONTHLY) AS REVENUE_ROWS;
""")
open(OUT, 'w').write("\n".join(parts))

cleanup = f"""-- Revenue Pulse: cleanup for Getting Started with Snowflake Dashboards.
-- Drops the four objects setup.sql created in {FQ}. The schema itself is left
-- in place because it existed before the tutorial.
-- Role: the role that ran setup.sql (it owns these objects). No warehouse needed.
-- First, if you published the dashboard, remove its roles in Share and delete
-- the artifact in CoWork. Afterwards, delete setup.sql, revenue_pulse.dash, and
-- this file from your workspace.

DROP SEMANTIC VIEW IF EXISTS {FQ}.REVENUE_SEMANTIC_VIEW;
DROP TABLE IF EXISTS {FQ}.REVENUE_MONTHLY;
DROP TABLE IF EXISTS {FQ}.PRODUCTS;
DROP TABLE IF EXISTS {FQ}.CUSTOMERS;
"""
open(os.path.join(OUT_DIR, 'cleanup.sql'), 'w').write(cleanup)

# Part 1's dashboard is the reference dashboard pointed at the tutorial schema.
dash = open(f'{C}/dashboards/revenue_pulse.dash').read()
assert SOURCE_FQ in dash
open(os.path.join(OUT_DIR, 'revenue_pulse.dash'), 'w').write(dash.replace(SOURCE_FQ, FQ))
