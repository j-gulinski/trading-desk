"""Aggregates a results directory into tables, charts and the gate check.

Usage: python analyze.py [results-dir]   (default: results)

Reads the hey summaries (<variant>_<scenario>_c<c>_run<n>.txt), CPU/RSS samples (.usage.csv)
and blocking_demo.sh output (demo_<load>_run<n>.txt). Writes summary.csv, summary.md and
charts/<scenario>.png into the same directory. The gates from docs/decision_criteria.md are
checked when the Stage 1 variants are present; before/after is compared when those are.
"""
import csv
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).parent
RESULTS = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "results"
CHARTS = RESULTS / "charts"

ORDER = ["A", "A-threads", "B", "before", "after", "B-std"]
LABELS = {
    "A": "A · Bottle, sync", "A-threads": "A′ · Bottle, 40 threads", "B": "B · FastAPI",
    "before": "before · wsgiref, thread per connection", "after": "after · gunicorn, 40 threads",
    "B-std": "B-std · FastAPI on uvloop + httptools",
}
COLORS = {"A": "#2a78d6", "A-threads": "#eb6834", "B": "#1baf7a",
          "before": "#2a78d6", "after": "#eb6834", "B-std": "#1baf7a"}
VARIANTS = []  # the ones present in RESULTS, set in main()
SCENARIOS = {
    "s1": "S1 /health — framework overhead",
    "s2": "S2 /io — waits 50 ms on another service",
    "s3": "S3 /cpu — computation",
    "s4": "S4 /books — real books-service code",
}
LEVELS = [1, 10, 50, 200]
MAX_ERROR_RATE = 0.01
NAME = re.compile(r"(?P<variant>.+)_(?P<scenario>s\d)_c(?P<c>\d+)_run(?P<run>\d+)\.txt")


def parse_hey(text):
    """One hey summary -> throughput, percentiles in ms, error rate."""
    rps = float(re.search(r"Requests/sec:\s+([\d.]+)", text).group(1))
    pct = {int(p): float(s) * 1000 for p, s in re.findall(r"(\d+)%+ in ([\d.]+) secs", text)}
    ok = bad = 0
    for code, count in re.findall(r"\[(\d{3})\]\s+(\d+) responses", text):
        if code.startswith("2"):
            ok += int(count)
        else:
            bad += int(count)
    errors_block = text.split("Error distribution:")[1] if "Error distribution:" in text else ""
    bad += sum(int(n) for n in re.findall(r"\[(\d+)\]", errors_block))
    total = ok + bad
    return {
        "rps": rps,
        "p50": pct.get(50), "p95": pct.get(95), "p99": pct.get(99),
        "errors": bad / total if total else 1.0,
    }


def parse_usage(path):
    rows = list(csv.DictReader(path.open())) if path.exists() else []
    if not rows:
        return {"cpu": None, "rss": None}
    return {
        "cpu": statistics.mean(float(r["cpu_percent"]) for r in rows),
        "rss": max(float(r["rss_mb"]) for r in rows),
    }


def load_runs():
    runs = []
    for path in sorted(RESULTS.glob("*_s*_c*_run*.txt")):
        m = NAME.fullmatch(path.name)
        if not m:
            continue
        row = {"variant": m["variant"], "scenario": m["scenario"],
               "c": int(m["c"]), "run": int(m["run"])}
        row.update(parse_hey(path.read_text()))
        row.update(parse_usage(path.with_suffix(".usage.csv")))
        runs.append(row)
    return runs


def aggregate(runs):
    """Median and spread (max - min) over the runs of each point."""
    groups = defaultdict(list)
    for r in runs:
        groups[(r["variant"], r["scenario"], r["c"])].append(r)
    points = {}
    for key, rs in groups.items():
        point = {"runs": len(rs)}
        for metric in ("rps", "p50", "p95", "p99", "errors", "cpu", "rss"):
            values = [r[metric] for r in rs if r[metric] is not None]
            point[metric] = statistics.median(values) if values else None
            point[metric + "_min"] = min(values) if values else None
            point[metric + "_max"] = max(values) if values else None
        points[key] = point
    return points


def spread(point, metric):
    return point[metric + "_max"] - point[metric + "_min"]


def fails(point):
    return point["errors"] > MAX_ERROR_RATE


def best_wsgi(points, scenario, c):
    """The better of A and A-threads at a point: fewer errors first, then throughput."""
    candidates = [points[(v, scenario, c)] | {"variant": v} for v in ("A", "A-threads")]
    return max(candidates, key=lambda p: (not fails(p), p["rps"]))


def compare(b, w, metric):
    """Relative change of B against WSGI; None when the gap is inside the spread."""
    gap = b[metric] - w[metric]
    if abs(gap) <= max(spread(b, metric), spread(w, metric)):
        return None
    return gap / w[metric]


def gate_gain(points, c):
    """Gates 2 and 4: in S2, p95 down >= 30 % or throughput >= 2x against WSGI."""
    b, w = points[("B", "s2", c)], best_wsgi(points, "s2", c)
    if fails(b):
        return False, f"B has {b['errors']:.1%} errors"
    if fails(w):
        return True, f"WSGI ({w['variant']}) has {w['errors']:.1%} errors, B none"
    p95, rps = compare(b, w, "p95"), compare(b, w, "rps")
    passed = (p95 is not None and p95 <= -0.30) or (rps is not None and rps >= 1.0)
    fmt = lambda x: "no difference" if x is None else f"{x:+.0%}"
    return passed, f"against {w['variant']}: p95 {fmt(p95)}, throughput {fmt(rps)}"


def gates(points):
    lines = []
    for scenario in ("s1", "s3", "s4"):
        b, w = points[("B", scenario, 10)], best_wsgi(points, scenario, 10)
        change = compare(b, w, "rps")
        ok = not fails(b) and (change is None or change >= -0.10)
        shown = "no difference" if change is None else f"{change:+.0%}"
        lines.append(f"| 1 | {scenario.upper()} c = 10 | throughput vs {w['variant']}: {shown} "
                     f"| {'pass' if ok else 'FAIL'} |")
    ok2, why2 = gate_gain(points, 50)
    lines.append(f"| 2 | S2 c = 50 | {why2} | {'pass' if ok2 else 'FAIL'} |")
    lines.append("| 3 | cost ≤ 40 h | estimated in Stage 2 | — |")
    ok4, why4 = gate_gain(points, 10)
    lines.append(f"| 4 | S2 c = 10 | {why4} | {'pass' if ok4 else 'FAIL'} |")
    head = ["| Gate | Point | Result | Verdict |", "| --- | --- | --- | --- |"]
    return head + lines


def fmt_range(point, metric, digits):
    m, lo, hi = point[metric], point[metric + "_min"], point[metric + "_max"]
    return f"{m:.{digits}f} ({lo:.{digits}f}–{hi:.{digits}f})"


def versus(points, base, other):
    """Change of `other` against `base` at every point, uncertainty rule applied."""
    out = ["| Scenario | c | Throughput | p95 |", "| --- | --- | --- | --- |"]
    for scenario in SCENARIOS:
        for c in LEVELS:
            b, a = points[(base, scenario, c)], points[(other, scenario, c)]
            cells = []
            for metric in ("rps", "p95"):
                change = compare(a, b, metric)
                cells.append("no difference" if change is None else f"{change:+.0%}")
            out.append(f"| {scenario.upper()} | {c} | {cells[0]} | {cells[1]} |")
    return out


def demo():
    """blocking_demo.sh: /health latency while ten clients load /cpu."""
    groups = defaultdict(list)
    for path in sorted(RESULTS.glob("demo_*_run*.txt")):
        load = re.fullmatch(r"demo_(.+)_run\d+\.txt", path.name)[1]
        groups[load].append(parse_hey(path.read_text()))
    if not groups:
        return []
    out = ["| Load beside /health | /health p50 ms | p95 ms | p99 ms | /health req/s |",
           "| --- | --- | --- | --- | --- |"]
    for load in ("none", "cpu", "cpu-async"):
        rs = groups.get(load, [])
        if rs:
            med = lambda m: statistics.median(r[m] for r in rs)
            out.append(f"| {load} | {med('p50'):.1f} | {med('p95'):.1f} | {med('p99'):.1f} "
                       f"| {med('rps'):.0f} |")
    return out


def tables(points):
    out = []
    for scenario, title in SCENARIOS.items():
        out += [f"### {title}", "",
                "| c | Variant | Throughput req/s | p50 ms | p95 ms | p99 ms | Errors | CPU % | RSS MB |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for c in LEVELS:
            for v in VARIANTS:
                p = points.get((v, scenario, c))
                if p is None:
                    continue
                out.append(
                    f"| {c} | {LABELS[v]} | {fmt_range(p, 'rps', 0)} | {p['p50']:.1f} "
                    f"| {fmt_range(p, 'p95', 1)} | {p['p99']:.1f} | {p['errors']:.1%} "
                    f"| {p['cpu']:.0f} | {p['rss']:.0f} |")
        out.append("")
    return out


def chart(points, scenario, title):
    fig, (ax_rps, ax_p95) = plt.subplots(1, 2, figsize=(10, 3.8), layout="constrained")
    for ax, metric, ylabel in ((ax_rps, "rps", "throughput, req/s"),
                               (ax_p95, "p95", "p95 latency, ms (log)")):
        for v in VARIANTS:
            ps = [points[(v, scenario, c)] for c in LEVELS]
            y = [p[metric] for p in ps]
            err = [[p[metric] - p[metric + "_min"] for p in ps],
                   [p[metric + "_max"] - p[metric] for p in ps]]
            ax.errorbar(LEVELS, y, yerr=err, color=COLORS[v], label=LABELS[v], linewidth=2,
                        marker="o", markersize=6, capsize=3,
                        markeredgecolor="#fcfcfb", markeredgewidth=1.5)
        ax.set_xscale("log")
        ax.set_xticks(LEVELS, [str(c) for c in LEVELS])
        ax.minorticks_off()
        ax.set_xlabel("concurrent clients (c)", color="#52514e")
        ax.set_ylabel(ylabel, color="#52514e")
        if metric == "p95":
            ax.set_yscale("log")
        else:
            ax.set_ylim(bottom=0)
        ax.grid(True, color="#e6e5e0", linewidth=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color("#c3c2b7")
        ax.tick_params(colors="#52514e")
        ax.set_facecolor("#fcfcfb")
    ax_rps.legend(frameon=False, fontsize=9)
    fig.suptitle(title + "  ·  median of 3 runs, bars = min–max", color="#0b0b0b", fontsize=11)
    fig.patch.set_facecolor("#fcfcfb")
    fig.savefig(CHARTS / f"{scenario}.png", dpi=150)
    plt.close(fig)


def main():
    runs = load_runs()
    points = aggregate(runs)
    VARIANTS[:] = [v for v in ORDER if any(r["variant"] == v for r in runs)]
    CHARTS.mkdir(exist_ok=True)

    with (RESULTS / "summary.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(runs[0]))
        writer.writeheader()
        writer.writerows(runs)

    lines = ["# Benchmark summary", "",
             "Median of the runs, (min–max) in brackets. Generated by `analyze.py`.", ""]
    lines += tables(points)
    if {"A", "A-threads", "B"} <= set(VARIANTS):
        lines += ["## Gates", ""] + gates(points) + [""]
    if {"before", "after"} <= set(VARIANTS):
        lines += ["## After against before", ""] + versus(points, "before", "after") + [""]
    if {"after", "B-std"} <= set(VARIANTS):
        lines += ["## B-std against after", ""] + versus(points, "after", "B-std") + [""]
    if demo():
        lines += ["## Blocking demo", ""] + demo() + [""]
    (RESULTS / "summary.md").write_text("\n".join(lines))

    for scenario, title in SCENARIOS.items():
        chart(points, scenario, title)
    print(f"wrote {RESULTS / 'summary.md'}")


if __name__ == "__main__":
    main()
