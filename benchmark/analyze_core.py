import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

RESULTS = Path(sys.argv[1] if len(sys.argv) > 1 else "results/core")
COLORS = {"gunicorn": "#eb6834", "fastapi": "#1baf7a"}
MAX_ERRORS, CPU_SAVING, ORDER_SLOWDOWN = 1.0, 0.30, 1.10
FLOWS = {
    "market_data": ("Market data in", "refresh every T s", 5, "age_p95_s", "quote age p95, s"),
    "orders": ("Order entry", "orders at once", 50, "p95_ms", "p95, ms"),
    "valuation_stream": ("Valuation stream", "subscribers", 200, "delivery_p95_ms", "delivery p95, ms"),
}
OPERATION = {"market_data": "refresh", "orders": "order", "valuation_stream": "update"}


def market_data_run(point):
    before, after = point["result"]["before"], point["result"]["after"]
    delta = {key: after[key] - before[key] for key in ("due", "completed", "errors")}
    window = [age for t, age in after["age_p95"] if before["elapsed"] <= t < after["elapsed"]]
    return {"on_time_pct": 100 * delta["completed"] / delta["due"], "age_p95_s": max(window),
            "errors_pct": 100 * delta["errors"] / max(delta["completed"] + delta["errors"], 1),
            "ops_per_s": delta["completed"] / (after["elapsed"] - before["elapsed"])}


def orders_run(point):
    report = point["result"]
    codes = report["statusCodeDistribution"]
    ok = sum(n for code, n in codes.items() if code.startswith("2"))
    failed = sum(n for code, n in codes.items() if not code.startswith("2"))
    failed += sum(n for kind, n in report["errorDistribution"].items() if kind != "aborted due to deadline")
    return {"p95_ms": 1000 * report["latencyPercentiles"]["p95"],
            "errors_pct": 100 * failed / max(ok + failed, 1), "ops_per_s": ok / report["summary"]["total"]}


def valuation_stream_run(point):
    result = point["result"]
    lost = result["subscribers"] - result["connected"] + result["dropped"]
    delivery = result["delivery_ms"]["p95"] if result["delivery_ms"] else float("inf")
    return {"delivery_p95_ms": delivery, "errors_pct": 100 * lost / result["subscribers"],
            "ops_per_s": result["updates_received"] / result["seconds"]}


READERS = {"market_data": market_data_run, "orders": orders_run, "valuation_stream": valuation_stream_run}


def within_budget(flow, level, point):
    median = {metric: value[0] for metric, value in point.items() if isinstance(value, tuple)}
    if median["errors_pct"] > MAX_ERRORS:
        return False
    if flow == "market_data":
        return median["on_time_pct"] >= 98 and median["age_p95_s"] <= level + 1
    if flow == "orders":
        return median["p95_ms"] <= 500
    return median["delivery_p95_ms"] <= 1000


def load(flow):
    runs = defaultdict(list)
    for line in (RESULTS / f"{flow}.jsonl").read_text().splitlines():
        point = json.loads(line)
        run = READERS[flow](point)
        run["cores"] = statistics.mean(point["cpu_cores"])
        run["cpu_ms"] = 1000 * run["cores"] / run["ops_per_s"] if run["ops_per_s"] else float("inf")
        runs[point["variant"], point["level"]].append(run)
    points = {}
    for (variant, level), point_runs in runs.items():
        point = {metric: (statistics.median(values), min(values), max(values))
                 for metric in point_runs[0] for values in [[run[metric] for run in point_runs]]}
        point["runs"] = len(point_runs)
        point["met"] = within_budget(flow, level, point)
        points[variant, level] = point
    return points


def number(x):
    if x == float("inf"):
        return "∞"
    return f"{x:.2f}" if abs(x) < 10 else f"{x:.1f}" if abs(x) < 100 else f"{x:,.0f}".replace(",", " ")


def cell(value):
    median, low, high = value
    return f"{number(median)} ({number(low)}–{number(high)})"


def spread(value):
    return value[2] - value[1]


def table(flow, points):
    title, level_name, _, metric, unit = FLOWS[flow]
    extra = ["refreshes on time %"] if flow == "market_data" else []
    header = ["variant", level_name, unit, *extra, "errors %", "CPU cores", f"CPU ms per {OPERATION[flow]}",
              "runs", "within budget"]
    lines = [f"## {title}", "", "Median of runs (min–max).", "",
             "| " + " | ".join(header) + " |", "|" + " --- |" * len(header)]
    for variant in COLORS:
        for level in sorted({level for v, level in points if v == variant}, reverse=flow == "market_data"):
            p = points[variant, level]
            cells = [variant, str(level), cell(p[metric]), *([cell(p["on_time_pct"])] if extra else []),
                     cell(p["errors_pct"]), cell(p["cores"]), cell(p["cpu_ms"]), str(p["runs"]),
                     "yes" if p["met"] else "**no**"]
            lines.append("| " + " | ".join(cells) + " |")
    return lines + [""]


def cpu_change(gunicorn, fastapi):
    difference = fastapi["cpu_ms"][0] - gunicorn["cpu_ms"][0]
    beyond_spread = abs(difference) > max(spread(gunicorn["cpu_ms"]), spread(fastapi["cpu_ms"]))
    return difference / gunicorn["cpu_ms"][0], beyond_spread


def decision(flow, points, orders_guard):
    target = FLOWS[flow][2]
    gunicorn, fastapi = points.get(("gunicorn", target)), points.get(("fastapi", target))
    if not gunicorn or not fastapi:
        return [f"| {FLOWS[flow][0]} | not measured at target | | | |"]
    change, beyond = cpu_change(gunicorn, fastapi)
    if fastapi["met"] and not gunicorn["met"]:
        verdict = "GO: FastAPI within budget, gunicorn not"
    elif fastapi["met"] and gunicorn["met"] and change <= -CPU_SAVING and beyond:
        verdict = "GO: FastAPI uses less CPU per operation"
    elif not fastapi["met"] and not gunicorn["met"]:
        verdict = "NO-GO: neither within budget"
    else:
        verdict = "NO-GO"
    if verdict.startswith("GO") and not orders_guard:
        verdict = "NO-GO: orders slower on FastAPI"
    return [f"| {FLOWS[flow][0]} | {'yes' if gunicorn['met'] else 'no'} | {'yes' if fastapi['met'] else 'no'} "
            f"| {100 * change:+.0f} %{'' if beyond else ' (within spread)'} | {verdict} |"]


def orders_guard_holds(orders):
    gunicorn, fastapi = orders.get(("gunicorn", 50)), orders.get(("fastapi", 50))
    if not gunicorn or not fastapi:
        return True
    slower = fastapi["p95_ms"][0] - gunicorn["p95_ms"][0]
    within_spread = slower <= max(spread(gunicorn["p95_ms"]), spread(fastapi["p95_ms"]))
    return fastapi["p95_ms"][0] <= ORDER_SLOWDOWN * gunicorn["p95_ms"][0] or within_spread


def budget_line(flow, levels):
    if flow == "market_data":
        return [level + 1 for level in levels]
    return [500 if flow == "orders" else 1000] * len(levels)


def chart(all_points, key, ylabel, name):
    figure, axes = plt.subplots(1, len(all_points), figsize=(4.2 * len(all_points), 3.4), squeeze=False)
    axes = axes[0]
    for axis, (flow, points) in zip(axes, all_points.items()):
        title, level_name, _, metric, unit = FLOWS[flow]
        metric = metric if key == "metric" else key
        for variant, color in COLORS.items():
            levels = sorted(level for v, level in points if v == variant)
            values = [points[variant, level][metric] for level in levels]
            medians = [value[0] for value in values]
            errors = [[m - v[1] for m, v in zip(medians, values)], [v[2] - m for m, v in zip(medians, values)]]
            axis.errorbar(levels, medians, yerr=errors, color=color, marker="o", capsize=3, label=variant)
        if key == "metric":
            levels = sorted({level for _, level in points})
            axis.plot(levels, budget_line(flow, levels), color="#888", linestyle="--", linewidth=1, label="budget")
        axis.set(title=title, xlabel=level_name, ylabel=unit if key == "metric" else ylabel)
        axis.set_xticks(sorted({level for _, level in points}))
        axis.grid(alpha=0.3)
    axes[0].legend()
    figure.tight_layout()
    (RESULTS / "charts").mkdir(exist_ok=True)
    figure.savefig(RESULTS / "charts" / name, dpi=150)


def main():
    all_points = {flow: load(flow) for flow in FLOWS if (RESULTS / f"{flow}.jsonl").exists()}
    lines = ["# Part 2: core flows", ""]
    if (RESULTS / "stub.json").exists():
        stub = json.loads((RESULTS / "stub.json").read_text())
        p = stub["latencyPercentiles"]
        lines += [f"**Stub alone** at 1 250 calls at once: {number(stub['summary']['requestsPerSec'])} calls/s, "
                  f"p50 {number(1000 * p['p50'])} ms, p99 {number(1000 * p['p99'])} ms", ""]
    if (RESULTS / "revalue.jsonl").exists():
        samples = [json.loads(line) for line in (RESULTS / "revalue.jsonl").read_text().splitlines()]
        micros = [sample["us_per_position"] for sample in samples]
        cores = [sample["cores_for_1m_positions_per_minute"] for sample in samples]
        lines += [f"**Revaluation** (Black–Scholes, `desk_pricing`, {len(samples)} runs): "
                  f"{number(statistics.median(micros))} µs per position ({number(min(micros))}–{number(max(micros))}) "
                  f"= {statistics.median(cores):.3f} cores for 1 000 000 positions per minute", ""]
    for flow, points in all_points.items():
        lines += table(flow, points)
    guard = orders_guard_holds(all_points.get("orders", {}))
    lines += ["## Rule at target level", "",
              f"Orders on FastAPI at 50 at once ≤ 110 % of gunicorn's p95: {'yes' if guard else '**no**'}", "",
              "| Flow | gunicorn within budget | FastAPI within budget | FastAPI CPU per operation vs gunicorn "
              "| Decision |", "| --- | --- | --- | --- | --- |"]
    for flow, points in all_points.items():
        lines += decision(flow, points, guard)
    (RESULTS / "summary.md").write_text("\n".join(lines) + "\n")
    chart(all_points, "metric", "", "flows.png")
    chart(all_points, "cpu_ms", "CPU ms per operation", "cpu.png")
    print((RESULTS / "summary.md").read_text())


if __name__ == "__main__":
    main()
