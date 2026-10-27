"""Build a compact Revenue Pulse: no explanatory text tiles, two tabs."""
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build_dashboard as full  # noqa: E402

TABS = [("default", "Overview"), ("drill", "Drill Down")]
LAYOUT = {
    "default": {
        "kpi-net-revenue": (0, 0, 3, 2), "kpi-attainment": (3, 0, 3, 2),
        "kpi-variance": (6, 0, 3, 2), "kpi-margin": (9, 0, 3, 2),
        "trend": (0, 2, 12, 4),
        "by-region": (0, 6, 6, 4), "heatmap": (6, 6, 6, 4),
        "drivers": (0, 10, 6, 4), "waterfall": (6, 10, 6, 4),
        "bubble": (0, 14, 12, 5),
    },
    "drill": {
        "geo-drill": (0, 0, 4, 6), "geo-drill-rows": (4, 0, 8, 6),
        "geo-table": (0, 6, 12, 8),
    },
}

tiles = {t["tile_id"]: t for tab in full.dash["tabs"] for t in tab["tiles"]}
dash = copy.deepcopy({k: v for k, v in full.dash.items() if k not in ("tabs", "layout", "datasources")})
dash["title"] = "Revenue Pulse (Compact)"
dash["tabs"] = [{"order": i, "tab_id": tab_id, "title": title,
                 "tiles": [copy.deepcopy(tiles[t]) for t in LAYOUT[tab_id]]}
                for i, (tab_id, title) in enumerate(TABS)]
dash["layout"] = {tab_id: {"meta": {"default": True} if tab_id == "default" else {},
                           "positions": {t: dict(zip("xywh", pos)) for t, pos in LAYOUT[tab_id].items()}}
                  for tab_id, _ in TABS}
used = {ds for tab in dash["tabs"] for t in tab["tiles"] for ds in t.get("datasources", [])}
dash["datasources"] = {k: v for k, v in full.datasources.items() if k in used}

if __name__ == "__main__":
    out = full.ROOT / "dashboards/revenue_pulse_compact.dash"
    out.write_text(json.dumps(dash, indent=2) + "\n")
    print(f"Wrote {out} with {sum(len(t['tiles']) for t in dash['tabs'])} tiles")
