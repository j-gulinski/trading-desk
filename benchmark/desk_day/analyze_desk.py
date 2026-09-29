"""Tables and charts for Part 2, the desk core, and Part 2b, many traders trading."""

import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

RESULTS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "results" / "desk_day"
NAME = re.compile(r"(?P<variant>[a-z]+)_k(?P<k>\d+)(?:_t(?P<t>\d+))?_run\d+")
COLORS = {"wsgiref": "#e87ba4", "gunicorn": "#eb6834", "fastapi": "#1baf7a"}
MARKERS = {"wsgiref": "o", "gunicorn": "s", "fastapi": "D"}
KS = (10, 50, 100, 200)
TITLES = {"tick": "Tick delivery", "valuation": "Valuation freshness", "preview": "Price preview",
          "position": "Position on screen", "execution": "Order execution",
          "md_errors": "Market-data and pricing errors", "errors": "All errors"}
BUDGETS = {"tick": 1000, "valuation": 1000, "preview": 300, "position": 3000, "execution": 500,
           "md_errors": 1.0, "errors": 1.0}
MD_PRICING = ("tick", "valuation", "preview", "position", "md_errors")
STREAMS = ("tick", "valuation", "position", "md_errors")
BASELINE = "gunicorn"
CANDIDATE = "fastapi"
DECISION_K = 200
CLIENT_CORES = 0.8
PRICING_LAG_S = 5.0
OTHER_HOST_CORES = 3.0


class Stat(NamedTuple):
    median: float
    low: float
    high: float


def host_cores(start, end):
    path = RESULTS / "host_cpu.txt"
    if not path.exists():
        return None
    busy = []
    for line in path.read_text().splitlines():
        epoch, cores = line.split()
        if start <= float(epoch) <= end:
            busy.append(float(cores))
    return statistics.mean(busy) if busy else None


def cgroup_sample(path):
    epoch, *lines = path.read_text().splitlines()
    return float(epoch), {name: int(usec) for name, usec in (line.split() for line in lines)}


def cgroup_usage(path):
    start, before = cgroup_sample(path / "cgroup.stable")
    end, after = cgroup_sample(path / "cgroup.done")
    return end - start, {name: after[name] - before[name] for name in after}


def read_run(path, k):
    if (path / "unstable").exists() or not (path / "summary.json").exists():
        return None
    summary = json.loads((path / "summary.json").read_text())
    run = dict(summary["p95_ms"])
    run["preview"], previews, previews_ok = None, 0, 0
    if (path / "preview.json").exists():
        preview = json.loads((path / "preview.json").read_text())
        codes = preview["statusCodeDistribution"]
        previews_ok = sum(n for code, n in codes.items() if code.startswith("2"))
        unsent = sum(n for kind, n in preview["errorDistribution"].items() if kind != "aborted due to deadline")
        previews = sum(codes.values()) + unsent
        run["preview"] = preview["latencyPercentiles"]["p95"] * 1000 if previews_ok else None
    orders = (summary["opens"], summary["closes"])
    trades = sum(n for side in orders for result, n in side.items() if result != "no_quote")
    trade_errors = sum(side.get("error", 0) for side in orders)
    md_failed = summary["streams_dropped"] + previews - previews_ok
    md_total = summary["streams_opened"] + previews
    run["md_errors"] = 100 * md_failed / md_total
    run["errors"] = 100 * (md_failed + trade_errors) / (md_total + trades)
    run["flags"] = []
    if summary["client_cores"] > CLIENT_CORES:
        run["flags"].append(f"client CPU {summary['client_cores']} cores")
    lag = summary["pricing_lag_p95_s"] or 0
    if lag > PRICING_LAG_S:
        run["flags"].append(f"pricing lag p95 {lag} s")
    if (path / "cgroup.done").exists():
        seconds, usage = cgroup_usage(path)
        run["cores"] = (usage["market-data-service"] + usage["pricing-service"]) / 1e6 / seconds
        run["cores_per_100"] = 100 * run["cores"] / k
        desk = sum(usage.values()) / 1e6 / seconds
        host = host_cores(summary["stable_at"], summary["stable_at"] + seconds)
        if host is not None and host - desk > OTHER_HOST_CORES:
            run["flags"].append(f"other programs {host - desk:.1f} cores")
    return run


def trader_levels():
    return sorted({int(match["t"]) for path in RESULTS.iterdir()
                   if path.is_dir() and (match := NAME.fullmatch(path.name)) and match["t"]})


def load_points(trading):
    runs = defaultdict(list)
    for path in sorted(RESULTS.iterdir()):
        match = NAME.fullmatch(path.name)
        if path.is_dir() and match and bool(match["t"]) == trading:
            k = int(match["k"])
            runs[match["variant"], int(match["t"]) if trading else k].append((path.name, read_run(path, k)))
    points, flags = {}, []
    for key, named in runs.items():
        stable = [run for _, run in named if run]
        points[key] = {"unstable": len(stable) < len(named), "previews": any((RESULTS / name / "preview.json").exists() for name, _ in named)}
        for metric in (*TITLES, "cores", "cores_per_100"):
            values = [run[metric] for run in stable if run.get(metric) is not None]
            points[key][metric] = Stat(statistics.median(values), min(values), max(values)) if values else None
        for name, run in named:
            if run is None:
                flags.append(f"- {name}: unstable")
            elif run["flags"]:
                flags.append(f"- {name}: {', '.join(run['flags'])}")
    return points, flags


def number(x):
    if x < 10:
        return f"{x:.2f}"
    if x < 100:
        return f"{x:.1f}"
    return f"{x:.0f}"


def within(point, metric):
    return bool(point and not point["unstable"] and point[metric] and point[metric].median <= BUDGETS[metric])


def cell(point, metric):
    if point is None or (metric == "preview" and not point["previews"]):
        return "–"
    value = point[metric]
    text = f"{number(value.median)} ({number(value.high - value.low)})" if value else "no data"
    mark = "✓" if within(point, metric) else "✗"
    return f"{text} {mark}" + (" unstable" if point["unstable"] else "")


def variants(points):
    return [variant for variant in COLORS if any(v == variant for v, _ in points)]


def table(points, levels, axis, header, row):
    lines = [header, "", f"| variant | {' | '.join(f'{axis} = {k}' for k in levels)} |",
             "| --- |" + " --- |" * len(levels)]
    for v in variants(points):
        lines.append(f"| {v} | " + " | ".join(row(points.get((v, k))) for k in levels) + " |")
    return "\n".join(lines)


def beyond_spread(a, b):
    return abs(a.median - b.median) > max(a.high - a.low, b.high - b.low)


def stable_pair(points, k):
    base, cand = points.get((BASELINE, k)), points.get((CANDIDATE, k))
    if base and cand and not base["unstable"] and not cand["unstable"]:
        return base, cand
    return None


def largest_k_within(points, variant):
    return max((k for k in KS if all(within(points.get((variant, k)), m) for m in MD_PRICING)), default=0)


def latency_gains(points):
    pair = stable_pair(points, DECISION_K)
    if pair is None:
        return []
    base, cand = pair
    return [m for m in ("tick", "preview", "valuation") if base[m] and cand[m]
            and cand[m].median <= 0.7 * base[m].median and beyond_spread(cand[m], base[m])]


def cpu_within(pair):
    base, cand = pair[0]["cores_per_100"], pair[1]["cores_per_100"]
    return not (cand.median > 1.1 * base.median and beyond_spread(cand, base))


def cpu_check(points):
    for k in reversed(KS):
        pair = stable_pair(points, k)
        if pair and pair[0]["cores_per_100"] and pair[1]["cores_per_100"]:
            return k, cpu_within(pair)
    return None, False


def decision(points):
    level = {v: largest_k_within(points, v) for v in variants(points)}
    a = level.get(CANDIDATE, 0) > level.get(BASELINE, 0)
    gains = latency_gains(points)
    cpu_k, cpu_ok = cpu_check(points)
    lines = [f"- Largest K within the market-data and pricing budgets, {v}: {k or 'none'}" for v, k in level.items()]
    return "\n".join(lines + [
        f"- (a) {CANDIDATE} within those budgets at least one K level higher: **{'yes' if a else 'no'}**",
        f"- (b) at K = {DECISION_K}, p95 at least 30 % lower beyond the larger spread: **{', '.join(gains) or 'no'}**",
        f"- Market-data + pricing CPU per client at most 10 % higher (K = {cpu_k or '–'}): "
        f"**{'yes' if cpu_ok else 'no'}**",
        f"- Market-data and pricing: **{'GO' if (a or gains) and cpu_ok else 'NO-GO'}**"])


def trading_decision(points, levels):
    held = [t for t in levels if all(within(points.get((BASELINE, t)), m) for m in STREAMS)]
    kept = [t for t in held if all(within(points.get((CANDIDATE, t)), m) for m in STREAMS)]
    streams_ok = kept == held
    cpu_t = held[-1] if held else next((t for t in reversed(levels) if stable_pair(points, t)), None)
    pair = stable_pair(points, cpu_t) if cpu_t is not None else None
    cpu_ok = bool(pair and pair[0]["cores_per_100"] and pair[1]["cores_per_100"] and cpu_within(pair))
    return "\n".join([
        f"- T within the market-data and pricing budgets, {BASELINE}: {', '.join(map(str, held)) or 'none'}",
        f"- {CANDIDATE} within those budgets at each of them: **{'yes' if streams_ok else 'no'}**",
        f"- Market-data + pricing CPU per client at most 10 % higher (T = {cpu_t if cpu_t is not None else '–'}): "
        f"**{'yes' if cpu_ok else 'no'}**",
        f"- The Part 2 GO for the streams: **{'stands' if streams_ok and cpu_ok else 'withdrawn'}**"])


def plot(ax, points, levels, axis, metric, title, budget=None):
    for variant, color in COLORS.items():
        rows = sorted((k, p[metric]) for (v, k), p in points.items() if v == variant and p[metric])
        if rows:
            ax.errorbar([k for k, _ in rows], [s.median for _, s in rows], capsize=3, color=color,
                        yerr=[[s.median - s.low for _, s in rows], [s.high - s.median for _, s in rows]],
                        marker=MARKERS[variant], markersize=7, linewidth=2, label=variant)
    if budget is not None:
        ax.axhline(budget, color="#888888", linestyle="--", linewidth=1, label="budget")
    ax.set(xscale="log", title=title, xlabel="T traders" if axis == "T" else "K clients", xticks=levels,
           xticklabels=[str(k) for k in levels], ylim=(0, None))
    ax.minorticks_off()
    ax.grid(alpha=0.3)
    ax.spines[["top", "right"]].set_visible(False)


def charts(points, levels, axis, heading):
    (RESULTS / "charts").mkdir(exist_ok=True)
    latency, axes = plt.subplots(2, 3, figsize=(14, 8))
    metrics = [m for m in ("tick", "valuation", "preview", "position", "execution", "md_errors")
               if any(point[m] for point in points.values())]
    for ax in axes.flat[len(metrics):]:
        ax.set_visible(False)
    for ax, metric in zip(axes.flat, metrics):
        unit = ", %" if metric == "md_errors" else ", p95 ms"
        plot(ax, points, levels, axis, metric, TITLES[metric] + unit, BUDGETS[metric])
    latency.suptitle(f"{heading} — median, bars = min–max of runs")
    cpu, ax = plt.subplots(figsize=(6, 4))
    plot(ax, points, levels, axis, "cores", "Market-data + pricing CPU, cores")
    for figure, name in ((latency, "desk_p95"), (cpu, "desk_cpu")):
        figure.axes[0].legend(frameon=False)
        figure.tight_layout()
        figure.savefig(RESULTS / "charts" / f"{name}.png", dpi=120)
    plt.close("all")


def metric_table(points, levels, axis, metric):
    unit = "%" if metric.endswith("errors") else "ms, p95"
    return table(points, levels, axis, f"## {TITLES[metric]} ({unit}, budget {BUDGETS[metric]:g})",
                 lambda p: cell(p, metric))


def cpu_cell(point):
    if not point or not point["cores"]:
        return "–"
    return f"{number(point['cores'].median)} ({number(point['cores_per_100'].median)})"


def main():
    traders = trader_levels()
    levels, axis = (traders, "T") if traders else (KS, "K")
    heading = "Part 2b: many traders trading" if traders else "Part 2: the desk core"
    points, flags = load_points(bool(traders))
    charts(points, levels, axis, heading)
    parts = [f"# {heading}", "", "Median of runs (spread = max − min). ✓ within budget, ✗ out.", "",
             "## Decision", "", trading_decision(points, levels) if traders else decision(points), "",
             "## Flagged runs", "", "\n".join(flags) or "- none"]
    for metric in TITLES:
        parts += ["", metric_table(points, levels, axis, metric)]
    parts += ["", table(points, levels, axis, "## Market-data + pricing CPU: cores (per 100 clients)", cpu_cell),
              "", "![p95](charts/desk_p95.png)", "", "![cpu](charts/desk_cpu.png)"]
    (RESULTS / "summary.md").write_text("\n".join(parts) + "\n")
    print("\n".join(parts))


if __name__ == "__main__":
    main()
