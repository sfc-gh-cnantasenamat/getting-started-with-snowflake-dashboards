"""Build dashboards/revenue_pulse.dash (native Dashboards 2.0 spec v2)."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config/demo.json").read_text())
FQ = f'{CONFIG["database"]}.{CONFIG["schema"]}'
SV = f'{FQ}.{CONFIG["semantic_view"]}'
FILTERS = ("MONTH", "REGION", "SEGMENT", "PRODUCT_NAME")
NUM, TXT, DATE = "NUMBER", "VARCHAR", "DATE"

# Muted five-step palette: red -> orange -> yellow -> blue -> teal (worst to best).
PALETTE = ["#C8524B", "#DD8459", "#E2C27A", "#5E8AC7", "#3E9F98"]
BLUE, TEAL = "#5B8DEF", "#3E9F98"
SLATE, INK = "#8a9bb0", "#14365d"
REGION_SCALE = {"domain": ["Americas", "EMEA", "APAC"], "range": [BLUE, "#4FA88A", "#E3C77A"]}
# Preserve the live dashboard's data-relative variance palette.
VARIANCE_SCALE = {"range": PALETTE, "interpolate": "rgb"}


DRILLS = {"DRILL_REGION": ["REGION", "SEGMENT", "CUSTOMER_NAME"], "DRILL_DRIVER": ["RECORDED_DRIVER", "CUSTOMER_NAME"]}
LEVEL_NAMES = {"REGION": "Region", "SEGMENT": "Segment", "CUSTOMER_NAME": "Account", "RECORDED_DRIVER": "Driver"}
DRILL_PATHS = [(f"{d}_{i + 1}", " || ' › ' || ".join(cols[:i + 1]))
               for d, cols in DRILLS.items() for i in range(len(cols))]


# Every query carries driver and account so chart actions can filter any tile by them.
def base(extra_dims=", revenue.recorded_driver, customers.customer_name", shift_year=False, metrics="revenue.net_revenue, revenue.revenue_target, "
         "revenue.gross_profit, revenue.total_discounts, revenue.total_refunds"):
    month = "DATEADD(YEAR, 1, MONTH) AS MONTH" if shift_year else "MONTH"
    # Drill paths: a bar click emits one path ("EMEA › Enterprise"); the drill filters match it
    # against these prefix columns.
    paths = ", ".join(f"{expr} AS {name}" for name, expr in DRILL_PATHS)
    return (f"SELECT *, {paths} FROM (\n    SELECT {month}, * EXCLUDE (MONTH) FROM SEMANTIC_VIEW(\n        {SV}\n"
            f"        DIMENSIONS revenue.month, customers.region, customers.segment, products.product_name{extra_dims}\n"
            f"        METRICS {metrics}))")


BRUSH = "{{ filter('BRUSH_MONTH', 'MONTH') }}"
# TRUE only while months are brushed: an empty filter renders TRUE, so no 1900 date fails it.
BRUSH_SET = f"EXISTS (SELECT 1 FROM (SELECT DATE '1900-01-01' AS MONTH) WHERE NOT ({BRUSH}))"


def where(ids=FILTERS, brush=True):
    # The trend brush is its own filter so an action never shadows the Period chip; while it is
    # set it replaces the Period (otherwise a brush outside the Period leaves every tile empty).
    clauses = [f"({{{{ filter('{i}') }}}} OR {BRUSH_SET})" if brush and i == "MONTH"
               else f"{{{{ filter('{i}') }}}}" for i in ids]
    if brush:
        clauses.append(BRUSH)
    for d, cols in DRILLS.items():
        clauses.append("(" + " OR ".join(f"{{{{ filter('{d}', '{d}_{i + 1}') }}}}" for i in range(len(cols))) + ")")
    return "WHERE " + "\n    AND ".join(clauses)


def datasource(sql, columns, ids=FILTERS, brush=True):
    bindings = list(ids)
    if brush:
        bindings.insert(bindings.index("MONTH") + 1 if "MONTH" in bindings else len(bindings), "BRUSH_MONTH")
    return {"type": "sql", "columns": [{"name": n, "type": t} for n, t in columns], "sql": sql,
            "filter_bindings": [{"filter_id": i} for i in (*bindings, *DRILLS)]}


# Variance sparkline: red below -$1.5M, yellow below target, green at or above it.
VARIANCE_THRESHOLDS = [{"slot": "alert", "comparator": "lt", "value": -1500000, "color": "red"},
                       {"slot": "warn", "comparator": "lt", "value": 0, "color": "yellow"},
                       {"slot": "good", "comparator": "gte", "value": 0, "color": "green"}]


def scorecard(title, label, decimals=1, increases_better=True, compare=True, thresholds=None):
    # Sparklines colour by trend direction (polarity), or by fixed bands when thresholds are given.
    sparkline = ({"sparklineColorMode": "threshold", "thresholdDirection": "higher-is-better",
                  "thresholds": thresholds} if thresholds else {"sparklineColorMode": "polarity"})
    return {"title": title, "type": "chart", "spec": {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json", "data": {"name": "values"},
        "usermeta": {"snowflake": {"chartType": "scorecard", "scorecardConfig": {
            "format": "decimal", "decimals": decimals, "abbreviate": True,
            "deltaColorMode": "increasesBetter" if increases_better else "decreasesBetter",
            "comparisonMode": "manual", "comparisonEnabled": compare,
            "prevColumn": "PRIOR_VALUE", "currentColumn": "CURRENT_VALUE",
            "displayFormat": "change", "sparklineEnabled": True, **sparkline,
            "seriesBucketField": "DS", "seriesBucketFieldType": "temporal", "seriesValueField": "SERIES_VALUE",
            "labelEnabled": True, "labelField": "", "labelText": label}}}}}


def kpi_sql(expression):
    """Current period vs the same months one year earlier, both under identical filters, plus a
    12-month sparkline series ending at the last selected month (other filters still apply)."""
    agg = ("SUM(NET_REVENUE) AS NET, SUM(REVENUE_TARGET) AS TGT, SUM(GROSS_PROFIT) AS GP")
    return (f"WITH cur_rows AS (\n    SELECT * FROM ({base()})\n    {where()}\n),\n"
            f"cur AS (SELECT {agg} FROM cur_rows),\n"
            f"py AS (\n    SELECT {agg} FROM ({base(shift_year=True)})\n    {where()}\n),\n"
            f"spark AS (\n    SELECT MONTH AS DS, {agg} FROM ({base()})\n"
            f"    {where(ids=FILTERS[1:], brush=False)}\n"
            f"    AND MONTH BETWEEN DATEADD(MONTH, -11, (SELECT MAX(MONTH) FROM cur_rows))"
            f" AND (SELECT MAX(MONTH) FROM cur_rows)\n    GROUP BY MONTH\n)\n"
            f"SELECT spark.DS, {expression.format(t='spark')} AS SERIES_VALUE,\n"
            f"    {expression.format(t='cur')} AS CURRENT_VALUE, {expression.format(t='py')} AS PRIOR_VALUE\n"
            f"FROM spark CROSS JOIN cur CROSS JOIN py\nORDER BY spark.DS")


def with_colorbar(spec, field, scale, fmt, title, domain=None, pre=()):
    """Draw the colour legend as a vertical gradient bar at the right edge of the plot.

    The dashboard renderer replaces Vega-Lite legends with discrete swatches, so the bar is an
    extra layer: 50 thin rects spanning the data range (or a fixed domain), coloured by the same
    scale as the chart, on its own scales so the chart itself is untouched.
    """
    if domain:
        lo_hi = [{"calculate": f"{domain[0]}", "as": "LO"}, {"calculate": f"{domain[1]}", "as": "HI"},
                 {"aggregate": [{"op": "count", "as": "N"}], "groupby": ["LO", "HI"]}]
    else:
        lo_hi = [{"aggregate": [{"op": "min", "field": field, "as": "LO"},
                                {"op": "max", "field": field, "as": "HI"}]}]
    bar = {"transform": list(pre) + lo_hi + [
        {"calculate": "sequence(0, 50)", "as": "I"}, {"flatten": ["I"]},
        {"calculate": "datum.LO + (datum.HI - datum.LO) * datum.I / 50", "as": "V"},
        {"calculate": "datum.LO + (datum.HI - datum.LO) * (datum.I + 1) / 50", "as": "V2"}],
        "mark": {"type": "rect"},
        "encoding": {
            "x": {"datum": 0, "axis": None,
                  "scale": {"domain": [0, 1], "range": [{"expr": "width - 14"}, {"expr": "width"}]}},
            "x2": {"datum": 1},
            "y": {"field": "V", "type": "quantitative", "title": title,
                  "scale": {"zero": False, "nice": False, "range": [{"expr": "height * 0.85"},
                                                                    {"expr": "height * 0.15"}]},
                  "axis": {"orient": "right", "offset": 4, "format": fmt, "tickCount": 4,
                           "grid": False, "domain": False, "titleAngle": 90}},
            "y2": {"field": "V2"},
            "color": {"field": "V", "type": "quantitative", "scale": scale, "legend": None}}}
    # The renderer clips marks to the plot area, so the bar sits inside it: narrow the chart's
    # x range to leave a strip on the right.
    x = spec["encoding"]["x"]
    x["scale"] = {**x.get("scale", {}), "range": [0, {"expr": "width - 28"}]}
    return {"layer": [spec, bar],
            "resolve": {"scale": {"x": "independent", "y": "independent", "color": "independent"},
                        "axis": {"x": "independent", "y": "independent"}}}


def drill_sql(drill, metrics):
    """Drilldown without a native drill feature: once the drill filter is set, show the first level
    that still has more than one value. Each bar carries its full path (e.g. DRILL_REGION), so a click sets the
    drill filter to that path and the chart re-queries one level deeper."""
    n = len(DRILLS[drill])
    cols = [f"{drill}_{i + 1}" for i in range(n)]
    # This chart's own drill filter, or a REGION/SEGMENT filter (e.g. a heatmap cell), moves it to the
    # first level that still splits. An unset filter renders TRUE, so each "is set" check has its own EXISTS.
    own = [c for c in DRILLS[drill] if c in ("REGION", "SEGMENT")]
    match = " OR ".join(f"{{{{ filter('{drill}', '{c}') }}}}" for c in cols)
    dummy = ", ".join(f"'§' AS {c}" for c in cols)
    checks = [f"EXISTS (SELECT 1 FROM (SELECT {dummy}) WHERE NOT ({match}))"] \
        + [f"EXISTS (SELECT 1 FROM (SELECT '§' AS {c}) WHERE NOT ({{{{ filter('{c}', '{c}') }}}}))" for c in own]
    drilled = "(" + " OR ".join(checks) + ")"
    level = f"CASE WHEN NOT {drilled} THEN 1 " \
        + " ".join(f"WHEN COUNT(DISTINCT {drill}_{i + 1}) > 1 THEN {i + 1}" for i in range(n - 1)) \
        + f" ELSE {n} END"
    path = "CASE L " + " ".join(f"WHEN {i + 1} THEN {drill}_{i + 1}" for i in range(n)) + " END"
    return (f"WITH f AS (\n    SELECT * FROM ({base()})\n    {where()}\n),\n"
            f"lvl AS (SELECT {level} AS L FROM f)\n"
            f"SELECT {path} AS {drill}, DECODE(L, {', '.join(f'{i + 1}, {LEVEL_NAMES[c]!r}' for i, c in enumerate(DRILLS[drill]))}) AS LEVEL,\n"
            f"    {metrics}\nFROM f CROSS JOIN lvl\nGROUP BY 1, L\nORDER BY VARIANCE")


# Axis labels show only the last part of a drill path.
LAST_PART = "peek(split(datum.label, ' › '))"


VARIANCE_METRICS = ("SUM(NET_REVENUE) AS NET_REVENUE, SUM(REVENUE_TARGET) AS REVENUE_TARGET,\n"
                    "    SUM(NET_REVENUE) - SUM(REVENUE_TARGET) AS VARIANCE,\n"
                    "    DIV0NULL(SUM(NET_REVENUE), SUM(REVENUE_TARGET)) AS ATTAINMENT")
KPI_COLUMNS = [("DS", DATE), ("SERIES_VALUE", NUM), ("CURRENT_VALUE", NUM), ("PRIOR_VALUE", NUM)]
tiles, datasources, layout = [], {}, {}


def add(tile_id, tile, position, ds=None):
    tile = {"tile_id": tile_id, **tile}
    if ds:
        datasources[f"ds-{tile_id}"] = ds
        tile["datasources"] = [f"ds-{tile_id}"]
    tiles.append(tile)
    layout[tile_id] = dict(zip("xywh", position))


add("header", {"type": "text", "text": (
    "# Revenue Pulse\n**Synthetic demo data** for a fictional B2B software company, complete through "
    f"**{CONFIG['reporting_cutoff']}**.\n\n"
    "Net revenue = gross revenue minus discounts and refunds. Attainment = net revenue / target. "
    "Year-over-year compares the same filtered months one year earlier. Default view: Q3 2026.")}, (0, 0, 7, 2))

add("actions", {"title": "Try Chart Actions", "type": "text", "text": (
    "- **Drag** across months in **Monthly Net Revenue** to zoom and filter every tile.\n"
    "- **Click** a region bar in **Variance to Target by Region** to drill into segments, then accounts.\n"
    "- **Click** a cell in **Target Attainment** to filter the dashboard by that region and segment.")}, (7, 0, 5, 2))

add("kpi-net-revenue", scorecard("Net Revenue", "USD, vs same period last year"), (0, 2, 3, 2),
    datasource(kpi_sql("{t}.NET"), KPI_COLUMNS))
add("kpi-attainment", scorecard("Target Attainment", "% of target, vs last year"), (3, 2, 3, 2),
    datasource(kpi_sql("100 * DIV0NULL({t}.NET, {t}.TGT)"), KPI_COLUMNS))
add("kpi-variance", scorecard("Variance to Target", "USD, net revenue minus target", decimals=0, compare=False,
                                   thresholds=VARIANCE_THRESHOLDS), (6, 2, 3, 2),
    datasource(kpi_sql("{t}.NET - {t}.TGT"), KPI_COLUMNS))
add("kpi-margin", scorecard("Gross Margin", "% of net revenue, vs last year"), (9, 2, 3, 2),
    datasource(kpi_sql("100 * DIV0NULL({t}.GP, {t}.NET)"), KPI_COLUMNS))

# Trend ignores the date filter on purpose so the selected period is seen in 24-month context.
trend_ids = FILTERS[1:]
add("trend", {"title": "Monthly Net Revenue vs Target (Drag across months to zoom and filter)", "type": "chart", "spec": {
    "transform": [{"fold": ["NET_REVENUE", "REVENUE_TARGET"], "as": ["SERIES", "VALUE"]},
                  {"calculate": "datum.SERIES === 'NET_REVENUE' ? 'Net revenue' : 'Target'", "as": "SERIES_LABEL"}],
    # Non-zero axis makes the gap between net revenue and target visible.
    "encoding": {"x": {"field": "MONTH", "type": "temporal", "title": "Month"},
                 "y": {"field": "VALUE", "type": "quantitative", "title": "USD", "stack": None,
                       "scale": {"zero": False}, "axis": {"format": "$,.2s"}},
                 "color": {"field": "SERIES_LABEL", "type": "nominal", "title": None,
                           "scale": {"domain": ["Net revenue", "Target"], "range": [BLUE, TEAL]}},
                 "fillOpacity": {"condition": {"test": "datum.SERIES === 'NET_REVENUE'", "value": 0.3},
                                 "value": 0},
                 "tooltip": [{"field": "MONTH", "type": "temporal", "format": "%b %Y"},
                             {"field": "SERIES_LABEL", "title": "Series"},
                             {"field": "VALUE", "type": "quantitative", "format": "$,.0f"}]},
    # Single layer so the dashboard attaches its own drag brush (it ignores brushes on layered specs).
    # Area mark with an outline for both series; Target gets no fill, so it reads as a line.
    "mark": {"type": "area", "interpolate": "monotone", "clip": True,
             "line": {"strokeWidth": 2.5}, "point": True}}},
    (0, 4, 12, 4),
    datasource(f"SELECT MONTH, SUM(NET_REVENUE) AS NET_REVENUE, SUM(REVENUE_TARGET) AS REVENUE_TARGET\n"
               f"FROM ({base()})\n{where(trend_ids)}\nGROUP BY MONTH\nORDER BY MONTH",
               [("MONTH", DATE), ("NET_REVENUE", NUM), ("REVENUE_TARGET", NUM)], trend_ids))

add("by-region", {"title": "Variance to Target by Region (Click a Region to drill the charts below)",
                  "type": "chart", "spec": {
    "mark": {"type": "bar", "cornerRadiusEnd": 3},
    "encoding": {"y": {"field": "DRILL_REGION", "type": "nominal", "sort": "x", "title": None,
                       "axis": {"labelExpr": LAST_PART, "labelLimit": 180}},
                 "x": {"field": "VARIANCE", "type": "quantitative", "title": "USD vs target", "axis": {"format": "$,.2s"}},
                 "color": {"field": "VARIANCE", "type": "quantitative", "title": "Variance",
                           "scale": VARIANCE_SCALE, "legend": None},
                 "tooltip": [{"field": "LEVEL", "title": "Level"}, {"field": "DRILL_REGION", "title": "Path"},
                             {"field": "NET_REVENUE", "type": "quantitative", "format": "$,.0f", "title": "Net revenue"},
                             {"field": "REVENUE_TARGET", "type": "quantitative", "format": "$,.0f", "title": "Target"},
                             {"field": "VARIANCE", "type": "quantitative", "format": "$,.0f", "title": "Variance"},
                             {"field": "ATTAINMENT", "type": "quantitative", "format": ".1%", "title": "Attainment"}]}}},
    (0, 8, 6, 4),
    datasource(drill_sql("DRILL_REGION", VARIANCE_METRICS),
               [("DRILL_REGION", TXT), ("LEVEL", TXT), ("NET_REVENUE", NUM), ("REVENUE_TARGET", NUM),
                ("VARIANCE", NUM), ("ATTAINMENT", NUM)]))

# Palette fixed on 55-120% attainment: deep misses red, ~88% yellow, beating target teal.
HEATMAP_SCALE = {"range": PALETTE, "domain": [0.55, 0.7125, 0.875, 1.0375, 1.2], "clamp": True, "interpolate": "rgb"}
HEAT_PRE = [{"calculate": "datum.ATTAINMENT", "as": "HEAT"}]
add("heatmap", {"title": "Target Attainment (Click a cell to filter by Region and Segment)", "type": "chart", "spec": {
    "transform": HEAT_PRE + [{"joinaggregate": [{"op": "min", "field": "HEAT", "as": "HEAT_LO"},
                                                {"op": "max", "field": "HEAT", "as": "HEAT_HI"}]}],
    "layer": [
        {"mark": {"type": "rect", "stroke": "black", "strokeWidth": 2},
         "encoding": {"color": {"field": "HEAT", "type": "quantitative", "title": "Attainment",
                                "scale": HEATMAP_SCALE,
                                "legend": None}}},
        {"mark": {"type": "text", "fontWeight": "bold"},
         "encoding": {"text": {"field": "ATTAINMENT", "type": "quantitative", "format": ".1%"},
                      "color": {"condition": {"test": "datum.ATTAINMENT < 0.68 || datum.ATTAINMENT > 1.12", "value": "white"},
                                "value": INK}}}],
    "encoding": {"x": {"field": "SEGMENT", "type": "nominal", "title": None, "sort": ["Enterprise", "Mid-market", "SMB"],
                       "axis": {"labelAngle": 0}},
                 "y": {"field": "REGION", "type": "nominal", "title": None},
                 "tooltip": [{"field": "REGION"}, {"field": "SEGMENT"},
                             {"field": "ATTAINMENT", "type": "quantitative", "format": ".1%"},
                             {"field": "VARIANCE", "type": "quantitative", "format": "$,.0f"}]}}},
    (6, 8, 6, 4),
    datasource(f"SELECT REGION, SEGMENT, DIV0NULL(SUM(NET_REVENUE), SUM(REVENUE_TARGET)) AS ATTAINMENT,\n"
               f"    SUM(NET_REVENUE) - SUM(REVENUE_TARGET) AS VARIANCE\n"
               f"FROM ({base()})\n{where()}\nGROUP BY REGION, SEGMENT",
               [("REGION", TXT), ("SEGMENT", TXT), ("ATTAINMENT", NUM), ("VARIANCE", NUM)]))

add("drivers", {"title": "What Sales Ops Recorded: Variance by Driver", "type": "chart",
                "spec": json.loads((ROOT / "config/chart_specs/drivers.json").read_text())},
    (0, 12, 6, 4),
    datasource(drill_sql("DRILL_DRIVER",
                         "SUM(NET_REVENUE) - SUM(REVENUE_TARGET) AS VARIANCE,\n"
                         "    SUM(TOTAL_DISCOUNTS) AS DISCOUNTS, SUM(TOTAL_REFUNDS) AS REFUNDS, "
                         "COUNT(DISTINCT CUSTOMER_NAME) AS ACCOUNTS"),
               [("DRILL_DRIVER", TXT), ("LEVEL", TXT), ("VARIANCE", NUM), ("DISCOUNTS", NUM),
                ("REFUNDS", NUM), ("ACCOUNTS", NUM)]))

# Waterfall: start on target (zero variance), step through each recorded driver, end at the total gap.
add("waterfall", {"title": "Variance Bridge: How Each Recorded Driver Moves Us vs Target", "type": "chart", "spec": {
    "layer": [
        {"mark": {"type": "bar", "width": {"band": 0.6}},
         "encoding": {"y": {"field": "START_VALUE", "type": "quantitative", "title": "USD vs target",
                           "axis": {"format": "$,.2s"}},
                     "y2": {"field": "END_VALUE"},
                     "color": {"field": "AMOUNT", "type": "quantitative", "title": "Amount",
                               "scale": VARIANCE_SCALE, "legend": None}}},
        {"mark": {"type": "rule", "color": SLATE}, "encoding": {"y": {"datum": 0}}},
        # Connector: a dashed level line from each step's end to the next step's start.
        {"transform": [{"filter": "datum.KIND !== 'Total'"}],
         "mark": {"type": "rule", "strokeDash": [3, 3], "color": SLATE, "xOffset": {"expr": "bandwidth('x') * 0.3"},
                  "x2Offset": {"expr": "-bandwidth('x') * 0.3"}},
         "encoding": {"y": {"field": "END_VALUE", "type": "quantitative"},
                      "x2": {"field": "NEXT_STEP"}}},
        # Labels sit on the outside end of each bar: above increases, below decreases.
        {"mark": {"type": "text", "fontSize": 11, "color": SLATE,
                  "dy": {"expr": "datum.AMOUNT < 0 ? 10 : -8"}},
         "encoding": {"y": {"field": "LABEL_Y", "type": "quantitative"},
                     "text": {"field": "AMOUNT", "type": "quantitative", "format": "$,.3s"}}}],
    "encoding": {"x": {"field": "STEP", "type": "nominal", "title": None, "sort": {"field": "STEP_ORDER"},
                       "axis": {"labelAngle": 0, "labelOverlap": False, "labelLineHeight": 14,
                                "labelExpr": "[substring(datum.label, 0, indexof(datum.label, ' ')), substring(datum.label, indexof(datum.label, ' ') + 1)]"}},
                 "tooltip": [{"field": "STEP", "title": "Step"},
                             {"field": "AMOUNT", "type": "quantitative", "format": "$,.0f", "title": "Amount"},
                             {"field": "END_VALUE", "type": "quantitative", "format": "$,.0f", "title": "Running variance"}]}}},
    (6, 12, 6, 4),
    datasource(f"WITH d AS (\n    SELECT RECORDED_DRIVER, SUM(NET_REVENUE) - SUM(REVENUE_TARGET) AS V\n"
               f"    FROM ({base()})\n    {where()}\n    GROUP BY RECORDED_DRIVER\n),\n"
               f"steps AS (\n"
               f"    SELECT ROW_NUMBER() OVER (ORDER BY V DESC) AS STEP_ORDER,\n"
               f"        DECODE(RECORDED_DRIVER, 'NORMAL_TRADING', 'Normal trading', 'RECORDED_RENEWAL_DELAY', 'Renewal delay',\n"
               f"            'RECORDED_CONTRACT_DOWNSIZE', 'Contract downsize', 'RECORDED_DISCOUNT_AND_SERVICE_CREDIT', 'Discounts & credits',\n"
               f"            RECORDED_DRIVER) AS STEP,\n"
               f"        IFF(V < 0, 'Decrease', 'Increase') AS KIND,\n"
               f"        COALESCE(SUM(V) OVER (ORDER BY V DESC ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0) AS START_VALUE,\n"
               f"        SUM(V) OVER (ORDER BY V DESC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS END_VALUE,\n"
               f"        V AS AMOUNT\n    FROM d\n"
               f"    UNION ALL\n"
               f"    SELECT 99, 'Total variance', 'Total', 0, SUM(V), SUM(V) FROM d\n)\n"
               f"SELECT STEP_ORDER, STEP, KIND, START_VALUE, END_VALUE, AMOUNT,\n"
               f"    IFF(AMOUNT < 0, LEAST(START_VALUE, END_VALUE), GREATEST(START_VALUE, END_VALUE)) AS LABEL_Y,\n"
               f"    LEAD(STEP) OVER (ORDER BY STEP_ORDER) AS NEXT_STEP\n"
               f"FROM steps\nORDER BY STEP_ORDER",
               [("STEP_ORDER", NUM), ("STEP", TXT), ("KIND", TXT), ("START_VALUE", NUM), ("END_VALUE", NUM),
                ("AMOUNT", NUM), ("LABEL_Y", NUM), ("NEXT_STEP", TXT)]))

# Bubble: one point per account. Position shows size of book vs attainment; area shows net revenue.
add("bubble", {"title": "Accounts: Target vs Attainment (bubble size = net revenue)", "type": "chart", "spec": {
    "layer": [
        {"mark": {"type": "rule", "strokeDash": [4, 4], "color": SLATE},
         "encoding": {"y": {"datum": 1}}},
        {"mark": {"type": "circle", "opacity": 0.75, "stroke": "white", "strokeWidth": 1},
         "encoding": {"x": {"field": "REVENUE_TARGET", "type": "quantitative", "title": "Target (USD)",
                           "axis": {"format": "$,.2s"},
                           # fit the data instead of rounding out to whole decades
                           "scale": {"type": "log", "nice": False, "padding": 48}},
                     "y": {"field": "ATTAINMENT", "type": "quantitative", "title": "Attainment",
                           # pow scale gives the busy band around 100% more room
                           "axis": {"format": ".0%", "values": [0, 0.5, 0.7, 0.8, 0.9, 1.0, 1.05], "labelOverlap": False},
                           "scale": {"type": "pow", "exponent": 4, "domain": [0, 1.07], "nice": False}},
                     "size": {"field": "NET_REVENUE", "type": "quantitative", "title": "Net revenue",
                              "scale": {"range": [20, 900]}, "legend": None},
                     "color": {"field": "REGION", "type": "nominal", "title": "Region", "scale": REGION_SCALE},
                     "tooltip": [{"field": "CUSTOMER_NAME", "title": "Account"}, {"field": "SEGMENT"},
                                 {"field": "NET_REVENUE", "type": "quantitative", "format": "$,.0f", "title": "Net revenue"},
                                 {"field": "REVENUE_TARGET", "type": "quantitative", "format": "$,.0f", "title": "Target"},
                                 {"field": "ATTAINMENT", "type": "quantitative", "format": ".1%"}]}}]}},
    (0, 16, 8, 5),
    datasource(f"SELECT CUSTOMER_NAME, REGION, SEGMENT, SUM(NET_REVENUE) AS NET_REVENUE,\n"
               f"    SUM(REVENUE_TARGET) AS REVENUE_TARGET,\n"
               f"    DIV0NULL(SUM(NET_REVENUE), SUM(REVENUE_TARGET)) AS ATTAINMENT\n"
               f"FROM ({base()})\n{where()}\n"
               f"GROUP BY CUSTOMER_NAME, REGION, SEGMENT",
               [("CUSTOMER_NAME", TXT), ("REGION", TXT), ("SEGMENT", TXT), ("NET_REVENUE", NUM),
                ("REVENUE_TARGET", NUM), ("ATTAINMENT", NUM)]))

add("ask", {"type": "text", "text": (
    "### Ask Revenue Advisor\nOnce published to CoWork, use the chat box below this dashboard. Try:\n"
    "- *Why is EMEA Enterprise behind target in Q3 2026? Quantify the drivers.*\n"
    "- *Which accounts contributed most to the Q3 shortfall?*\n"
    "- *Will the renewal-delayed revenue recover in Q4?*\n"
    "- *How much of the gap is associated with discounts and refunds?*\n\n"
    "Drivers come from the `RECORDED_DRIVER` field logged by sales ops. They are recorded reasons, not inferred causes.")},
    (8, 16, 4, 5))

add("accounts", {"title": "Account Detail (sorted by variance)", "type": "table", "spec": {"columns": [
    {"field": "CUSTOMER_NAME", "label": "Account"}, {"field": "REGION", "label": "Region"},
    {"field": "SEGMENT", "label": "Segment"}, {"field": "NET_REVENUE", "label": "Net revenue (USD)"},
    {"field": "REVENUE_TARGET", "label": "Target (USD)"}, {"field": "VARIANCE", "label": "Variance (USD)"},
    {"field": "ATTAINMENT_PCT", "label": "Attainment %"}, {"field": "GROSS_MARGIN_PCT", "label": "Gross margin %"},
    {"field": "TOP_DRIVER", "label": "Recorded driver"}]}},
    (0, 21, 12, 6),
    datasource(f"SELECT CUSTOMER_NAME, REGION, SEGMENT, ROUND(SUM(NET_REVENUE), 0) AS NET_REVENUE,\n"
               f"    ROUND(SUM(REVENUE_TARGET), 0) AS REVENUE_TARGET,\n"
               f"    ROUND(SUM(NET_REVENUE) - SUM(REVENUE_TARGET), 0) AS VARIANCE,\n"
               f"    ROUND(100 * DIV0NULL(SUM(NET_REVENUE), SUM(REVENUE_TARGET)), 1) AS ATTAINMENT_PCT,\n"
               f"    ROUND(100 * DIV0NULL(SUM(GROSS_PROFIT), SUM(NET_REVENUE)), 1) AS GROSS_MARGIN_PCT,\n"
               f"    MAX_BY(RECORDED_DRIVER, ABS(REVENUE_TARGET - NET_REVENUE)) AS TOP_DRIVER\n"
               f"FROM ({base()})\n{where()}\n"
               f"GROUP BY CUSTOMER_NAME, REGION, SEGMENT\nORDER BY VARIANCE\nLIMIT 100",
               [("CUSTOMER_NAME", TXT), ("REGION", TXT), ("SEGMENT", TXT), ("NET_REVENUE", NUM),
                ("REVENUE_TARGET", NUM), ("VARIANCE", NUM), ("ATTAINMENT_PCT", NUM),
                ("GROSS_MARGIN_PCT", NUM), ("TOP_DRIVER", TXT)]))

COLORBARS = {"heatmap": ("HEAT", HEATMAP_SCALE, ".0%", "Attainment", (0.55, 1.2), HEAT_PRE),
             "by-region": ("VARIANCE", VARIANCE_SCALE, "$,.2s", "Variance", None),
             "waterfall": ("AMOUNT", VARIANCE_SCALE, "$,.2s", "Amount", None)}
for t in tiles:
    if t["tile_id"] in COLORBARS:
        t["spec"] = with_colorbar(t["spec"], *COLORBARS[t["tile_id"]])


# Chart actions. by-region sits outside every scope, so it stays at region level while its click
# drills the other tiles (e.g. drivers) one level deeper. "main" holds the other data tiles, so a write there re-queries the whole dashboard;
# "detail" (bubble, table, drivers) is a child scope, so driver clicks stay local to it.
# A filter sent to a scope also reaches its child scopes. The heatmap and the region chart each sit
# in their own scope so their clicks can filter each other (and everything else) but never themselves.
SCOPES = {"main": {}, "detail": {"parent": "main"}, "heat": {}, "region": {}}
TILE_SCOPE = {t: "main" for t in ("kpi-net-revenue", "kpi-attainment", "kpi-variance", "kpi-margin",
                                  "trend", "waterfall")}
TILE_SCOPE.update({t: "detail" for t in ("drivers", "bubble", "accounts")})
TILE_SCOPE.update({"heatmap": "heat", "by-region": "region"})


def set_filter(scopes, *fields):
    scopes = [scopes] if isinstance(scopes, str) else scopes
    return {"trigger": "select", "fields": list(fields), "operator": "set_filter",
            "targets": [{"scope": sc, "fields": [f], "filter": f} for sc in scopes for f in fields]}


INTERACTIONS = {
    # Drilldown: a region click narrows every other tile, e.g. drivers show what was recorded in EMEA.
    "by-region": [set_filter(["main", "heat"], "DRILL_REGION")],
    "heatmap": [set_filter(["main", "region"], "REGION", "SEGMENT")],
    # Drag across the trend to pick a date range (the trend itself ignores the date filter).
    "trend": [{"trigger": "select", "fields": ["MONTH"], "operator": "set_filter",
               "targets": [{"scope": sc, "fields": ["MONTH"], "filter": "BRUSH_MONTH"}
                           for sc in ("main", "heat", "region")]}],
}
for t in tiles:
    if t["tile_id"] in TILE_SCOPE:
        t["scope"] = TILE_SCOPE[t["tile_id"]]
    if t["tile_id"] in INTERACTIONS:
        t["interactions"] = INTERACTIONS[t["tile_id"]]


def options(table, column):
    return {"source": "column", "table": f"{FQ}.{table}", "column": column}


# Footer: where every tile's numbers come from.
add("source", {"type": "text", "text": (
    f"Source: Database/Schema: `{FQ}` | Semantic View: `{CONFIG['semantic_view']}` | Tables: `REVENUE_MONTHLY` "
    "(monthly revenue, targets, and recorded drivers), `CUSTOMERS` (region and segment), and `PRODUCTS`.")},
    (0, 27, 12, 1))


dash = {
    "spec_version": 2, "spec_revision": 5, "version": 2, "title": "Revenue Pulse",
    "tabs": [{"order": 0, "tab_id": "default", "title": "Overview", "tiles": tiles}],
    "filters": {
        "MONTH": {"label": "Period", "mode": "range", "valueType": "DATE",
                  "default_values": ["2026-07-01", "2026-09-01"]},
        "REGION": {"label": "Region", "mode": "multi_select", "valueType": "STRING", "options": options("CUSTOMERS", "REGION")},
        "SEGMENT": {"label": "Segment", "mode": "multi_select", "valueType": "STRING", "options": options("CUSTOMERS", "SEGMENT")},
        "PRODUCT_NAME": {"label": "Product", "mode": "multi_select", "valueType": "STRING",
                         "options": options("PRODUCTS", "PRODUCT_NAME")},
        "BRUSH_MONTH": {"label": "Months picked on trend", "mode": "range", "valueType": "DATE", "default_values": []},
        # Set by clicking the drill charts; clear the chip to drill back up.
        "DRILL_REGION": {"label": "Drill: region path", "mode": "single_select", "valueType": "STRING",
                         "default_values": [], "options": options("CUSTOMERS", "REGION")},
        "DRILL_DRIVER": {"label": "Drill: driver path", "mode": "single_select", "valueType": "STRING",
                         "default_values": [], "options": options("REVENUE_MONTHLY", "RECORDED_DRIVER")}},
    "scopes": SCOPES,
    "layout": {"default": {"meta": {"default": True}, "positions": layout}},
    "datasources": datasources,
}

# Keep native editor-generated scorecard rendering and animation intact.
for tile in tiles:
    if tile["tile_id"] in ("kpi-net-revenue", "kpi-variance"):
        native = json.loads((ROOT / "config/chart_specs" / f"{tile['tile_id']}.json").read_text())
        native_config = native["usermeta"]["snowflake"]["scorecardConfig"]
        expected = tile["spec"]["usermeta"]["snowflake"]["scorecardConfig"]
        if any(native_config.get(key) != value for key, value in expected.items()):
            raise ValueError(f"Update the native scorecard spec for {tile['tile_id']} to match its configuration")
        tile["spec"] = native

if __name__ == "__main__":
    out = ROOT / "dashboards/revenue_pulse.dash"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(dash, indent=2) + "\n")
    print(f"Wrote {out} with {len(tiles)} tiles and {len(datasources)} datasources")
