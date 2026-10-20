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
SPEC = importlib.util.spec_from_file_location("build_dashboard", ROOT / "scripts/build_dashboard.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
TILES = {tile["tile_id"]: tile for tile in MODULE.dash["tabs"][0]["tiles"]}


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
        stored = json.loads((ROOT / "dashboards/revenue_pulse.dash").read_text())
        self.assertEqual(stored, MODULE.dash)

    def test_variance_palette_matches_live_configuration(self):
        self.assertEqual(MODULE.VARIANCE_SCALE, {"range": MODULE.PALETTE, "interpolate": "rgb"})

    def test_portable_source_and_no_publication_identity(self):
        serialized = json.dumps(MODULE.dash)
        self.assertNotIn("TEMP.CNANTASENAMAT", serialized)
        self.assertNotIn("siArtifact", serialized)
        self.assertIn("REVENUE_PULSE_DB.DASHBOARD_DEMO.REVENUE_SEMANTIC_VIEW", serialized)

    def test_actions_panel_and_layout(self):
        self.assertEqual(len(TILES), 15)
        self.assertEqual(TILES["actions"]["title"], "Try Chart Actions")
        positions = MODULE.dash["layout"]["default"]["positions"]
        self.assertEqual(positions["header"], {"x": 0, "y": 0, "w": 7, "h": 2})
        self.assertEqual(positions["actions"], {"x": 7, "y": 0, "w": 5, "h": 2})

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