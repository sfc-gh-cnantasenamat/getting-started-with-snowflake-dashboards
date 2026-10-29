import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("generate_data", ROOT / "maintainer-scripts/generate_data.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RevenueDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((ROOT / "config/demo.json").read_text())
        cls.customers, cls.products, cls.facts = MODULE.generate(cls.config)
        cls.truth = MODULE.ground_truth(cls.facts)

    def test_complete_unique_grain(self):
        self.assertEqual(len(self.facts), 54 * 3 * 24)
        self.assertEqual(len({row["revenue_id"] for row in self.facts}), len(self.facts))

    def test_dimensions(self):
        self.assertEqual(len(self.customers), 54)
        self.assertEqual(len(self.products), 3)
        self.assertEqual({row["customer_id"] for row in self.facts}, {row["customer_id"] for row in self.customers})

    def test_dates(self):
        self.assertEqual(min(row["month"] for row in self.facts), "2024-10-01")
        self.assertEqual(max(row["month"] for row in self.facts), "2026-09-01")

    def test_nonnegative_components(self):
        for row in self.facts:
            self.assertGreaterEqual(row["gross_revenue_cents"] - row["discount_cents"] - row["refund_cents"], 0)
            self.assertGreater(row["target_cents"], 0)

    def test_growth_and_shortfall_story(self):
        current = self.truth["current"]
        self.assertLess(current["variance_cents"], 0)
        self.assertGreater(current["net_revenue_cents"], self.truth["prior_year"]["net_revenue_cents"])
        worst = self.truth["region_segments"][0]
        self.assertEqual((worst["region"], worst["segment"]), ("EMEA", "Enterprise"))

    def test_contributions_reconcile(self):
        self.assertEqual(sum(row["variance_cents"] for row in self.truth["region_segments"]), self.truth["current"]["variance_cents"])
        self.assertEqual(sum(row["variance_cents"] for row in self.truth["emea_enterprise_accounts"]), self.truth["region_segments"][0]["variance_cents"])

    def test_target_only_periods_retained(self):
        delayed = [row for row in self.facts if row["recorded_driver"] == "RECORDED_RENEWAL_DELAY"]
        self.assertEqual(len(delayed), 17)
        self.assertTrue(all(row["gross_revenue_cents"] == 0 and row["target_cents"] > 0 for row in delayed))

    def test_empty_and_weighted_ratios(self):
        self.assertIsNone(MODULE.summarize([])["gross_margin"])
        self.assertIsNone(MODULE.summarize([])["attainment"])
        result = MODULE.summarize(self.facts)
        self.assertEqual(result["gross_margin"], result["gross_profit_cents"] / result["net_revenue_cents"])

    def test_reproducibility(self):
        with tempfile.TemporaryDirectory() as temporary:
            first, second = Path(temporary) / "first", Path(temporary) / "second"
            MODULE.write_outputs(self.config, first)
            MODULE.write_outputs(self.config, second)
            for path in first.iterdir():
                self.assertEqual(path.read_bytes(), (second / path.name).read_bytes())

    def test_cutoff_validation(self):
        with self.assertRaises(ValueError):
            MODULE.generate({**self.config, "reporting_cutoff": "2026-09-29"})


if __name__ == "__main__":
    unittest.main()