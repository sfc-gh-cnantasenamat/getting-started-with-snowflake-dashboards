"""Build getting-started/setup.sql (one-shot setup for Part 1) from the committed data and semantic view."""
import csv
import os
import sys

C = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FQ = sys.argv[1] if len(sys.argv) > 1 else 'REVENUE_PULSE_DB.DASHBOARD_DEMO'
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(C, 'getting-started', 'setup.sql')


def q(s):
    return "'" + s.replace("'", "''") + "'"


cust = list(csv.DictReader(open(f'{C}/data/customers.csv')))
prod = list(csv.DictReader(open(f'{C}/data/products.csv')))
rev = list(csv.DictReader(open(f'{C}/data/revenue_monthly.csv')))
sv = open(f'{C}/sql/02_semantic_view.sql').read().strip()
sv = sv.replace('REVENUE_PULSE_DB.DASHBOARD_DEMO', FQ)
drivers = sorted({r['recorded_driver'] for r in rev})
dcode = {d: i for i, d in enumerate(drivers)}
db = FQ.split('.')[0]

head = f"""-- Revenue Pulse: one-shot setup for Getting Started with Snowflake Dashboards.
-- Upload this file to a Snowsight workspace and select Run All.
-- It creates {db} with three tables of synthetic revenue data and a semantic
-- view. No stages, Git integrations, or external files are needed.
-- Role: any role with CREATE DATABASE on the account (SYSADMIN has it), plus
-- USAGE on a warehouse. That role owns everything this script creates.
-- Rerunning is safe: tables are replaced. Teardown: run cleanup.sql.

CREATE DATABASE IF NOT EXISTS {db}
  COMMENT = 'Revenue Pulse quickstart (synthetic data). Safe to drop.';
CREATE SCHEMA IF NOT EXISTS {FQ}
  COMMENT = 'Revenue Pulse Snowflake Dashboards demo (synthetic data)';

CREATE OR REPLACE TABLE {FQ}.CUSTOMERS (
  CUSTOMER_ID VARCHAR NOT NULL PRIMARY KEY,
  CUSTOMER_NAME VARCHAR NOT NULL,
  REGION VARCHAR NOT NULL,
  SEGMENT VARCHAR NOT NULL
) COMMENT = 'Synthetic customer accounts';

CREATE OR REPLACE TABLE {FQ}.PRODUCTS (
  PRODUCT_ID VARCHAR NOT NULL PRIMARY KEY,
  PRODUCT_NAME VARCHAR NOT NULL
) COMMENT = 'Synthetic product lines';

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
) COMMENT = 'Synthetic revenue at account x product x month grain';
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
