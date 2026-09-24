import csv
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, LogLocator, NullLocator

RESULTS = Path(sys.argv[1] if len(sys.argv) > 1 else "results")
COLORS = {"bottle-sync": "#2a78d6", "bottle-threads": "#eb6834",
          "fastapi-async": "#1baf7a", "fastapi-sync": "#eda100"}
MARKERS = dict(zip(COLORS, "osD^"))
BOTTLE, FASTAPI = ("bottle-sync", "bottle-threads"), ("fastapi-async", "fastapi-sync")
TITLES = {"s1": "S1 GET /health", "s2": "S2 GET /io, stub waits 50 ms", "s3": "S3 GET /cpu",
          "s4": "S4 POST /db, write then read", "s5": "S5 GET /health at c = 10 beside open streams"}
BUDGET_MS, MAX_ERRORS = 100, 1.0
NAME = re.compile(r"(?P<variant>[a-z-]+)_(?P<scenario>s\d)_(?:c|streams)(?P<level>\d+)_run\d+\.json")
COLUMNS = (("rps", "req/s", True), ("p50", "p50 ms", False), ("p95", "p95 ms", True), ("p99", "p99 ms", False),
           ("errors", "errors %", True), ("cpu", "CPU %", False), ("cpu_ms", "CPU ms/req", False),
           ("rss", "RSS MB", False))


def read_run(path):
    report = json.loads(path.read_text())
    codes, percentiles = report["statusCodeDistribution"], report["latencyPercentiles"]
    ok = sum(n for code, n in codes.items() if code.startswith("2"))
    kinds = Counter({kind: n for kind, n in report["errorDistribution"].items() if kind != "aborted due to deadline"})
    kinds.update({f"HTTP {code}": n for code, n in codes.items() if not code.startswith("2")})
    usage = list(csv.DictReader(path.with_suffix(".usage.csv").open()))
    streams = path.with_suffix(".streams")
    run = {"rps": ok / report["summary"]["total"], "errors": 100 * kinds.total() / max(ok + kinds.total(), 1),
           "cpu": statistics.median(float(row["cpu_percent"]) for row in usage),
           "rss": max(float(row["rss_mb"]) for row in usage), "kinds": kinds,
           "streams": streams.read_text().split("answered=")[1].strip() if streams.exists() else ""}
    run["cpu_ms"] = run["cpu"] * 10 / run["rps"] if ok else None
    for key in ("p50", "p95", "p99"):
        run[key] = percentiles[key] * 1000 if ok else None
    return run


def load_points():
    runs = defaultdict(list)
    for path in RESULTS.glob("*_run*.json"):
        match = NAME.fullmatch(path.name)
        runs[match["scenario"], match["variant"], int(match["level"])].append(read_run(path))
    points = {}
    for key, point_runs in runs.items():
        points[key] = {"kinds": sum((run["kinds"] for run in point_runs), Counter()),
                       "streams": " ".join(run["streams"] for run in point_runs)}
        for metric, _, _ in COLUMNS:
            values = [run[metric] for run in point_runs if run[metric] is not None]
            points[key][metric] = (statistics.median(values), min(values), max(values)) if values else None
    return points


def number(x):
    return f"{x:.1f}" if x < 100 else f"{x:.0f}"


def fmt(value, spread=False):
    if value is None:
        return "–"
    median, low, high = value
    return f"{number(median)} ({number(low)}–{number(high)})" if spread else number(median)


def table(points, scenario):
    rows = sorted((list(COLORS).index(v), c, v, p) for (s, v, c), p in points.items() if s == scenario)
    header = ["variant", "streams" if scenario == "s5" else "c", *(title for _, title, _ in COLUMNS)]
    header += ["answered"] if scenario == "s5" else []
    lines = ["| " + " | ".join(header) + " |", "|" + " --- |" * len(header)]
    for _, c, variant, p in rows:
        cells = [variant, str(c), *(fmt(p[key], spread) for key, _, spread in COLUMNS)]
        lines.append("| " + " | ".join(cells + ([p["streams"]] if scenario == "s5" else [])) + " |")
    lines += [f"- {v} at {c}: " + ", ".join(f"{kind} × {n}" for kind, n in p["kinds"].items())
              for _, c, v, p in rows if p["kinds"]]
    return "\n".join(lines)


def chart(points, scenario):
    figure, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, key, label in zip(axes, ("rps", "p95"), ("successful req/s", "p95 latency, ms")):
        for variant, color in COLORS.items():
            rows = sorted((c, p[key]) for (s, v, c), p in points.items() if s == scenario and v == variant and p[key])
            if rows:
                ax.errorbar([c for c, _ in rows], [m for _, (m, _, _) in rows], capsize=3, color=color,
                            yerr=[[m - low for _, (m, low, _) in rows], [high - m for _, (m, _, high) in rows]],
                            marker=MARKERS[variant], markersize=8, linewidth=2, label=variant)
        if key == "p95" and scenario != "s3":
            ax.axhline(BUDGET_MS, color="#888888", linestyle="--", linewidth=1, label="budget 100 ms")
        ticks = [10, 50, 200] if scenario == "s5" else [1, 10, 50, 200]
        medians = [p[key][0] for (s, _, _), p in points.items() if s == scenario and p[key]]
        wide = min(medians) > 0 and max(medians) > 10 * min(medians)
        ax.set(xscale="log", yscale="log" if wide else "linear", ylabel=label,
               xlabel="open streams" if scenario == "s5" else "c")
        ax.set_xticks(ticks, [str(tick) for tick in ticks])
        ax.xaxis.set_minor_locator(NullLocator())
        if wide:
            ax.yaxis.set_major_locator(LogLocator(subs=(1, 2, 5)))
            ax.yaxis.set_minor_locator(NullLocator())
            ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}"))
        else:
            ax.set_ylim(bottom=0)
        ax.grid(alpha=0.3)
        ax.spines[["top", "right"]].set_visible(False)
    axes[1].legend(frameon=False)
    figure.suptitle(TITLES[scenario] + " — median, bars = min–max of runs")
    figure.tight_layout()
    figure.savefig(RESULTS / "charts" / f"{scenario}.png", dpi=120)
    plt.close(figure)


def better(points, scenario, level, variants):
    valid = [(v, points[scenario, v, level]) for v in variants if (scenario, v, level) in points
             and points[scenario, v, level]["errors"][0] <= MAX_ERRORS and points[scenario, v, level]["p95"]]
    return min(valid, key=lambda item: item[1]["p95"][0]) if valid else (None, None)


def beyond_spread(a, b):
    return abs(a[0] - b[0]) > max(a[2] - a[1], b[2] - b[1])


def side(framework, variant, point):
    if point is None:
        return f"{framework}: none within 1 % errors"
    return f"{framework} {variant}: {fmt(point['rps'])} req/s, p95 {fmt(point['p95'])} ms"


def regression(f, b):
    return f is None or (b is not None and (
        (f["rps"][0] < 0.9 * b["rps"][0] and beyond_spread(f["rps"], b["rps"])) or
        (f["p95"][0] > 1.1 * b["p95"][0] and beyond_spread(f["p95"], b["p95"]))))


def gain(f, b):
    return f is not None and (b is None or
                              (f["p95"][0] <= 0.7 * b["p95"][0] and beyond_spread(f["p95"], b["p95"])) or
                              (f["rps"][0] >= 2 * b["rps"][0] and beyond_spread(f["rps"], b["rps"])))


def need(f, b):
    return f is not None and f["p95"][0] <= BUDGET_MS and (b is None or b["p95"][0] > BUDGET_MS)


def gates(points):
    lines = {}

    def pair(scenario, level):
        (fv, f), (bv, b) = better(points, scenario, level, FASTAPI), better(points, scenario, level, BOTTLE)
        lines[f"{scenario} at {level}"] = side("FastAPI", fv, f) + " | " + side("Bottle", bv, b)
        return f, b

    regressions = [f"{s} at {c}" for s, c in (("s3", 10), ("s3", 50), ("s4", 10), ("s4", 50))
                   if regression(*pair(s, c))]
    gains = [f"{s} at 50" for s in ("s2", "s5") if gain(*pair(s, 50))]
    needs = [f"{s} at 50" for s in ("s2", "s4", "s5") if need(*pair(s, 50))]
    verdicts = [("1. No regression (S3, S4 at c = 10, 50)", not regressions, "regression", regressions),
                ("2. Real gain (S2 c = 50 or S5 50 streams)", bool(gains), "gain", gains),
                ("4. Need (at 50, Bottle misses the budget, FastAPI meets it)", bool(needs), "need", needs)]
    header = [f"- Gate {name}: **{'PASS' if passed else 'FAIL'}**" + (f" ({label}: {', '.join(where)})" if where else "")
              for name, passed, label, where in verdicts]
    return "\n".join(header + ["- Gate 3. Cost: judged in the report", "",
                               "Better variant = lower median p95 among variants with at most 1 % errors.",
                               "", "```", *(f"{point}: {text}" for point, text in lines.items()), "```"])


def main():
    points = load_points()
    (RESULTS / "charts").mkdir(exist_ok=True)
    stub = json.loads((RESULTS / "stub_c200.json").read_text())
    pct, stub_ok = stub["latencyPercentiles"], stub["statusCodeDistribution"].get("200", 0)
    parts = ["# Benchmark summary", "",
             "Median of runs; (min–max) where shown. Errors include timeouts. RSS: the serving process.", "",
             f"Stub alone at c = 200: {stub_ok / stub['summary']['total']:.0f} req/s, p50 {pct['p50'] * 1000:.1f} ms, "
             f"p99 {pct['p99'] * 1000:.1f} ms", "", "## Gates", "", gates(points)]
    for scenario in sorted({s for s, _, _ in points}):
        chart(points, scenario)
        parts += ["", f"## {TITLES[scenario]}", "", table(points, scenario), "", f"![{scenario}](charts/{scenario}.png)"]
    (RESULTS / "summary.md").write_text("\n".join(parts) + "\n")
    print("\n".join(parts))


if __name__ == "__main__":
    main()
