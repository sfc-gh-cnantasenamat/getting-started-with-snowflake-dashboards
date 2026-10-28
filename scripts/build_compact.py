"""Build dashboards/revenue_pulse.dash: the compact Revenue Pulse (no how-to tiles)."""
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build_dashboard as full  # noqa: E402

TABS = [("default", "Overview"), ("hierarchy", "Hierarchical Chart"), ("hierarchy_table", "Hierarchical Table"),
        ("source", "Data Source")]
LAYOUT = {
    "default": {
        "header": (0, 0, 12, 2),
        "kpi-net-revenue": (0, 2, 3, 2), "kpi-attainment": (3, 2, 3, 2),
        "kpi-variance": (6, 2, 3, 2), "kpi-margin": (9, 2, 3, 2),
        "trend": (0, 4, 12, 4),
        "by-region": (0, 8, 6, 4), "heatmap": (6, 8, 6, 4),
        "drivers": (0, 12, 6, 4), "waterfall": (6, 12, 6, 4),
        "bubble": (0, 16, 12, 5),
    },
    "hierarchy": {"geo-drill": (0, 0, 4, 6), "geo-drill-rows": (4, 0, 8, 6)},
    "hierarchy_table": {"geo-table": (0, 0, 12, 8)},
    "source": {"source": (0, 0, 6, 4), "ask": (6, 0, 6, 4)},
}

tiles = {t["tile_id"]: t for tab in full.dash["tabs"] for t in tab["tiles"]}
dash = copy.deepcopy({k: v for k, v in full.dash.items() if k not in ("tabs", "layout", "datasources")})
dash["title"] = "Revenue Pulse"
dash["tabs"] = [{"order": i, "tab_id": tab_id, "title": title,
                 "tiles": [copy.deepcopy(tiles[t]) for t in LAYOUT[tab_id]]}
                for i, (tab_id, title) in enumerate(TABS)]
dash["layout"] = {tab_id: {"meta": {"default": True} if tab_id == "default" else {},
                           "positions": {t: dict(zip("xywh", pos)) for t, pos in LAYOUT[tab_id].items()}}
                  for tab_id, _ in TABS}
used = {ds for tab in dash["tabs"] for t in tab["tiles"] for ds in t.get("datasources", [])}
dash["datasources"] = {k: v for k, v in full.datasources.items() if k in used}

if __name__ == "__main__":
    out = full.ROOT / "dashboards/revenue_pulse.dash"
    out.write_text(json.dumps(dash, indent=2) + "\n")
    print(f"Wrote {out} with {sum(len(t['tiles']) for t in dash['tabs'])} tiles")
    # Part 1's copy points at a different schema; rerun build_getting_started.py.
