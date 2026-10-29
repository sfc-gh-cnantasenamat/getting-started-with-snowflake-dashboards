"""Build getting-started-ossie/: the Part 1 files with the semantic view defined in OSSIE YAML.

Same tables and data as getting-started/; only the semantic view step differs. It calls
SYSTEM$CREATE_SEMANTIC_VIEW_FROM_OSSIE_YAML instead of CREATE SEMANTIC VIEW. OSSIE metrics
are model-level, so the dashboard references them without a table prefix.
Usage: build_getting_started_ossie.py [DB.SCHEMA] [OUT_DIR]
"""
import json
import os
import re
import subprocess
import sys
import tempfile

import yaml

C = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FQ = sys.argv[1] if len(sys.argv) > 1 else 'TEMP.CNANTASENAMAT'
OUT_DIR = sys.argv[2] if len(sys.argv) > 2 else os.path.join(C, 'getting-started-ossie')
METRICS = ['GROSS_MARGIN', 'GROSS_PROFIT', 'GROSS_REVENUE', 'NET_REVENUE', 'REVENUE_TARGET',
           'TARGET_ATTAINMENT', 'TARGET_VARIANCE', 'TOTAL_DISCOUNTS', 'TOTAL_REFUNDS']


def expr(sql):
    return {'dialects': [{'dialect': 'SNOWFLAKE', 'expression': sql}]}


def field(name, sql, desc, kind='dim', ai=None):
    f = {'name': name, 'expression': expr(sql), 'description': desc}
    if kind == 'dim':
        f['dimension'] = {'is_time': False}
    elif kind == 'time':
        f['dimension'] = {'is_time': True}
    if ai:
        f['ai_context'] = ai
    return f


def metric(name, sql, desc, ai=None):
    m = {'name': name, 'expression': expr(sql), 'description': desc}
    if ai:
        m['ai_context'] = ai
    return m


# Mirrors sql/02_semantic_view.sql using only standard OSSIE 0.1.1 constructs.
# Synonyms become ai_context, and table-level metrics become model-level metrics.
model = {
    'version': '0.1.1',
    'name': 'REVENUE_SEMANTIC_VIEW',
    'description': ('Revenue Pulse: synthetic B2B revenue vs target by month, region, segment, '
                    'account, and product. Data through 2026-09-30.'),
    'ai_context': ('Data is monthly and complete through September 2026. Last quarter or Q3 means months '
                   '2026-07-01 through 2026-09-01. Ratios are 0-1; present as percentages. '
                   'Year-over-year compares the same months one year earlier.'),
    'datasets': [
        {'name': 'CUSTOMERS', 'source': f'{FQ}.CUSTOMERS', 'primary_key': ['CUSTOMER_ID'],
         'description': 'Customer accounts with sales region and segment',
         'ai_context': 'Also called accounts or clients.',
         'fields': [
             field('CUSTOMER_ID', 'CUSTOMER_ID', 'Customer identifier'),
             field('CUSTOMER_NAME', 'CUSTOMER_NAME', 'Customer account name', ai='Also called account name.'),
             field('REGION', 'REGION', 'Sales region: Americas, EMEA, APAC', ai='Also called geo or territory.'),
             field('SEGMENT', 'SEGMENT', 'Customer segment: Enterprise, Mid-market, SMB'),
         ]},
        {'name': 'PRODUCTS', 'source': f'{FQ}.PRODUCTS', 'primary_key': ['PRODUCT_ID'],
         'description': 'Product lines', 'ai_context': 'Also called product lines.',
         'fields': [
             field('PRODUCT_ID', 'PRODUCT_ID', 'Product identifier'),
             field('PRODUCT_NAME', 'PRODUCT_NAME', 'Product line name', ai='Also called product.'),
         ]},
        {'name': 'REVENUE', 'source': f'{FQ}.REVENUE_MONTHLY', 'primary_key': ['REVENUE_ID'],
         'description': 'Monthly revenue, target, and cost per customer and product. Synthetic.',
         'fields': [
             field('REVENUE_ID', 'REVENUE_ID', 'Row identifier: customer, product, and month'),
             field('CUSTOMER_ID', 'CUSTOMER_ID', 'Customer identifier (foreign key)'),
             field('PRODUCT_ID', 'PRODUCT_ID', 'Product identifier (foreign key)'),
             field('MONTH', 'MONTH', 'First day of the revenue month', kind='time', ai='Also called period or date.'),
             field('QUARTER', "DATE_TRUNC('QUARTER', MONTH)", 'First day of the calendar quarter', kind='time'),
             field('YEAR', 'YEAR(MONTH)', 'Calendar year'),
             field('RECORDED_DRIVER', 'RECORDED_DRIVER',
                   'Driver recorded by sales ops: NORMAL_TRADING, RECORDED_CONTRACT_DOWNSIZE, '
                   'RECORDED_DISCOUNT_AND_SERVICE_CREDIT, RECORDED_RENEWAL_DELAY'),
             field('GROSS_REVENUE_USD', 'GROSS_REVENUE_CENTS / 100', 'List revenue before discounts and refunds, USD', kind='fact'),
             field('DISCOUNT_USD', 'DISCOUNT_CENTS / 100', 'Discounts granted, USD', kind='fact'),
             field('REFUND_USD', 'REFUND_CENTS / 100', 'Refunds and service credits, USD', kind='fact'),
             field('NET_REVENUE_USD', '(GROSS_REVENUE_CENTS - DISCOUNT_CENTS - REFUND_CENTS) / 100',
                   'Gross revenue minus discounts and refunds, USD', kind='fact'),
             field('COST_USD', 'COST_CENTS / 100', 'Cost of revenue, USD', kind='fact'),
             field('TARGET_USD', 'TARGET_CENTS / 100', 'Revenue target, USD', kind='fact'),
         ]},
    ],
    'relationships': [
        {'name': 'REVENUE_TO_CUSTOMERS', 'from': 'REVENUE', 'to': 'CUSTOMERS',
         'from_columns': ['CUSTOMER_ID'], 'to_columns': ['CUSTOMER_ID']},
        {'name': 'REVENUE_TO_PRODUCTS', 'from': 'REVENUE', 'to': 'PRODUCTS',
         'from_columns': ['PRODUCT_ID'], 'to_columns': ['PRODUCT_ID']},
    ],
    'metrics': [
        metric('NET_REVENUE', 'SUM(REVENUE.NET_REVENUE_USD)', 'Net revenue in USD: gross minus discounts and refunds',
               ai='Also called revenue or sales.'),
        metric('GROSS_REVENUE', 'SUM(REVENUE.GROSS_REVENUE_USD)', 'Gross revenue in USD'),
        metric('TOTAL_DISCOUNTS', 'SUM(REVENUE.DISCOUNT_USD)', 'Total discounts in USD'),
        metric('TOTAL_REFUNDS', 'SUM(REVENUE.REFUND_USD)', 'Total refunds and service credits in USD'),
        metric('REVENUE_TARGET', 'SUM(REVENUE.TARGET_USD)', 'Revenue target in USD', ai='Also called quota or plan.'),
        metric('TARGET_VARIANCE', 'SUM(REVENUE.NET_REVENUE_USD) - SUM(REVENUE.TARGET_USD)',
               'Net revenue minus target in USD; negative means behind target', ai='Also called gap or shortfall.'),
        metric('TARGET_ATTAINMENT', 'DIV0NULL(SUM(REVENUE.NET_REVENUE_USD), SUM(REVENUE.TARGET_USD))',
               'Net revenue divided by target, as a ratio (0.92 = 92%)'),
        metric('GROSS_PROFIT', 'SUM(REVENUE.NET_REVENUE_USD) - SUM(REVENUE.COST_USD)', 'Net revenue minus cost in USD'),
        metric('GROSS_MARGIN', 'DIV0NULL(SUM(REVENUE.NET_REVENUE_USD) - SUM(REVENUE.COST_USD), SUM(REVENUE.NET_REVENUE_USD))',
               'Gross profit divided by net revenue, as a ratio; null when net revenue is zero'),
    ],
}
ossie = yaml.safe_dump(model, sort_keys=False, width=120)
assert '$$' not in ossie

os.makedirs(OUT_DIR, exist_ok=True)
with tempfile.TemporaryDirectory() as tmp:
    subprocess.run([sys.executable, os.path.join(C, 'maintainer-scripts/build_getting_started.py'), FQ, tmp], check=True)
    setup = open(os.path.join(tmp, 'setup.sql')).read()
    cleanup = open(os.path.join(tmp, 'cleanup.sql')).read()
    dash = open(os.path.join(tmp, 'revenue_pulse.dash')).read()

# Swap only the semantic view statement; tables, data, and the row-count check stay the same.
sv = re.compile(r'CREATE OR REPLACE SEMANTIC VIEW .*?COPY GRANTS;\n', re.S)
assert len(sv.findall(setup)) == 1
call = (f"-- The semantic view comes from OSSIE YAML (open semantic model standard). The\n"
        f"-- procedure needs DATABASE.SCHEMA here and in each dataset source below; replace\n"
        f"-- {FQ} in all four places. A rerun replaces the view and keeps its grants.\n"
        f"CALL SYSTEM$CREATE_SEMANTIC_VIEW_FROM_OSSIE_YAML(\n"
        f"  '{FQ}',   -- Replace with your own DATABASE.SCHEMA\n$$\n{ossie}$$);\n")
setup = sv.sub(lambda _: call, setup)
setup = setup.replace('setup for Getting Started with Snowflake Dashboards.',
                      'setup for Getting Started with Snowflake Dashboards (OSSIE variant).')
setup = setup.replace('-- Before running: set the two USE lines below to your own database and schema,\n',
                      f'-- Before running: set the two USE lines below to your own database and schema,\n'
                      f'-- replace {FQ} in the OSSIE CALL near the end,\n')
cleanup = cleanup.replace('cleanup for Getting Started with Snowflake Dashboards.',
                          'cleanup for Getting Started with Snowflake Dashboards (OSSIE variant).')

pat = re.compile(r'\brevenue\.(' + '|'.join(METRICS) + r')\b', re.I)
assert pat.search(dash)
dash = pat.sub(lambda m: m.group(1).upper(), dash)
json.loads(dash)

for name, text in [('setup.sql', setup), ('cleanup.sql', cleanup), ('revenue_pulse.dash', dash),
                   ('revenue_semantic_view.ossie.yaml', ossie)]:
    open(os.path.join(OUT_DIR, name), 'w').write(text)
