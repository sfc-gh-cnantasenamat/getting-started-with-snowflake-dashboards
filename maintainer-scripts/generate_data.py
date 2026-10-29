"""Generate fictional account/product/month revenue using integer cents."""

import argparse
import calendar
import csv
import hashlib
import json
import random
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGIONS = ("Americas", "EMEA", "APAC")
SEGMENTS = ("Enterprise", "Mid-market", "SMB")
PRODUCTS = (("P01", "Analytics Cloud", 100), ("P02", "Data Platform", 140),
            ("P03", "AI Studio", 70))


def month_offset(start, offset):
    ordinal = start.year * 12 + start.month - 1 + offset
    return date(ordinal // 12, ordinal % 12 + 1, 1)


def generate(config):
    start = date.fromisoformat(config["start_month"])
    if start.day != 1 or config["months"] < 15:
        raise ValueError("Use a first-of-month start and at least 15 months")
    last = month_offset(start, config["months"] - 1)
    cutoff = date(last.year, last.month, calendar.monthrange(last.year, last.month)[1])
    if cutoff.isoformat() != config["reporting_cutoff"]:
        raise ValueError("Reporting cutoff must match the last complete generated month")
    rng = random.Random(config["seed"])
    customers, facts = [], []
    for region_index, region in enumerate(REGIONS):
        for segment_index, segment in enumerate(SEGMENTS):
            for customer_index in range(6):
                customer_id = f"C{len(customers) + 1:03}"
                customer = {"customer_id": customer_id,
                            "customer_name": f"Demo {region} {segment} {customer_index + 1:02}",
                            "region": region, "segment": segment}
                customers.append(customer)
                base = (1800000, 600000, 150000)[segment_index]
                base += rng.randrange(0, base // 3)
                for product_id, product_name, weight in PRODUCTS:
                    for offset in range(config["months"]):
                        month = month_offset(start, offset)
                        season = (100, 98, 105, 102, 104, 110, 106, 108, 118, 108, 112, 125)[month.month - 1]
                        target = base * weight * (100 + 2 * offset) * season // 1000000
                        gross = target * (106 + rng.randrange(-3, 5)) // 100
                        discount = gross * 3 // 100
                        refund = gross // 200
                        reason = "NORMAL_TRADING"
                        if region == "EMEA" and segment == "Enterprise" and offset >= config["months"] - 3:
                            if customer_index < 2:
                                gross = target * 58 // 100
                                discount = gross * 3 // 100
                                refund = gross // 200
                                reason = "RECORDED_CONTRACT_DOWNSIZE"
                            elif customer_index < 4:
                                discount = gross * 25 // 100
                                refund = gross * 8 // 100
                                reason = "RECORDED_DISCOUNT_AND_SERVICE_CREDIT"
                            elif customer_index == 4:
                                gross = discount = refund = 0
                                reason = "RECORDED_RENEWAL_DELAY"
                        elif offset >= config["months"] - 3:
                            # Milder versions of the same drivers in every other slice, so each one
                            # shows all four; EMEA Enterprise stays by far the largest miss.
                            if customer_index == 0:
                                gross = target * 100 // 100
                                discount = gross * 3 // 100
                                refund = gross // 200
                                reason = "RECORDED_CONTRACT_DOWNSIZE"
                            elif customer_index == 1:
                                discount = gross * 5 // 100
                                refund = gross * 1 // 100
                                reason = "RECORDED_DISCOUNT_AND_SERVICE_CREDIT"
                            elif customer_index == 2 and product_id == "P03" and offset == config["months"] - 1:
                                gross = discount = refund = 0
                                reason = "RECORDED_RENEWAL_DELAY"
                            elif region != "EMEA":
                                # Mixed Q3 outside EMEA: Americas Enterprise beats target; the other segments
                                # miss by 12-35 points, each with a recorded driver.
                                factor, recorded = {
                                    ('Americas', 'Enterprise'): (1231, None),
                                    ('Americas', 'Mid-market'): (692, 'RECORDED_DISCOUNT_AND_SERVICE_CREDIT'),
                                    ('Americas', 'SMB'): (783, 'RECORDED_CONTRACT_DOWNSIZE'),
                                    ('APAC', 'Enterprise'): (827, 'RECORDED_CONTRACT_DOWNSIZE'),
                                    ('APAC', 'Mid-market'): (588, 'RECORDED_CONTRACT_DOWNSIZE'),
                                    ('APAC', 'SMB'): (498, 'RECORDED_DISCOUNT_AND_SERVICE_CREDIT')}[(region, segment)]
                                gross = gross * factor // 1000
                                reason = recorded or reason
                        net = gross - discount - refund
                        cost = net * (25 + region_index * 2 + rng.randrange(0, 5)) // 100
                        facts.append({"revenue_id": f"{customer_id}-{product_id}-{month:%Y%m}",
                                      "month": month.isoformat(), **customer,
                                      "product_id": product_id, "product_name": product_name,
                                      "gross_revenue_cents": gross, "discount_cents": discount,
                                      "refund_cents": refund, "cost_cents": cost,
                                      "target_cents": target, "recorded_driver": reason})
    return customers, [{"product_id": pid, "product_name": name} for pid, name, _ in PRODUCTS], facts


def summarize(rows):
    gross = sum(row["gross_revenue_cents"] for row in rows)
    discounts = sum(row["discount_cents"] for row in rows)
    refunds = sum(row["refund_cents"] for row in rows)
    net = gross - discounts - refunds
    target = sum(row["target_cents"] for row in rows)
    cost = sum(row["cost_cents"] for row in rows)
    return {"rows": len(rows), "net_revenue_cents": net, "target_cents": target,
            "variance_cents": net - target, "discount_cents": discounts,
            "refund_cents": refunds, "gross_profit_cents": net - cost,
            "attainment": net / target if target else None,
            "gross_margin": (net - cost) / net if net else None}


def ground_truth(facts):
    end = max(row["month"] for row in facts)
    last_month = date.fromisoformat(end)
    quarter_start = date(last_month.year, ((last_month.month - 1) // 3) * 3 + 1, 1)
    current = [row for row in facts if quarter_start.isoformat() <= row["month"] <= end]
    prior_start = quarter_start.replace(year=quarter_start.year - 1).isoformat()
    prior_end = last_month.replace(year=last_month.year - 1).isoformat()
    prior = [row for row in facts if prior_start <= row["month"] <= prior_end]
    slices = [{"region": region, "segment": segment,
               **summarize([row for row in current if row["region"] == region and row["segment"] == segment])}
              for region in REGIONS for segment in SEGMENTS]
    return {"period_start": quarter_start.isoformat(), "period_end_month": end,
            "current": summarize(current), "prior_year": summarize(prior),
            "region_segments": sorted(slices, key=lambda row: row["variance_cents"]),
            "emea_enterprise_accounts": [{"customer_id": customer_id,
                **summarize([row for row in current if row["customer_id"] == customer_id])}
                for customer_id in sorted({row["customer_id"] for row in current
                                           if row["region"] == "EMEA" and row["segment"] == "Enterprise"})]}


def write_outputs(config, destination):
    customers, products, facts = generate(config)
    destination.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name, rows in (("customers", customers), ("products", products), ("revenue_monthly", facts)):
        path = destination / f"{name}.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (destination / "expected_results.json").write_text(json.dumps(ground_truth(facts), indent=2) + "\n")
    (destination / "manifest.json").write_text(json.dumps({"synthetic": True, "config": config,
        "row_count": len(facts), "sha256": hashes}, indent=2) + "\n")
    return len(facts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "config/demo.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    print(f"Generated {write_outputs(json.loads(args.config.read_text()), args.output):,} synthetic revenue rows")