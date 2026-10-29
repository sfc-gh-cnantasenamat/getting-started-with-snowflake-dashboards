# Getting Started with Snowflake Dashboards

Companion code for both Snowflake Dashboards developer guides:

- **Part 1, *Getting Started with Snowflake Dashboards*:** everything is in [`getting-started/`](getting-started/). Run `setup.sql`, upload `revenue_pulse.dash`, and explore a working dashboard in a few minutes.
- **Part 2, *Build Snowflake Dashboards with CoCo*:** build the same dashboard from scratch.

Both parts use the same synthetic Revenue Pulse data. Part 1 gets a finished dashboard running in a few minutes, and Part 2 shows how to build it yourself with Cortex Code. The sections below give a quick-reference version of each.

## Part 1: Deploy the ready-made dashboard

In Part 1 you load a small synthetic revenue dataset and a semantic view into a schema you already have, open the finished Revenue Pulse dashboard, explore its chart actions and hierarchy drill-down, then publish it to Snowflake CoWork and ask why the numbers moved. All data is synthetic.

Everything runs in Snowsight. You don't need Python, a CLI, a Git integration, or a local clone.

The guide holds the walkthrough: what to click, the expected numbers at each step, and the screenshots. This repository holds the files it uses: `setup.sql`, `revenue_pulse.dash`, and `cleanup.sql` in `getting-started/`. The steps below are a quick reference; follow the guide the first time.

Part 1 works in an existing schema, `TEMP.CNANTASENAMAT` by default (replace it with your own database and schema), so it needs no `ACCOUNTADMIN`, `SYSADMIN`, or `CREATE DATABASE`. The role needs `USAGE` on the database, the schema, and a warehouse, plus `CREATE TABLE` and `CREATE SEMANTIC VIEW` on the schema; a schema's owner has all of these. The schema must already exist: setup doesn't create it, because `CREATE SCHEMA IF NOT EXISTS` still requires `CREATE SCHEMA` on the database. To use a different schema, edit the `USE DATABASE` and `USE SCHEMA` lines at the top of `setup.sql` and `cleanup.sql`, and replace `TEMP.CNANTASENAMAT` in `revenue_pulse.dash`, whose queries keep fully qualified names so shared viewers can run them. The semantic view stores fully qualified table references, so the dashboard works from any session context.

1. In Snowsight, open **Projects » Workspaces**. In **My Workspace**, select **+ Add New » Upload Files** and upload [`getting-started/setup.sql`](getting-started/setup.sql).
2. Open it, pick your role and a warehouse, and select **Run All**. It finishes in about 10 seconds and returns 54 customers, 3 products, and 3,888 revenue rows.
3. Upload [`getting-started/revenue_pulse.dash`](getting-started/revenue_pulse.dash) the same way and open it.
4. To clean up, run [`getting-started/cleanup.sql`](getting-started/cleanup.sql) with the same role. It drops the four objects setup created and leaves the schema in place.

`setup.sql` is self-contained: it inlines the data from `data/` and the semantic view from `sql/02_semantic_view.sql`, with no stage or Git integration. It replaces any existing `CUSTOMERS`, `PRODUCTS`, `REVENUE_MONTHLY`, or `REVENUE_SEMANTIC_VIEW` in the schema, and uses `COPY GRANTS` so a rerun keeps their grants. `getting-started/revenue_pulse.dash` is `dashboards/revenue_pulse.dash` pointed at the Part 1 schema. Part 2 sets up its own `REVENUE_PULSE_DB` and doesn't reuse Part 1's objects.

### Optional: define the semantic view with OSSIE

[`getting-started-ossie/`](getting-started-ossie/) is the same Part 1 setup with the semantic view defined in [Apache Ossie](https://docs.snowflake.com/en/sql-reference/stored-procedures/system_create_semantic_view_from_ossie_yaml) (incubating) YAML, an open semantic model standard shared across AI and BI tools. Use it instead of `getting-started/`, not alongside it: both create the same objects in the same schema.

- `setup.sql` creates the same tables and data, then calls `SYSTEM$CREATE_SEMANTIC_VIEW_FROM_OSSIE_YAML` instead of `CREATE SEMANTIC VIEW`. It needs the same privileges, and a rerun keeps grants. The procedure needs fully qualified names, so replace `TEMP.CNANTASENAMAT` in the `CALL` and its three dataset `source:` lines as well as in the `USE` lines.
- `revenue_pulse.dash` is the Part 1 dashboard with unprefixed metric references (`NET_REVENUE` instead of `revenue.net_revenue`), because OSSIE metrics are model-level, so use it only with the OSSIE view.
- `cleanup.sql` is identical to the native one.
- `revenue_semantic_view.ossie.yaml` is the same YAML as a standalone file, for other tools.

OSSIE has no synonyms or custom instructions; they become `ai_context` text. The dashboard returns the same results with either view.

## Part 2: Build the dashboard with CoCo

In Part 2 you use Cortex Code prompts to build, refine, and check a native Workspaces dashboard on a revenue semantic view, publish it to a sales-ops role as an artifact, and ask follow-up "why" questions in Snowflake CoWork. All data is synthetic.

Everything runs in Snowsight. You don't need Python, a CLI, or a local clone.

The guide holds the walkthrough: the Cortex Code prompts, the expected output and checks for each step, and the screenshots. This repository holds what those steps run against: the SQL, the synthetic data, and the completed dashboard. The steps below are a quick reference; follow the guide the first time.

1. In Snowsight, open **Projects > Workspaces**, create a SQL file in **My Workspace**, and set the role to `ACCOUNTADMIN` and the warehouse to `COMPUTE_WH`.
2. Paste and run [`sql/00_bootstrap.sql`](sql/00_bootstrap.sql). It creates `REVENUE_PULSE_DB`, an API integration, and a Git repository object over this repo.
3. Run the remaining scripts straight from the repository:

```sql
EXECUTE IMMEDIATE FROM @REVENUE_PULSE_DB.DASHBOARD_DEMO.REVENUE_PULSE_REPO/branches/main/sql/01_setup.sql;
EXECUTE IMMEDIATE FROM @REVENUE_PULSE_DB.DASHBOARD_DEMO.REVENUE_PULSE_REPO/branches/main/sql/02_semantic_view.sql;
EXECUTE IMMEDIATE FROM @REVENUE_PULSE_DB.DASHBOARD_DEMO.REVENUE_PULSE_REPO/branches/main/sql/03_agent.sql;
EXECUTE IMMEDIATE FROM @REVENUE_PULSE_DB.DASHBOARD_DEMO.REVENUE_PULSE_REPO/branches/main/sql/04_viewer_role.sql;
```

4. In **Workspaces**, select **+ > Git workspace**, paste this repo's URL, and choose the `REVENUE_PULSE_GIT_API` integration (the dialog may preselect another one) and **Public repository**.
5. Open Cortex Code in the workspace and follow the guide's prompts to build your own `dashboards/revenue_pulse_draft.dash`. Leave `dashboards/revenue_pulse.dash` unchanged; it is the completed example used for the guide's screenshots and expected figures.
   To view the completed example, open it and select the role and a warehouse (for example `COMPUTE_WH`) in its toolbar before **Run all**.
6. After validating your draft, choose **Share > Publish as artifact** with the `DASHBOARD_DEMO_SALES_OPS` role. See the guide for the full walkthrough.

If your warehouse isn't `COMPUTE_WH`, replace it in `sql/03_agent.sql` and `sql/04_viewer_role.sql` in your own copy of the files before running them.

## Layout

```
sql/00_bootstrap.sql         database, API integration, Git repository object
sql/01_setup.sql             tables, stage, and data load from data/
sql/02_semantic_view.sql     semantic view
sql/03_agent.sql             Revenue Advisor Cortex agent
sql/04_viewer_role.sql       least-privilege viewer role
sql/99_cleanup.sql           teardown; never run automatically
getting-started/             Part 1 (generated): setup.sql, revenue_pulse.dash, cleanup.sql
getting-started-ossie/       Part 1 with an OSSIE-defined semantic view (generated, optional)
data/                        committed synthetic CSVs and expected_results.json
dashboards/revenue_pulse.dash  completed example dashboard, compact (reference; build your own draft beside it)
dashboards/revenue_pulse_extended.dash  extended example with how-to tiles on five tabs
docs/demo-script.md          five-minute presenter walkthrough of the completed dashboard
```

Maintainer only (not needed to follow the guide): `maintainer-scripts/generate_data.py` and `maintainer-scripts/build_dashboard.py` regenerate `data/` and `dashboards/`, and `maintainer-scripts/build_getting_started.py` regenerates all three `getting-started/` files from `data/`, `sql/02_semantic_view.sql`, and `dashboards/revenue_pulse.dash` (rerun it after changing any of them; pass `DATABASE.SCHEMA` to target another schema). `maintainer-scripts/build_getting_started_ossie.py` regenerates `getting-started-ossie/` the same way; it needs PyYAML. Both `data/` and `dashboards/` from `config/demo.json`, and `tests/test_data.py` tests the generator.

### Local visual checks

After changing the dashboard generator, regenerate the file and run the tests:

```bash
python3 maintainer-scripts/build_dashboard.py
python3 -m unittest discover -s tests -v
```

Install the optional `vl-convert-python` package to include local chart-rendering checks.
Set `DASHBOARD_PREVIEW_DIR` to a local output directory to retain driver-chart PNGs.
The checks cover narrow and wide tiles, light and dark theme simulations, signed
variances, and empty data. Native scorecard sparklines and dashboard interactions
still need verification in Snowsight; the local Vega renderer does not exercise them.

The driver donut uses absolute variance for slice area and signed values for its
in-ring labels. Slice area is not a share of the net shortfall. Its data-relative
palette also appears on the region bars and the variance waterfall; colors show relative variance,
not fixed alert bands.

`config/chart_specs/` preserves the native editor's driver donut and expanded net
revenue and variance scorecards, including their animations. The generator loads
these specs and checks that the scorecard settings match its configuration. Keep
these files when regenerating so native editor refinements are not lost.

The companion dashboard uses `REVENUE_PULSE_DB.DASHBOARD_DEMO` and omits publishing
IDs so it can be deployed and published independently in another account.

## Clean up

Remove every role from the dashboard's **Share** dialog, delete the artifact in CoWork, and delete the Git workspace (**...** next to its name > **Delete**). Then run `sql/99_cleanup.sql`, which drops `REVENUE_PULSE_DB`, the viewer role, and the API integration.
