# Getting Started with Snowflake Dashboards

Companion code for both Snowflake Dashboards developer guides:

- **Part 1, *Getting Started with Snowflake Dashboards*:** everything is in [`getting-started/`](getting-started/). Run `setup.sql`, upload `revenue_pulse.dash`, and explore a working dashboard in a few minutes.
- **Part 2, *Build Snowflake Dashboards with CoCo*:** build the same dashboard from scratch.

Both parts use the same synthetic Revenue Pulse data. Part 1 gets a finished dashboard running in a few minutes, and Part 2 shows how to build it yourself with Cortex Code. The sections below give a quick-reference version of each.

## Part 1: Deploy the ready-made dashboard

Get the finished Revenue Pulse dashboard running in a few minutes, explore its chart actions and drill-downs, then ask CoWork why the numbers moved.

**You need:** a schema you can create tables and semantic views in, and a warehouse. No admin role.

1. Point the files in [`getting-started/`](getting-started/) at your schema.
2. Run `setup.sql` in a workspace to load the data and semantic view.
3. Upload and open `revenue_pulse.dash`.
4. When you're done, run `cleanup.sql`.

The [guide](https://github.com/sfc-gh-cnantasenamat/sfguide-getting-started-with-snowflake-dashboards) has the full walkthrough and expected numbers.

### Optional: OSSIE variant

[`getting-started-ossie/`](getting-started-ossie/) is the same setup with the semantic view defined in open [Apache Ossie](https://docs.snowflake.com/en/sql-reference/stored-procedures/system_create_semantic_view_from_ossie_yaml) YAML instead of native DDL. Use it in place of `getting-started/`; the dashboard returns the same results.

## Part 2: Build the dashboard with CoCo

Build the same dashboard yourself by prompting Cortex Code, publish it to a sales-ops role, and ask follow-up questions in CoWork.

**You need:** `ACCOUNTADMIN` (setup creates a database, a Git integration, and a viewer role) and a warehouse.

1. Run the SQL scripts in [`sql/`](sql/) in order, starting with `00_bootstrap.sql`.
2. Open this repo as a Git workspace.
3. Prompt Cortex Code to build your own dashboard, using `dashboards/revenue_pulse.dash` as the reference.
4. Publish it as an artifact and share it.

The [guide](https://github.com/sfc-gh-cnantasenamat/sfguide-build-snowflake-dashboards-with-coco) has the prompts, checks, and screenshots for each step.

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
