"""Local dashboard contracts and optional Vega rendering checks.

Install vl-convert-python to run rendering checks. Set DASHBOARD_PREVIEW_DIR
to retain PNG previews; otherwise rendering creates no output files.
"""

import copy
import csv
import importlib.util
import json
import os
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_dashboard", ROOT / "maintainer-scripts/build_dashboard.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
TILES = {tile["tile_id"]: tile for tab in MODULE.dash["tabs"] for tile in tab["tiles"]}
TAB_OF = {tile["tile_id"]: tab["tab_id"] for tab in MODULE.dash["tabs"] for tile in tab["tiles"]}


def driver_rows(region=None, segment=None):
    totals = {}
    with (ROOT / "data/revenue_monthly.csv").open(newline="") as source:
        for row in csv.DictReader(source):
            if not "2026-07-01" <= row["month"] <= "2026-09-01":
                continue
            if region and row["region"] != region:
                continue
            if segment and row["segment"] != segment:
                continue
            name = row["recorded_driver"]
            total = totals.setdefault(name, {"variance": 0, "discounts": 0, "refunds": 0, "accounts": set()})
            total["variance"] += (int(row["gross_revenue_cents"]) - int(row["discount_cents"])
                                  - int(row["refund_cents"]) - int(row["target_cents"]))
            total["discounts"] += int(row["discount_cents"])
            total["refunds"] += int(row["refund_cents"])
            total["accounts"].add(row["customer_id"])
    return [{"DRILL_DRIVER": name, "LEVEL": "Driver", "VARIANCE": values["variance"] / 100,
             "DISCOUNTS": values["discounts"] / 100, "REFUNDS": values["refunds"] / 100,
             "ACCOUNTS": len(values["accounts"])} for name, values in totals.items()]


class DashboardTests(unittest.TestCase):
    def test_generated_file_matches_source(self):
        stored = json.loads((ROOT / "dashboards/revenue_pulse_extended.dash").read_text())
        self.assertEqual(stored, MODULE.dash)

    def test_variance_palette_matches_live_configuration(self):
        self.assertEqual(MODULE.VARIANCE_SCALE, {"range": MODULE.PALETTE, "interpolate": "rgb"})

    def test_portable_source_and_no_publication_identity(self):
        serialized = json.dumps(MODULE.dash)
        self.assertNotIn("TEMP.CNANTASENAMAT", serialized)
        self.assertNotIn("siArtifact", serialized)
        self.assertIn("REVENUE_PULSE_DB.DASHBOARD_DEMO.REVENUE_SEMANTIC_VIEW", serialized)

    def test_actions_panel_and_layout(self):
        self.assertEqual(len(TILES), 26)
        self.assertEqual([(t["tab_id"], t["title"]) for t in MODULE.dash["tabs"]],
                         [("default", "Overview"), ("chart_actions", "Chart Actions"), ("hierarchy", "Hierarchical Chart"), ("hierarchy_table", "Hierarchical Table"),
                          ("source", "Data Source")])
        for tab in MODULE.dash["tabs"]:
            self.assertEqual(set(MODULE.dash["layout"][tab["tab_id"]]["positions"]),
                             {t["tile_id"] for t in tab["tiles"]})
        self.assertTrue(TILES["actions"]["text"].startswith("### Explore the Tabs"))
        positions = MODULE.dash["layout"]["default"]["positions"]
        self.assertEqual(positions["header"], {"x": 0, "y": 0, "w": 6, "h": 4})
        self.assertEqual(positions["actions"], {"x": 6, "y": 0, "w": 6, "h": 4})

    def test_native_specs_preserved(self):
        for name in ("drivers", "kpi-net-revenue", "kpi-variance"):
            expected = json.loads((ROOT / "config/chart_specs" / f"{name}.json").read_text())
            self.assertEqual(TILES[name]["spec"], expected)

    def test_sparkline_configuration(self):
        for name in ("net-revenue", "attainment", "variance", "margin"):
            config = TILES[f"kpi-{name}"]["spec"]["usermeta"]["snowflake"]["scorecardConfig"]
            self.assertTrue(config["sparklineEnabled"])
            self.assertEqual(config["seriesBucketField"], "DS")
            self.assertEqual(config["seriesValueField"], "SERIES_VALUE")
            self.assertEqual(config["sparklineColorMode"], "threshold" if name == "variance" else "polarity")
        variance = TILES["kpi-variance"]["spec"]["usermeta"]["snowflake"]["scorecardConfig"]
        self.assertFalse(variance["comparisonEnabled"])
        self.assertEqual(variance["decimals"], 0)
        for value in (-1500001, -1500000, -1, 0, 1):
            matches = [band for band in variance["thresholds"]
                       if (value < band["value"] if band["comparator"] == "lt" else value >= band["value"])]
            self.assertTrue(matches)
            self.assertEqual(matches[0]["color"], "red" if value < -1500000 else "yellow" if value < 0 else "green")

    def test_driver_totals_match_fixture(self):
        expected = json.loads((ROOT / "data/expected_results.json").read_text())
        self.assertAlmostEqual(sum(row["VARIANCE"] for row in driver_rows()),
                               expected["current"]["variance_cents"] / 100)
        self.assertAlmostEqual(sum(row["VARIANCE"] for row in driver_rows("EMEA", "Enterprise")), -778676.37)

    def test_donut_keeps_live_in_ring_labels(self):
        spec = TILES["drivers"]["spec"]
        self.assertEqual(spec["encoding"]["theta"]["field"], "ABS_VARIANCE")
        self.assertEqual(spec["layer"][-1]["encoding"]["text"]["field"], "LABEL")
        self.assertIn("format(datum.VARIANCE", spec["transform"][-1]["calculate"])

    def test_interactions_and_datasources_remain_connected(self):
        for tile in TILES.values():
            for source in tile.get("datasources", []):
                self.assertIn(source, MODULE.dash["datasources"])
        self.assertEqual(TILES["drivers"]["scope"], "detail")
        self.assertEqual(TILES["by-region"]["interactions"][0]["fields"], ["DRILL_REGION"])
        self.assertEqual(TILES["trend"]["interactions"][0]["fields"], ["MONTH"])

    def test_native_hierarchy_drill(self):
        geo = MODULE.dash["hierarchies"]["geo"]
        self.assertEqual([level["id"] for level in geo["levels"]], ["region", "segment", "account"])
        for level in geo["levels"]:
            self.assertIn(level["key"]["expr"], level["group_by"])
            self.assertEqual(level["group_by"][-1], level["display"])
        source = MODULE.dash["datasources"]["ds-geo-drill"]
        self.assertEqual(source["hierarchy_bindings"], [{"hierarchy_id": "geo"}])
        self.assertEqual(source["sql"].count("{{ hierarchy_key('geo') }}"), 2)
        self.assertIn("WHERE\n    {{ hierarchy_rows('geo') }}", source["sql"])
        self.assertNotIn("SEMANTIC_VIEW(", source["sql"])
        tile = TILES["geo-drill"]
        self.assertEqual(tile["scope"], "geo_drill")
        self.assertEqual(MODULE.dash["scopes"]["geo_drill"], {"parent": "main"})
        self.assertEqual(tile["spec"]["layer"][0]["encoding"]["y"]["field"], "LEVEL_LABEL")
        # The drill chart and its account table share a tab and a scope, table directly below.
        self.assertEqual(TAB_OF["geo-drill"], "hierarchy")
        self.assertEqual(TAB_OF["geo-drill-rows"], "hierarchy")
        positions = MODULE.dash["layout"]["hierarchy"]["positions"]
        chart = positions["geo-drill"]
        self.assertEqual((positions["geo-drill-rows"]["x"], positions["geo-drill-rows"]["y"]), (chart["x"] + chart["w"], chart["y"]))
        self.assertEqual(TILES["geo-drill-rows"]["scope"], "geo_drill")
        rows = MODULE.dash["datasources"]["ds-geo-drill-rows"]
        self.assertEqual(rows["hierarchy_bindings"], [{"hierarchy_id": "geo"}])
        self.assertIn("{{ hierarchy_rows('geo') }}", rows["sql"])
        self.assertNotIn("hierarchy_key", rows["sql"])
        self.assertEqual([(i["trigger"], i["operator"]) for i in tile["interactions"]],
                         [("select", "drill_down"), ("select_hierarchy_level", "drill_up"),
                          ("select_hierarchy_level", "set_hierarchy_level")])


@unittest.skipUnless(importlib.util.find_spec("vl_convert"), "Optional vl-convert-python is not installed")
class DashboardRenderTests(unittest.TestCase):
    def test_all_standard_charts_compile_and_render_empty(self):
        import vl_convert

        for name, tile in TILES.items():
            if tile["type"] != "chart" or name.startswith("kpi-"):
                continue
            with self.subTest(tile=name):
                spec = copy.deepcopy(tile["spec"])
                spec.update(data={"values": []}, width=520, height=240)
                ET.fromstring(vl_convert.vegalite_to_svg(spec))

    def test_driver_donut_scenarios(self):
        import vl_convert

        normal = driver_rows()
        scenarios = {"q3": normal, "emea-enterprise": driver_rows("EMEA", "Enterprise"),
                     "all-negative": [{**row, "VARIANCE": -abs(row["VARIANCE"])} for row in normal],
                     "all-positive": [{**row, "VARIANCE": abs(row["VARIANCE"])} for row in normal],
                     "zero": [{**normal[0], "VARIANCE": 0}], "empty": []}
        for scenario, rows in scenarios.items():
            for width in (360, 520):
                for theme in ("light", "dark"):
                    with self.subTest(scenario=scenario, width=width, theme=theme):
                        spec = copy.deepcopy(TILES["drivers"]["spec"])
                        spec.update(data={"values": rows}, width=width, height=240,
                                    background="#ffffff" if theme == "light" else "#17212f",
                                    config={"text": {"color": "#14365d" if theme == "light" else "#e2e8f0"}})
                        svg = vl_convert.vegalite_to_svg(spec)
                        document = ET.fromstring(svg)
                        labels = [element for element in document.iter()
                                  if element.tag.endswith("}text") and "ABS_VARIANCE:" in element.get("aria-label", "")]
                        self.assertEqual(len(labels), len(rows))
                        if os.environ.get("DASHBOARD_PREVIEW_DIR") and scenario in ("q3", "emea-enterprise"):
                            output = Path(os.environ["DASHBOARD_PREVIEW_DIR"])
                            output.mkdir(parents=True, exist_ok=True)
                            (output / f"drivers-{scenario}-{width}-{theme}.png").write_bytes(vl_convert.vegalite_to_png(spec, scale=2))


if __name__ == "__main__":
    unittest.main()

class CompactDashboardTests(unittest.TestCase):
    def test_compact_tabs_and_text_tiles(self):
        spec = importlib.util.spec_from_file_location("build_compact", ROOT / "maintainer-scripts/build_compact.py")
        compact = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(compact)
        self.assertEqual([t["title"] for t in compact.dash["tabs"]], ["Overview", "Hierarchical Chart", "Hierarchical Table", "Data Source"])
        tiles = [t for tab in compact.dash["tabs"] for t in tab["tiles"]]
        self.assertEqual([t["tile_id"] for t in tiles if t["type"] == "text"], ["header", "source", "ask"])
        for tab in compact.dash["tabs"]:
            self.assertEqual(set(compact.dash["layout"][tab["tab_id"]]["positions"]),
                             {t["tile_id"] for t in tab["tiles"]})
        stored = json.loads((ROOT / "dashboards/revenue_pulse.dash").read_text())
        self.assertEqual(stored, compact.dash)


class GettingStartedTests(unittest.TestCase):
    FQ = "TEMP.CNANTASENAMAT"

    def test_files_are_current(self):
        import subprocess, sys, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run([sys.executable, str(ROOT / "maintainer-scripts/build_getting_started.py"),
                            self.FQ, tmp], check=True, capture_output=True)
            for name in ("setup.sql", "cleanup.sql", "revenue_pulse.dash"):
                with self.subTest(name=name):
                    self.assertEqual((Path(tmp) / name).read_text(),
                                     (ROOT / "getting-started" / name).read_text())

    def test_dash_matches_reference_except_schema(self):
        ref = (ROOT / "dashboards/revenue_pulse.dash").read_text()
        part1 = (ROOT / "getting-started/revenue_pulse.dash").read_text()
        self.assertNotIn("REVENUE_PULSE_DB", part1)
        self.assertEqual(part1, ref.replace("REVENUE_PULSE_DB.DASHBOARD_DEMO", self.FQ))

    def test_part1_needs_no_database_or_account_privileges(self):
        for name in ("setup.sql", "cleanup.sql"):
            sql = (ROOT / "getting-started" / name).read_text()
            body = "\n".join(l for l in sql.splitlines()
                             if l.strip() and not l.startswith("--")).upper()
            with self.subTest(name=name):
                self.assertNotIn("CREATE DATABASE", body)
                self.assertNotIn("CREATE SCHEMA", body)  # needs CREATE SCHEMA on the database even IF NOT EXISTS
                self.assertNotIn("DROP DATABASE", body)
                self.assertNotIn("DROP SCHEMA", body)
                self.assertNotIn("REVENUE_PULSE_DB", body)

    def test_cleanup_drops_only_setup_objects(self):
        stmts = [l.split("--")[0].strip() for l in (ROOT / "getting-started/cleanup.sql").read_text().splitlines()
                 if l.strip() and not l.startswith("--")]
        db, schema = self.FQ.split(".")
        self.assertEqual(stmts, [
            f"USE DATABASE {db};",
            f"USE SCHEMA {schema};",
            "DROP SEMANTIC VIEW IF EXISTS REVENUE_SEMANTIC_VIEW;",
            "DROP TABLE IF EXISTS REVENUE_MONTHLY;",
            "DROP TABLE IF EXISTS PRODUCTS;",
            "DROP TABLE IF EXISTS CUSTOMERS;",
        ])

    def test_sql_uses_context_not_qualified_names(self):
        db, schema = self.FQ.split(".")
        for name in ("setup.sql", "cleanup.sql"):
            sql = (ROOT / "getting-started" / name).read_text()
            body = [l for l in sql.splitlines() if l.strip() and not l.startswith("--")]
            with self.subTest(name=name):
                use = [l.split("--")[0].strip() for l in body[:2]]
                self.assertEqual(use, [f"USE DATABASE {db};", f"USE SCHEMA {schema};"])
                self.assertIn(f"Replace {db} with your own database", body[0])
                self.assertIn(f"Replace {schema} with your own schema", body[1])
                self.assertNotIn(self.FQ + ".", "\n".join(body))


class GettingStartedOssieTests(unittest.TestCase):
    """getting-started-ossie/ is Part 1 with the semantic view defined in OSSIE YAML."""
    FQ = "TEMP.CNANTASENAMAT"
    DIR = ROOT / "getting-started-ossie"
    METRICS = ["GROSS_MARGIN", "GROSS_PROFIT", "GROSS_REVENUE", "NET_REVENUE", "REVENUE_TARGET",
               "TARGET_ATTAINMENT", "TARGET_VARIANCE", "TOTAL_DISCOUNTS", "TOTAL_REFUNDS"]

    def test_files_are_current(self):
        import subprocess, sys, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run([sys.executable, str(ROOT / "maintainer-scripts/build_getting_started_ossie.py"),
                            self.FQ, tmp], check=True, capture_output=True)
            for name in ("setup.sql", "cleanup.sql", "revenue_pulse.dash", "revenue_semantic_view.ossie.yaml"):
                with self.subTest(name=name):
                    self.assertEqual((Path(tmp) / name).read_text(), (self.DIR / name).read_text())

    def test_setup_differs_from_native_only_in_semantic_view(self):
        import re
        native = (ROOT / "getting-started/setup.sql").read_text()
        ossie = (self.DIR / "setup.sql").read_text()
        self.assertNotIn("CREATE OR REPLACE SEMANTIC VIEW", ossie)
        self.assertEqual(ossie.count("CALL SYSTEM$CREATE_SEMANTIC_VIEW_FROM_OSSIE_YAML("), 1)
        strip_native = re.sub(r"CREATE OR REPLACE SEMANTIC VIEW .*?COPY GRANTS;\n", "", native, flags=re.S)
        strip_ossie = re.sub(r"-- The semantic view comes from OSSIE.*?\$\$\);\n", "", ossie, flags=re.S)
        body = lambda s: [l for l in s.splitlines() if not l.startswith("--")]
        self.assertEqual(body(strip_ossie), body(strip_native))

    def test_yaml_matches_native_semantic_view(self):
        import re
        import yaml
        model = yaml.safe_load((self.DIR / "revenue_semantic_view.ossie.yaml").read_text())
        self.assertEqual(model["version"], "0.1.1")
        self.assertEqual(model["name"], "REVENUE_SEMANTIC_VIEW")
        self.assertEqual(sorted(m["name"] for m in model["metrics"]), self.METRICS)
        self.assertEqual(sorted(d["source"] for d in model["datasets"]),
                         [f"{self.FQ}.{t}" for t in ("CUSTOMERS", "PRODUCTS", "REVENUE_MONTHLY")])
        native = (ROOT / "sql/02_semantic_view.sql").read_text().upper()
        for m in self.METRICS:
            self.assertRegex(native, rf"\b{m}\b")
        for d in model["datasets"]:
            for f in d["fields"]:
                with self.subTest(field=f["name"]):
                    self.assertRegex(native, rf"\b{f['name']}\b")
        inline = re.search(r"\$\$\n(.*?)\$\$\);", (self.DIR / "setup.sql").read_text(), re.S).group(1)
        self.assertEqual(yaml.safe_load(inline), model)

    def test_dash_matches_native_except_metric_prefix(self):
        import re
        native = (ROOT / "getting-started/revenue_pulse.dash").read_text()
        ossie = (self.DIR / "revenue_pulse.dash").read_text()
        pat = re.compile(r"\brevenue\.(" + "|".join(self.METRICS) + r")\b", re.I)
        self.assertIsNone(pat.search(ossie))
        self.assertEqual(ossie, pat.sub(lambda m: m.group(1).upper(), native))

    def test_cleanup_matches_native(self):
        body = lambda p: [l for l in p.read_text().splitlines() if not l.startswith("--")]
        self.assertEqual(body(self.DIR / "cleanup.sql"), body(ROOT / "getting-started/cleanup.sql"))

    def test_needs_no_database_or_account_privileges(self):
        for name in ("setup.sql", "cleanup.sql"):
            sql = (self.DIR / name).read_text()
            body = "\n".join(l for l in sql.splitlines() if l.strip() and not l.startswith("--")).upper()
            with self.subTest(name=name):
                for bad in ("CREATE DATABASE", "CREATE SCHEMA", "DROP DATABASE", "DROP SCHEMA", "REVENUE_PULSE_DB"):
                    self.assertNotIn(bad, body)
